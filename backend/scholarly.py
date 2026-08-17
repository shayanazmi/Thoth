import os
import re
import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import httpx
from dotenv import load_dotenv

from backend.dispatcher import Dispatcher

load_dotenv()
logger = logging.getLogger("ThothScholarly")

# Module-level default dispatcher for academic API rate-limiting & resilience
scholarly_dispatcher = Dispatcher(
    max_concurrent=3,
    max_attempts=3,
    base_delay=1.0,
    max_consecutive_failures=5,
    cooloff_seconds=30.0
)


@dataclass
class SourceCandidate:
    """
    Unified dataclass representing an academic or web research candidate across all sources.
    """
    title: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    url: str = ""
    doi: Optional[str] = None
    citation_count: Optional[int] = None
    published_date: Optional[str] = None
    source_api: Optional[str] = None
    arxiv_id: Optional[str] = None

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
        }

    def to_formatted_snippet(self) -> str:
        """Formats the candidate into a clean Markdown / text snippet for LLM context."""
        authors_str = ", ".join(self.authors) if self.authors else "Unknown Authors"
        extra = []
        if self.published_date:
            extra.append(f"Published: {self.published_date}")
        if self.citation_count is not None:
            extra.append(f"Citations: {self.citation_count}")
        if self.doi:
            extra.append(f"DOI: {self.doi}")
        if self.arxiv_id:
            extra.append(f"arXiv: {self.arxiv_id}")
        if self.source_api:
            extra.append(f"Source: {self.source_api}")

        extra_str = f" ({' | '.join(extra)})" if extra else ""
        return (
            f"Title: {self.title}{extra_str}\n"
            f"Authors: {authors_str}\n"
            f"URL: {self.url}\n"
            f"Abstract / Snippet: {self.abstract[:600]}..."
        )


def _reconstruct_openalex_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    """Reconstructs text from OpenAlex's abstract_inverted_index format."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    words_by_pos = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words_by_pos[pos] = word
    sorted_positions = sorted(words_by_pos.keys())
    return " ".join(words_by_pos[pos] for pos in sorted_positions)


# ==============================================================================
# 1. arXiv API Client
# ==============================================================================

async def _fetch_arxiv_raw(query: str, max_results: int = 5) -> str:
    """Performs raw GET request to arXiv Atom XML API."""
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    headers = {"User-Agent": "Thoth-Academic-Researcher/1.0 (mailto:academic-research@thoth.ai)"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.text


def parse_arxiv_xml(xml_text: str) -> List[SourceCandidate]:
    """Parses arXiv Atom XML response into SourceCandidate objects."""
    candidates = []
    if not xml_text:
        return candidates

    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        for entry in root.findall("atom:entry", ns):
            title_elem = entry.find("atom:title", ns)
            title = re.sub(r"\s+", " ", title_elem.text.strip()) if title_elem is not None and title_elem.text else "Untitled"

            summary_elem = entry.find("atom:summary", ns)
            abstract = re.sub(r"\s+", " ", summary_elem.text.strip()) if summary_elem is not None and summary_elem.text else ""

            id_elem = entry.find("atom:id", ns)
            raw_id = id_elem.text.strip() if id_elem is not None and id_elem.text else ""

            # Extract arXiv ID (e.g. 2301.12345 or abs/2301.12345v1)
            arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

            # Locate PDF URL and entry URL
            pdf_url = ""
            entry_url = raw_id
            for link in entry.findall("atom:link", ns):
                rel = link.attrib.get("rel", "")
                title_attr = link.attrib.get("title", "")
                link_type = link.attrib.get("type", "")
                href = link.attrib.get("href", "")

                if title_attr == "pdf" or link_type == "application/pdf":
                    pdf_url = href
                elif rel == "alternate":
                    entry_url = href

            url = pdf_url if pdf_url else entry_url

            # Extract publication date
            published_elem = entry.find("atom:published", ns)
            published_date = published_elem.text.strip()[:10] if published_elem is not None and published_elem.text else None

            # Extract authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name_elem = author.find("atom:name", ns)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text.strip())

            # Extract DOI if present
            doi_elem = entry.find("arxiv:doi", ns)
            doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None

            candidates.append(
                SourceCandidate(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=url,
                    doi=doi,
                    citation_count=None,
                    published_date=published_date,
                    source_api="arxiv",
                    arxiv_id=arxiv_id,
                )
            )
    except Exception as e:
        logger.warning(f"[SCHOLARLY] Error parsing arXiv XML response: {e}")

    return candidates


async def search_arxiv(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches arXiv by query and returns a list of SourceCandidate objects.
    Routed through Dispatcher for concurrency and rate-limit control.
    """
    disp = dispatcher or scholarly_dispatcher
    try:
        xml_text = await disp.call(_fetch_arxiv_raw, query, max_results)
        return parse_arxiv_xml(xml_text)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] arXiv search failed for '{query}': {e}")
        return []


# ==============================================================================
# 2. Semantic Scholar API Client
# ==============================================================================

async def _fetch_semantic_scholar_raw(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Performs GET request to Semantic Scholar Paper Search Graph API."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,abstract,url,venue,year,citationCount,externalIds,publicationDate",
    }
    headers = {"User-Agent": "Thoth-Academic-Researcher/1.0"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def parse_semantic_scholar_json(data: Dict[str, Any]) -> List[SourceCandidate]:
    """Parses Semantic Scholar JSON response into SourceCandidate objects."""
    candidates = []
    if not data or not isinstance(data, dict):
        return candidates

    papers = data.get("data", [])
    for paper in papers:
        title = paper.get("title") or "Untitled"
        abstract = paper.get("abstract") or ""
        url = paper.get("url") or ""
        citation_count = paper.get("citationCount")
        published_date = paper.get("publicationDate") or str(paper.get("year") or "") or None

        authors = [a.get("name") for a in paper.get("authors", []) if a.get("name")]
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
            )
        )
    return candidates


async def search_semantic_scholar(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches Semantic Scholar by query and returns SourceCandidate objects.
    Gracefully handles public rate-limits (e.g. 429) returning empty list.
    """
    disp = dispatcher or scholarly_dispatcher
    try:
        json_data = await disp.call(_fetch_semantic_scholar_raw, query, max_results)
        return parse_semantic_scholar_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] Semantic Scholar search failed/rate-limited for '{query}': {e}")
        return []


# ==============================================================================
# 3. OpenAlex API Client (Public Scholarly Fallback / Companion)
# ==============================================================================

async def _fetch_openalex_raw(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Performs GET request to OpenAlex Works API."""
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
    """Parses OpenAlex JSON response into SourceCandidate objects."""
    candidates = []
    if not data or not isinstance(data, dict):
        return candidates

    works = data.get("results", [])
    for work in works:
        title = work.get("title") or "Untitled"
        abstract = _reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        doi = work.get("doi")
        citation_count = work.get("cited_by_count")
        published_date = work.get("publication_date")

        # Determine landing / source URL
        primary_loc = work.get("primary_location") or {}
        url = primary_loc.get("landing_page_url") or primary_loc.get("pdf_url") or doi or work.get("id") or ""

        # Extract authors
        authors = []
        for authorship in work.get("authorships", []):
            author_obj = authorship.get("author", {})
            name = author_obj.get("display_name")
            if name:
                authors.append(name)

        # Extract arXiv ID if present in ids dict
        ids_dict = work.get("ids", {})
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
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches OpenAlex by query and returns SourceCandidate objects.
    """
    disp = dispatcher or scholarly_dispatcher
    try:
        json_data = await disp.call(_fetch_openalex_raw, query, max_results)
        return parse_openalex_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] OpenAlex search failed for '{query}': {e}")
        return []


# ==============================================================================
# 4. Tavily Web Search Client (Unified Adapter)
# ==============================================================================

def _fetch_tavily_sync(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs synchronous search against Tavily API."""
    from tavily import TavilyClient
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    client = TavilyClient(api_key=api_key)
    res = client.search(query=query, search_depth="advanced", max_results=max_results)
    return res.get("results", [])


async def search_tavily(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches Tavily and returns results formatted as SourceCandidate objects.
    """
    disp = dispatcher or scholarly_dispatcher
    try:
        raw_results = await disp.call(_fetch_tavily_sync, query, max_results)
        candidates = []
        for r in raw_results:
            candidates.append(
                SourceCandidate(
                    title=r.get("title") or "Untitled Web Source",
                    authors=[],
                    abstract=r.get("content") or "",
                    url=r.get("url") or "",
                    doi=None,
                    citation_count=None,
                    published_date=None,
                    source_api="tavily",
                    arxiv_id=None,
                )
            )
        return candidates
    except Exception as e:
        logger.warning(f"[SCHOLARLY] Tavily search failed for '{query}': {e}")
        return []


# ==============================================================================
# 5. Unified Multi-Source Scholarly Search Aggregator
# ==============================================================================

async def search_scholarly_sources(
    query: str,
    max_results: int = 5,
    min_scholarly_results: int = 3,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches academic sources (arXiv, Semantic Scholar, OpenAlex) concurrently,
    deduplicates candidates, and falls back to Tavily web search if fewer than
    `min_scholarly_results` academic candidates are found.
    """
    disp = dispatcher or scholarly_dispatcher

    # Concurrently query academic endpoints
    academic_tasks = [
        search_arxiv(query, max_results=max_results, dispatcher=disp),
        search_semantic_scholar(query, max_results=max_results, dispatcher=disp),
        search_openalex(query, max_results=max_results, dispatcher=disp),
    ]

    results_lists = await asyncio.gather(*academic_tasks, return_exceptions=True)

    combined: List[SourceCandidate] = []
    for res in results_lists:
        if isinstance(res, list):
            combined.extend(res)

    # Deduplicate candidates based on normalized title or URL or DOI
    seen_keys = set()
    deduped_candidates: List[SourceCandidate] = []

    for candidate in combined:
        norm_title = re.sub(r"[^a-zA-Z0-9]", "", candidate.title.lower())
        key = candidate.doi or candidate.arxiv_id or norm_title or candidate.url
        if key and key not in seen_keys:
            seen_keys.add(key)
            deduped_candidates.append(candidate)

    # If insufficient academic results, fall back/supplement with Tavily web search
    if len(deduped_candidates) < min_scholarly_results:
        logger.info(f"[SCHOLARLY] Only {len(deduped_candidates)} academic results found. Supplementing with Tavily web search...")
        tavily_candidates = await search_tavily(query, max_results=max_results, dispatcher=disp)
        for cand in tavily_candidates:
            norm_title = re.sub(r"[^a-zA-Z0-9]", "", cand.title.lower())
            key = cand.url or norm_title
            if key and key not in seen_keys:
                seen_keys.add(key)
                deduped_candidates.append(cand)

    return deduped_candidates[:max_results]
