"""Librarian (docs/features/05-literature.md, prompt in 09 § Librarian).

Turns a question into a search strategy, searches OpenAlex and Europe PMC, and fetches legally open full
text in this order: Europe PMC full-text XML (PMC open access) → arXiv PDF → OpenAlex best open-access PDF.
Anything it cannot fetch stays abstract-only (or metadata-only); nothing is upgraded later.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from backend.agents import sanitize_log_message
from backend.research.llm import call_json

logger = logging.getLogger("ThothLibrarian")

UA = {"User-Agent": "Thoth-Research-Companion/1.0 (mailto:academic-research@thoth.ai)"}
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_TEXT_CHARS = 40000

STRATEGY_PROMPT = """ROLE
You are Thoth's Librarian. You turn a research question into a search strategy. You find papers; you do not
judge them.

METHOD
1. Classify the question: intervention/exposure → PICO; experience/meaning → PEO; other → concepts.
2. Break it into 2-4 concept blocks, each with synonyms and spelling variants.
3. Write a short keyword query for OpenAlex (plain words, no Boolean operators, at most 10 words) and a
   Boolean query for Europe PMC (AND between blocks, OR within a block, quoted phrases). Use AT MOST THREE
   blocks in the Europe PMC query, the exposure/population and the outcome first; never AND in the
   comparison group or the proposed mechanism as a separate block (it would exclude most relevant papers).
   At most 4 synonyms per block.
4. Add 1-2 adjacent fields where the same mechanism is studied under another name, each with a short
   keyword query (at most 8 words).

OUTPUT (JSON)
{"framework": "PICO"|"PEO"|"concepts",
 "blocks": [{"name": str, "synonyms": [str]}],
 "queries": {"openalex": str, "europepmc": str},
 "adjacent_fields": [{"field": str, "why": str, "query": str}]}"""


_STOP = set("a an the of in on for to and or is are was were be do does did have has had than then that this these "
             "those with without because why how what which who whom whether more less higher lower among between".split())


def keywords(text: str, n: int = 10) -> str:
    """Plain search words: OpenAlex treats ? and * as wildcards, and full sentences search poorly."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]+", text or "") if w.lower() not in _STOP]
    return " ".join(words[:n])


async def strategy(question: str) -> Dict[str, Any]:
    kw = keywords(question)
    fallback = {"framework": "concepts", "blocks": [], "queries": {"openalex": kw, "europepmc": kw},
                "adjacent_fields": [], "degraded": True}
    try:
        data = await call_json("librarian", STRATEGY_PROMPT, f"<question>{question}</question>", default={}) or {}
        q = data.get("queries") or {}
        if not (q.get("openalex") or q.get("europepmc")):
            return fallback
        data["queries"] = {"openalex": keywords(q.get("openalex") or kw, 12), "europepmc": q.get("europepmc") or q.get("openalex") or kw}
        data["adjacent_fields"] = (data.get("adjacent_fields") or [])[:2]
        return data
    except Exception as exc:
        logger.warning("[librarian] strategy fell back to the raw question: %s", sanitize_log_message(str(exc)))
        return fallback


# ---------------------------------------------------------------- search

def _abstract_from_inverted(idx: Optional[Dict[str, List[int]]]) -> str:
    if not idx:
        return ""
    words = sorted(((p, w) for w, ps in idx.items() for p in ps))
    return " ".join(w for _, w in words)


def _norm_title(t: str) -> str:
    return re.sub(r"\W+", "", (t or "").lower())[:90]


async def search_openalex(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        r = await client.get("https://api.openalex.org/works", params={
            "search": keywords(query, 12), "per-page": limit, "filter": "has_abstract:true,type:article|review",
            "select": "id,doi,title,publication_year,authorships,primary_location,abstract_inverted_index,open_access,best_oa_location,ids,cited_by_count,type",
        })
        r.raise_for_status()
        out = []
        for w in r.json().get("results", []):
            src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
            best = w.get("best_oa_location") or {}
            pmcid = ((w.get("ids") or {}).get("pmcid") or "").rsplit("/", 1)[-1] or None
            out.append({
                "title": w.get("title") or "", "year": w.get("publication_year"), "venue": src,
                "authors": [a["author"]["display_name"] for a in (w.get("authorships") or [])[:6] if a.get("author")],
                "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
                "abstract": _abstract_from_inverted(w.get("abstract_inverted_index")),
                "pmcid": pmcid, "oa_pdf": best.get("pdf_url"), "is_oa": (w.get("open_access") or {}).get("is_oa", False),
                "url": best.get("landing_page_url") or w.get("doi") or w.get("id"),
                "citations": w.get("cited_by_count"), "found_via": "OpenAlex",
            })
        return out
    except Exception as exc:
        logger.warning("[librarian] OpenAlex search failed: %s", sanitize_log_message(str(exc)))
        return []


_BOOL = {"and", "or", "not", "title_abs", "has_abstract"}


def _stems(text: str) -> set:
    """Five-letter stems of the content words (so "nurses"/"nursing" and "nurs*" meet)."""
    return {w.lower()[:5] for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text or "")
            if w.lower() not in _STOP and w.lower() not in _BOOL}


def on_topic(paper: Dict[str, Any], query: str) -> bool:
    """Title + abstract share at least two of the query's content words (one if the query has only one).
    Europe PMC matches words anywhere in the full text, which let in e.g. workplace-violence papers."""
    want = _stems(query)
    have = _stems(f"{paper.get('title', '')} {paper.get('abstract', '')}")
    return len(want & have) >= min(2, len(want))


async def search_europepmc(client: httpx.AsyncClient, query: str, limit: int, dropped: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    # Europe PMC orders by relevance by default; its `sort` parameter takes fields (e.g. "CITED desc"), and
    # "RELEVANCE" is rejected (checked 25 Oct 2026). Matching only titles and abstracts is what tightens it.
    try:
        r = await client.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params={
            "query": f"TITLE_ABS:({query}) AND HAS_ABSTRACT:Y", "format": "json", "resultType": "core", "pageSize": limit,
        })
        r.raise_for_status()
        out = []
        for p in r.json().get("resultList", {}).get("result", []):
            pmcid = p.get("pmcid")
            out.append({
                "title": (p.get("title") or "").rstrip("."), "year": int(p["pubYear"]) if str(p.get("pubYear", "")).isdigit() else None,
                "venue": (p.get("journalInfo") or {}).get("journal", {}).get("title") or p.get("journalTitle"),
                "authors": [a.strip() for a in (p.get("authorString") or "").split(",")[:6] if a.strip()],
                "doi": p.get("doi"), "abstract": re.sub(r"<[^>]+>", " ", p.get("abstractText") or "").strip(),
                "pmcid": pmcid, "oa_pdf": None, "is_oa": p.get("isOpenAccess") == "Y",
                "url": f"https://europepmc.org/article/{'PMC/' + pmcid if pmcid else (p.get('source', 'MED') + '/' + str(p.get('id')))}",
                "citations": p.get("citedByCount"), "found_via": "Europe PMC",
            })
        kept = [p for p in out if on_topic(p, query)]
        if dropped is not None:
            dropped.extend(p["title"] for p in out if p not in kept)
        return kept
    except Exception as exc:
        logger.warning("[librarian] Europe PMC search failed: %s", sanitize_log_message(str(exc)))
        return []


async def search(strat: Dict[str, Any], limit: int = 15, subclaims: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Both databases plus one OpenAlex query per sub-claim (so every link in the hypothesis gets witnesses),
    deduplicated by DOI and title, taken round-robin so no single query or source dominates."""
    per_sub = max(3, limit // max(1, len(subclaims or [])))
    dropped: List[str] = []
    async with httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True) as client:
        lists = list(await asyncio.gather(
            search_openalex(client, strat["queries"]["openalex"], limit),
            search_europepmc(client, strat["queries"]["europepmc"], limit, dropped),
            *[search_openalex(client, c, per_sub) for c in (subclaims or [])[:5]],
        ))
        if len(lists[1]) < 3:
            # A Boolean query that ANDs too many blocks returns almost nothing; relax to keywords.
            relaxed = keywords(strat["queries"]["openalex"], 8)
            lists[1] += await search_europepmc(client, relaxed, limit, dropped)
            strat["queries"]["europepmc_relaxed"] = relaxed
    # Recorded on the strategy so the trial (and the researcher) can see what was left out and why.
    strat["europepmc_dropped_off_topic"] = {"count": len(dropped), "titles": dropped[:10]}
    seen, merged = set(), []
    for i in range(max((len(l) for l in lists), default=0)):
        for l in lists:
            if i >= len(l) or not l[i]["title"]:
                continue
            p = l[i]
            keys = {k for k in (p.get("doi") and p["doi"].lower(), _norm_title(p["title"])) if k}
            if keys & seen:
                twin = next(m for m in merged if {m.get("doi") and m["doi"].lower(), _norm_title(m["title"])} & keys)
                twin["pmcid"] = twin.get("pmcid") or p.get("pmcid")
                twin["oa_pdf"] = twin.get("oa_pdf") or p.get("oa_pdf")
                twin["is_oa"] = twin.get("is_oa") or p.get("is_oa")
                continue
            seen |= keys
            merged.append(p)
    return merged[:limit]


async def adjacent_search(strat: Dict[str, Any], per_field: int = 4) -> Dict[str, Any]:
    """Titles and abstracts from adjacent fields, for the originality judgement (not read in full)."""
    fields = strat.get("adjacent_fields") or []
    if not fields:
        return {"ran": False, "fields": []}
    async with httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True) as client:
        results = await asyncio.gather(*[search_openalex(client, f.get("query") or f.get("field", ""), per_field) for f in fields])
    return {"ran": True, "fields": [{"field": f.get("field"), "why": f.get("why"), "query": f.get("query"),
                                     "papers": [{"title": p["title"], "year": p["year"], "abstract": p["abstract"][:500]} for p in res]}
                                    for f, res in zip(fields, results)]}


async def by_doi(doi: str) -> Optional[Dict[str, Any]]:
    """Look up one paper the user pasted (DOI, doi.org URL)."""
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I)
    async with httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True) as client:
        try:
            r = await client.get(f"https://api.openalex.org/works/doi:{doi}")
            r.raise_for_status()
            w = r.json()
        except Exception as exc:
            logger.info("[librarian] DOI lookup failed for %s: %s", doi, sanitize_log_message(str(exc)))
            return None
    best = w.get("best_oa_location") or {}
    return {
        "title": w.get("title") or doi, "year": w.get("publication_year"),
        "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "authors": [a["author"]["display_name"] for a in (w.get("authorships") or [])[:6] if a.get("author")],
        "doi": doi, "abstract": _abstract_from_inverted(w.get("abstract_inverted_index")),
        "pmcid": ((w.get("ids") or {}).get("pmcid") or "").rsplit("/", 1)[-1] or None,
        "oa_pdf": best.get("pdf_url"), "is_oa": (w.get("open_access") or {}).get("is_oa", False),
        "url": best.get("landing_page_url") or f"https://doi.org/{doi}", "citations": w.get("cited_by_count"),
        "found_via": "added by you",
    }


# ---------------------------------------------------------------- full text

def _xml_to_text(xml: str) -> str:
    body = xml.split("<body", 1)[-1] if "<body" in xml else xml
    body = re.sub(r"<title>(.*?)</title>", lambda m: f"\n\n## {m.group(1)}\n", body, flags=re.S)
    body = re.sub(r"<(table-wrap|ref-list|fig)[\s\S]*?</\1>", " ", body)
    text = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def pdf_to_text(data: bytes) -> str:
    from backend.ingestion import extract_text_from_pdf
    text, status, _pages, _trunc, _err = extract_text_from_pdf(data, max_pages=40, max_chars=MAX_TEXT_CHARS)
    return text if status != "failed" else ""


async def full_text(paper: Dict[str, Any]) -> Tuple[str, str, str]:
    """Returns (text, access, source). access ∈ full_text | abstract_only | metadata_only."""
    async with httpx.AsyncClient(timeout=25, headers=UA, follow_redirects=True) as client:
        if paper.get("pmcid"):
            try:
                r = await client.get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{paper['pmcid']}/fullTextXML")
                if r.status_code == 200 and "<body" in r.text:
                    text = _xml_to_text(r.text)
                    if len(text) > 2000:
                        return text[:MAX_TEXT_CHARS], "full_text", "PubMed Central (open access)"
            except Exception as exc:
                logger.info("[librarian] PMC full text failed: %s", sanitize_log_message(str(exc)))
        pdf_url = paper.get("oa_pdf")
        if not pdf_url and paper.get("arxiv_id"):
            pdf_url = f"https://arxiv.org/pdf/{paper['arxiv_id']}"
        if pdf_url:
            try:
                r = await client.get(pdf_url)
                if r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) <= MAX_PDF_BYTES:
                    text = pdf_to_text(r.content)
                    if len(text) > 2000:
                        return text, "full_text", "Open-access PDF"
            except Exception as exc:
                logger.info("[librarian] OA PDF failed: %s", sanitize_log_message(str(exc)))
    if paper.get("abstract"):
        return paper["abstract"], "abstract_only", "Abstract only (no legal open full text found)"
    return "", "metadata_only", "Title and metadata only"
