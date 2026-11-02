# Thoth · Developed by Shayan Azmi
import os
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import httpx
from dotenv import load_dotenv

from backend.dispatcher import Dispatcher, scholarly_dispatcher, s2_dispatcher

load_dotenv()
logger = logging.getLogger("ThothScholarly")

@dataclass
class SourceCandidate:
    title: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    url: str = ""
    doi: Optional[str] = None
    citation_count: Optional[int] = None
    published_date: Optional[str] = None
    source_api: Optional[str] = None
    arxiv_id: Optional[str] = None
    paper_id: Optional[str] = None
    relation: Optional[str] = None
    pmid: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "url": self.url,
            "doi": self.doi,
            "citation_count": self.citation_count,
            "published_date": self.published_date,
            "source_api": self.source_api,
            "arxiv_id": self.arxiv_id,
            "paper_id": self.paper_id,
            "relation": self.relation,
            "pmid": self.pmid,
        }


def _reconstruct_openalex_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    words_by_pos = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words_by_pos[pos] = word
    sorted_positions = sorted(words_by_pos.keys())
    return " ".join(words_by_pos[pos] for pos in sorted_positions)


def _get_s2_headers() -> Dict[str, str]:
    headers = {"User-Agent": "Thoth-Academic-Researcher/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    return headers

async def _fetch_semantic_scholar_raw(query: str, max_results: int = 15) -> Dict[str, Any]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,abstract,url,venue,year,citationCount,externalIds,publicationDate,paperId",
    }
    headers = _get_s2_headers()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

def parse_semantic_scholar_json(data: Dict[str, Any]) -> List[SourceCandidate]:
    candidates = []
    if not data or not isinstance(data, dict):
        return candidates

    papers = data.get("data") or []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        title = paper.get("title") or "Untitled"
        abstract = paper.get("abstract") or ""
        url = paper.get("url") or ""
        citation_count = paper.get("citationCount")
        published_date = paper.get("publicationDate") or str(paper.get("year") or "") or None
        paper_id = paper.get("paperId")

        authors = [a.get("name") for a in (paper.get("authors") or []) if isinstance(a, dict) and a.get("name")]
        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")

        if not url and arxiv_id:
            url = f"https://arxiv.org/abs/{arxiv_id}"

        candidates.append(
            SourceCandidate(
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                doi=doi,
                citation_count=citation_count,
                published_date=published_date,
                source_api="semantic_scholar",
                arxiv_id=arxiv_id,
                paper_id=paper_id,
            )
        )
    return candidates

async def search_semantic_scholar(
    query: str,
    max_results: int = 15,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    disp = dispatcher or s2_dispatcher
    try:
        json_data = await disp.call(_fetch_semantic_scholar_raw, query, max_results)
        return parse_semantic_scholar_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] Semantic Scholar search failed/rate-limited for '{query}': {e}")
        return []

def _normalize_s2_id(pid: str) -> str:
    p = str(pid).strip()
    if not p:
        return ""
    if p.isdigit():
        return f"CorpusId:{p}"
    if p.startswith("10."):
        return f"DOI:{p}"
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", p):
        return f"ARXIV:{p}"
    if p.lower().startswith("arxiv:"):
        return f"ARXIV:{p[6:].strip()}"
    if p.lower().startswith("doi:"):
        return f"DOI:{p[4:].strip()}"
    return p


async def _fetch_openalex_raw(query: str, max_results: int = 15) -> Dict[str, Any]:
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per_page": max_results,
    }
    headers = {"User-Agent": "Thoth-Academic-Researcher/1.0 (mailto:academic-research@thoth.ai)"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

def parse_openalex_json(data: Dict[str, Any]) -> List[SourceCandidate]:
    candidates = []
    if not data or not isinstance(data, dict):
        return candidates

    works = data.get("results") or []
    for work in works:
        if not isinstance(work, dict):
            continue
        title = work.get("title") or "Untitled"
        abstract = _reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        doi = work.get("doi")
        citation_count = work.get("cited_by_count")
        published_date = work.get("publication_date")

        primary_loc = work.get("primary_location") or {}
        url = primary_loc.get("landing_page_url") or primary_loc.get("pdf_url") or doi or work.get("id") or ""

        authors = []
        for authorship in (work.get("authorships") or []):
            if isinstance(authorship, dict):
                author_obj = authorship.get("author") or {}
                name = author_obj.get("display_name")
                if name:
                    authors.append(name)

        ids_dict = work.get("ids") or {}
        arxiv_url = ids_dict.get("arxiv")
        arxiv_id = arxiv_url.split("/")[-1] if arxiv_url else None

        candidates.append(
            SourceCandidate(
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                doi=doi,
                citation_count=citation_count,
                published_date=published_date,
                source_api="openalex",
                arxiv_id=arxiv_id,
            )
        )
    return candidates

async def search_openalex(
    query: str,
    max_results: int = 15,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    disp = dispatcher or scholarly_dispatcher
    try:
        json_data = await disp.call(_fetch_openalex_raw, query, max_results)
        return parse_openalex_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] OpenAlex search failed for '{query}': {e}")
        return []

async def _fetch_europepmc_raw(query: str, max_results: int = 15) -> Dict[str, Any]:
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    clean_query = f"{query} AND OPEN_ACCESS:y"
    params = {
        "query": clean_query,
        "format": "json",
        "pageSize": max_results,
        "resultType": "core",
    }
    headers = {"User-Agent": "Thoth-Academic-Researcher/1.0"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

def parse_europepmc_json(data: Dict[str, Any]) -> List[SourceCandidate]:
    candidates = []
    if not data or not isinstance(data, dict):
        return candidates

    results = data.get("resultList", {}).get("result", [])
    for paper in results:
        if not isinstance(paper, dict):
            continue
        title = paper.get("title") or "Untitled"
        abstract = paper.get("abstractText") or ""
        doi = paper.get("doi")
        citation_count = paper.get("citedByCount")
        pub_year = paper.get("pubYear")
        pmcid = paper.get("pmcid")
        pmid = paper.get("id")

        url = f"https://europepmc.org/article/MED/{pmid}" if pmid else ""
        if pmcid:
            url = f"https://europepmc.org/article/PMC/{pmcid}"

        author_str = paper.get("authorString") or ""
        authors = [a.strip() for a in author_str.split(",") if a.strip()]

        candidates.append(
            SourceCandidate(
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                doi=f"https://doi.org/{doi}" if doi and not doi.startswith("http") else doi,
                citation_count=citation_count,
                published_date=str(pub_year) if pub_year else None,
                source_api="europe_pmc",
            )
        )
    return candidates

async def search_europepmc(
    query: str,
    max_results: int = 15,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    disp = dispatcher or scholarly_dispatcher
    try:
        json_data = await disp.call(_fetch_europepmc_raw, query, max_results)
        return parse_europepmc_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] Europe PMC search failed for '{query}': {e}")
        return []


