"""Citation following (vision §4.2, §6.1): the papers a seed cites (backward) and the papers that cite it
(forward). OpenAlex first; Semantic Scholar (backend/scholarly.py, rate-limited by its dispatcher) when OpenAlex
has no identifier for the seed, fails, or returns nothing. No model calls. Every call fails open and reports
what it did in `info`, so the caller can record the search honestly (including an off-topic filter's drops).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.agents import sanitize_log_message
from backend.research import librarian

logger = logging.getLogger("ThothCitations")

OPENALEX = "https://api.openalex.org"
_OA_SLOTS = asyncio.Semaphore(3)
BATCH = 50

FOUND_VIA = {
    ("backward", "OpenAlex"): "Citation search: reference of a screened paper (OpenAlex)",
    ("backward", "Semantic Scholar"): "Citation search: reference of a screened paper (Semantic Scholar)",
    ("forward", "OpenAlex"): "Citation search: cites a screened paper (OpenAlex)",
    ("forward", "Semantic Scholar"): "Citation search: cites a screened paper (Semantic Scholar)",
}


def _info() -> Dict[str, Any]:
    return {"provider": None, "requested": 0, "returned": 0, "removed_offtopic": 0, "total_available": None, "error": None}


def _err(exc: Exception) -> str:
    return sanitize_log_message(str(exc))[:200]


async def _get(client: httpx.AsyncClient, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    async with _OA_SLOTS:
        r = await librarian.openalex_get(client, f"{OPENALEX}{path}", params or {})
        r.raise_for_status()
        return r.json()


async def resolve_openalex_id(client: httpx.AsyncClient, meta: Dict[str, Any]) -> str:
    oid = librarian.norm_openalex(meta.get("openalex_id"))
    if oid:
        return oid
    doi = librarian.norm_doi(meta.get("doi"))
    if not doi:
        return ""
    try:
        return librarian.norm_openalex((await _get(client, f"/works/doi:{doi}", {"select": "id"})).get("id"))
    except Exception as exc:
        logger.info("[citations] no OpenAlex id for %s: %s", doi, _err(exc))
        return ""


def _s2_id(meta: Dict[str, Any]) -> str:
    return librarian.norm_doi(meta.get("doi")) or str(meta.get("s2_id") or "")


def _filter(papers: List[Dict[str, Any]], query: str, info: Dict[str, Any], need: int = 2) -> List[Dict[str, Any]]:
    if not query:
        return papers
    kept = [p for p in papers if librarian.on_topic(p, query, need)]
    info["removed_offtopic"] += len(papers) - len(kept)
    return kept


def _tag(papers: List[Dict[str, Any]], kind: str, provider: str) -> List[Dict[str, Any]]:
    for p in papers:
        p["found_via"] = FOUND_VIA[(kind, provider)]
    return [p for p in papers if p.get("title")]


async def _s2(kind: str, meta: Dict[str, Any], limit: int, info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Semantic Scholar references or citations (librarian.s2_get: rate-limited; a spent key falls back to the
    anonymous pool). Errors are recorded, so a rate limit is never mistaken for "no papers"."""
    sid = _s2_id(meta)
    if not sid:
        return []
    from backend.scholarly import _normalize_s2_id
    path = f"/paper/{_normalize_s2_id(sid)}/{'references' if kind == 'backward' else 'citations'}"
    try:
        data = await librarian.s2_get(path, {"fields": librarian.S2_FIELDS, "limit": limit})
    except Exception as exc:
        info["error"] = "; ".join(x for x in (info.get("error") and f"OpenAlex: {info['error']}", f"Semantic Scholar: {_err(exc)}") if x)
        return []
    key = "citedPaper" if kind == "backward" else "citingPaper"
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        info["error"] = info.get("error") or "Semantic Scholar returned no data"
        return []
    info["provider"] = "Semantic Scholar"
    return [librarian.s2_meta(x.get(key) or {}, FOUND_VIA[(kind, "Semantic Scholar")]) for x in items if isinstance(x, dict)]


async def backward(client: httpx.AsyncClient, meta: Dict[str, Any], limit: int, query: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Up to `limit` works in the seed's reference list."""
    info, papers = _info(), []
    info["requested"] = limit
    wid = await resolve_openalex_id(client, meta)
    if wid:
        try:
            refs = [librarian.norm_openalex(x) for x in (await _get(client, f"/works/{wid}", {"select": "referenced_works"})).get("referenced_works") or []]
            refs = [r for r in refs if r]
            info["total_available"] = len(refs)
            for i in range(0, min(limit, len(refs)), BATCH):
                chunk = refs[i:min(i + BATCH, limit)]
                data = await _get(client, "/works", {"filter": f"openalex:{'|'.join(chunk)}", "per-page": BATCH,
                                                     "select": librarian.OPENALEX_SELECT})
                papers += [librarian._openalex_meta(w) for w in data.get("results", [])]
            info["provider"] = "OpenAlex"
        except Exception as exc:
            info["error"] = _err(exc)
            papers = []
    if not papers:
        papers = await _s2("backward", meta, limit, info)
    elif not info["provider"]:
        info["provider"] = "OpenAlex"
    if not papers and not wid and not _s2_id(meta):
        info["error"] = info["error"] or "no identifier"
    papers = _tag(papers, "backward", info["provider"] or "OpenAlex")
    # One shared word is enough for a seed's own references; the Screener judges relevance (and is logged).
    papers = _filter(papers, query, info, need=1)
    info["returned"] = len(papers)
    return papers, info


async def forward(client: httpx.AsyncClient, meta: Dict[str, Any], limit: int, query: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Up to `limit` works that cite the seed, ranked by OpenAlex relevance to the query."""
    info, papers = _info(), []
    info["requested"] = limit
    wid = await resolve_openalex_id(client, meta)
    if wid:
        try:
            params = {"filter": f"cites:{wid},has_abstract:true", "per-page": limit, "select": librarian.OPENALEX_SELECT}
            if query:
                params["search"] = librarian.keywords(query, 8)
            data = await _get(client, "/works", params)
            info["total_available"] = (data.get("meta") or {}).get("count")
            papers = [librarian._openalex_meta(w) for w in data.get("results", [])]
            info["provider"] = "OpenAlex"
        except Exception as exc:
            info["error"] = _err(exc)
            papers = []
    if not papers:
        papers = await _s2("forward", meta, limit, info)
        # Semantic Scholar does not rank citing papers by topic; the off-topic filter does that (and is counted).
    if not papers and not wid and not _s2_id(meta):
        info["error"] = info["error"] or "no identifier"
    papers = _tag(papers, "forward", info["provider"] or "OpenAlex")
    if info["provider"] == "Semantic Scholar":  # OpenAlex already searched within the citing works
        papers = _filter(papers, query, info)
    info["returned"] = len(papers)
    return papers, info
