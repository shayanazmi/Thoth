import os
import re
import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import httpx
from dotenv import load_dotenv

from backend.dispatcher import Dispatcher, scholarly_dispatcher, s2_dispatcher
from backend.telemetry import observe

load_dotenv()
logger = logging.getLogger("ThothScholarly")


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
    paper_id: Optional[str] = None
    relation: Optional[str] = None

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
        }

    def to_formatted_snippet(self) -> str:
        """Formats the candidate into a clean Markdown / text snippet for LLM context."""
        authors_str = ", ".join(self.authors) if self.authors else "Unknown Authors"
        extra = []
        if self.relation:
            extra.append(f"Relation: {self.relation}")
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

            # Extract arXiv ID
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


@observe(type="tool", description="Searches arXiv repository for academic preprints and papers")
async def search_arxiv(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches arXiv by query and returns a list of SourceCandidate objects.
    """
    disp = dispatcher or scholarly_dispatcher
    try:
        xml_text = await disp.call(_fetch_arxiv_raw, query, max_results)
        return parse_arxiv_xml(xml_text)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] arXiv search failed for '{query}': {e}")
        return []


# ==============================================================================
# 2. Semantic Scholar API Client & Advanced Graph Tools
# ==============================================================================

def _get_s2_headers() -> Dict[str, str]:
    """Returns headers with Semantic Scholar API key if configured."""
    headers = {"User-Agent": "Thoth-Academic-Researcher/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    return headers


async def _fetch_semantic_scholar_raw(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Performs GET request to Semantic Scholar Paper Search Graph API."""
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
    """Parses Semantic Scholar JSON response into SourceCandidate objects."""
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


@observe(type="tool", description="Queries Semantic Scholar Academic Graph API for peer-reviewed papers")
async def search_semantic_scholar(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches Semantic Scholar by query and returns SourceCandidate objects.
    Routed through s2_dispatcher with strict 1 req/sec pacing.
    """
    disp = dispatcher or s2_dispatcher
    try:
        json_data = await disp.call(_fetch_semantic_scholar_raw, query, max_results)
        return parse_semantic_scholar_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] Semantic Scholar search failed/rate-limited for '{query}': {e}")
        return []


def _normalize_s2_id(pid: str) -> str:
    """Normalizes raw IDs for S2 API endpoints (e.g. adding CorpusId: prefix to bare integers)."""
    p = str(pid).strip()
    if p.isdigit():
        return f"CorpusId:{p}"
    return p


async def _fetch_s2_recommendations_raw(positive_ids: List[str], negative_ids: List[str], limit: int = 5) -> Dict[str, Any]:
    """Performs POST request to S2 Recommendations API."""
    url = "https://api.semanticscholar.org/recommendations/v1/papers"
    params = {
        "fields": "title,authors,abstract,url,venue,year,citationCount,externalIds,publicationDate,paperId",
        "limit": limit,
    }
    body = {
        "positivePaperIds": [_normalize_s2_id(p) for p in positive_ids],
        "negativePaperIds": [_normalize_s2_id(p) for p in negative_ids],
    }
    headers = _get_s2_headers()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, params=params, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()


@observe(type="tool", description="Fetches neural paper recommendations based on positive/negative seed papers")
async def get_paper_recommendations(
    positive_paper_ids: List[str],
    negative_paper_ids: Optional[List[str]] = None,
    limit: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Recommends papers given a list of positive and optional negative seed paper IDs.
    """
    if not positive_paper_ids:
        return []
    neg_ids = negative_paper_ids or []
    disp = dispatcher or s2_dispatcher
    try:
        json_data = await disp.call(_fetch_s2_recommendations_raw, positive_paper_ids, neg_ids, limit)
        recommended = json_data.get("recommendedPapers", [])
        candidates = []
        for paper in recommended:
            authors = [a.get("name") for a in (paper.get("authors") or []) if isinstance(a, dict) and a.get("name")]
            ext_ids = paper.get("externalIds") or {}
            candidates.append(
                SourceCandidate(
                    title=paper.get("title") or "Untitled",
                    authors=authors,
                    abstract=paper.get("abstract") or "",
                    url=paper.get("url") or "",
                    doi=ext_ids.get("DOI"),
                    citation_count=paper.get("citationCount"),
                    published_date=paper.get("publicationDate") or str(paper.get("year") or "") or None,
                    source_api="semantic_scholar_recommendations",
                    arxiv_id=ext_ids.get("ArXiv"),
                    paper_id=paper.get("paperId"),
                    relation="recommended",
                )
            )
        return candidates
    except Exception as e:
        logger.warning(f"[SCHOLARLY] S2 recommendations failed: {e}")
        return []


async def _fetch_s2_citations_raw(paper_id: str, limit: int = 5) -> Dict[str, Any]:
    """Fetches citing papers for a given paper ID from S2."""
    norm_id = _normalize_s2_id(paper_id)
    url = f"https://api.semanticscholar.org/graph/v1/paper/{norm_id}/citations"
    params = {
        "fields": "title,authors,abstract,url,venue,year,citationCount,externalIds,publicationDate,paperId",
        "limit": limit,
    }
    headers = _get_s2_headers()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


@observe(type="tool", description="Fetches papers that cite the specified seed paper")
async def get_paper_citations(
    paper_id: str,
    limit: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """Retrieves forward citation descendants for a paper."""
    disp = dispatcher or s2_dispatcher
    try:
        json_data = await disp.call(_fetch_s2_citations_raw, paper_id, limit)
        data = json_data.get("data", [])
        candidates = []
        for item in data:
            citing_paper = item.get("citingPaper") or {}
            if not citing_paper.get("title"):
                continue
            ext_ids = citing_paper.get("externalIds") or {}
            authors = [a.get("name") for a in (citing_paper.get("authors") or []) if isinstance(a, dict) and a.get("name")]
            candidates.append(
                SourceCandidate(
                    title=citing_paper.get("title") or "Untitled",
                    authors=authors,
                    abstract=citing_paper.get("abstract") or "",
                    url=citing_paper.get("url") or "",
                    doi=ext_ids.get("DOI"),
                    citation_count=citing_paper.get("citationCount"),
                    published_date=citing_paper.get("publicationDate") or str(citing_paper.get("year") or "") or None,
                    source_api="semantic_scholar_citations",
                    arxiv_id=ext_ids.get("ArXiv"),
                    paper_id=citing_paper.get("paperId"),
                    relation="cites_seed",
                )
            )
        return candidates
    except Exception as e:
        logger.warning(f"[SCHOLARLY] S2 citations failed for {paper_id}: {e}")
        return []


async def _fetch_s2_references_raw(paper_id: str, limit: int = 5) -> Dict[str, Any]:
    """Fetches cited papers (bibliography) for a given paper ID from S2."""
    norm_id = _normalize_s2_id(paper_id)
    url = f"https://api.semanticscholar.org/graph/v1/paper/{norm_id}/references"
    params = {
        "fields": "title,authors,abstract,url,venue,year,citationCount,externalIds,publicationDate,paperId",
        "limit": limit,
    }
    headers = _get_s2_headers()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()



@observe(type="tool", description="Fetches papers cited in the bibliography of the specified seed paper")
async def get_paper_references(
    paper_id: str,
    limit: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """Retrieves backward references (foundational bibliography) for a paper."""
    disp = dispatcher or s2_dispatcher
    try:
        json_data = await disp.call(_fetch_s2_references_raw, paper_id, limit)
        data = json_data.get("data", [])
        candidates = []
        for item in data:
            cited_paper = item.get("citedPaper") or {}
            if not cited_paper.get("title"):
                continue
            ext_ids = cited_paper.get("externalIds") or {}
            authors = [a.get("name") for a in (cited_paper.get("authors") or []) if isinstance(a, dict) and a.get("name")]
            candidates.append(
                SourceCandidate(
                    title=cited_paper.get("title") or "Untitled",
                    authors=authors,
                    abstract=cited_paper.get("abstract") or "",
                    url=cited_paper.get("url") or "",
                    doi=ext_ids.get("DOI"),
                    citation_count=cited_paper.get("citationCount"),
                    published_date=cited_paper.get("publicationDate") or str(cited_paper.get("year") or "") or None,
                    source_api="semantic_scholar_references",
                    arxiv_id=ext_ids.get("ArXiv"),
                    paper_id=cited_paper.get("paperId"),
                    relation="reference_of_seed",
                )
            )
        return candidates
    except Exception as e:
        logger.warning(f"[SCHOLARLY] S2 references failed for {paper_id}: {e}")
        return []


async def _fetch_s2_snippets_raw(query: str, limit: int = 5) -> Dict[str, Any]:
    """Performs GET request to S2 snippet search endpoint for full-text passages."""
    url = "https://api.semanticscholar.org/graph/v1/snippet/search"
    params = {
        "query": query,
        "limit": limit,
    }
    headers = _get_s2_headers()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


@observe(type="tool", description="Searches 500-word full-text excerpt snippets from academic papers")
async def search_paper_snippets(
    query: str,
    limit: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Searches ~500-word full-text passages from papers to verify specific factual claims.
    """
    disp = dispatcher or s2_dispatcher
    try:
        json_data = await disp.call(_fetch_s2_snippets_raw, query, limit)
        snippets = json_data.get("data", [])
        candidates = []
        for item in snippets:
            snippet_obj = item.get("snippet") or {}
            snippet_text = snippet_obj.get("text") or ""
            paper = item.get("paper") or {}
            corpus_id = paper.get("corpusId")
            authors_raw = paper.get("authors") or []
            authors = [a if isinstance(a, str) else a.get("name", "") for a in authors_raw if a]
            oa_info = paper.get("openAccessInfo") or {}
            disclaimer = oa_info.get("disclaimer") or ""
            url_match = re.search(r"https?://\S+", disclaimer)
            url = url_match.group(0).rstrip(",.") if url_match else ""

            candidates.append(
                SourceCandidate(
                    title=paper.get("title") or "Academic Excerpt",
                    authors=authors,
                    abstract=snippet_text,
                    url=url,
                    doi=None,
                    citation_count=None,
                    published_date=None,
                    source_api="semantic_scholar_snippet",
                    arxiv_id=None,
                    paper_id=corpus_id,
                    relation="snippet_match",
                )
            )
        return candidates
    except Exception as e:
        logger.warning(f"[SCHOLARLY] S2 snippet search failed for '{query}': {e}")
        return []



# ==============================================================================
# 3. OpenAlex API Client
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


@observe(type="tool", description="Queries OpenAlex global scholarly corpus for research publications")
async def search_openalex(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """Searches OpenAlex by query and returns SourceCandidate objects."""
    disp = dispatcher or scholarly_dispatcher
    try:
        json_data = await disp.call(_fetch_openalex_raw, query, max_results)
        return parse_openalex_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] OpenAlex search failed for '{query}': {e}")
        return []


# ==============================================================================
# 4. Europe PMC API Client
# ==============================================================================

async def _fetch_europepmc_raw(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Performs GET request to Europe PMC REST API (Open Access filter enabled)."""
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
    """Parses Europe PMC JSON response into SourceCandidate objects."""
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


@observe(type="tool", description="Queries Europe PMC database for open-access scientific publications")
async def search_europepmc(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """Searches Europe PMC for open-access papers."""
    disp = dispatcher or scholarly_dispatcher
    try:
        json_data = await disp.call(_fetch_europepmc_raw, query, max_results)
        return parse_europepmc_json(json_data)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] Europe PMC search failed for '{query}': {e}")
        return []


# ==============================================================================
# 5. PubMed NCBI API Client
# ==============================================================================

async def _fetch_pubmed_raw(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs ESearch followed by ESummary on NCBI Entrez API."""
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results,
    }
    headers = {"User-Agent": "Thoth-Academic-Researcher/1.0 (mailto:academic-research@thoth.ai)"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        search_resp = await client.get(search_url, params=search_params, headers=headers)
        search_resp.raise_for_status()
        id_list = search_resp.json().get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return []

        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        summary_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json",
        }
        sum_resp = await client.get(summary_url, params=summary_params, headers=headers)
        sum_resp.raise_for_status()
        res_data = sum_resp.json().get("result", {})

        papers = []
        for uid in id_list:
            item = res_data.get(uid)
            if item and isinstance(item, dict):
                papers.append(item)
        return papers


def parse_pubmed_json(results: List[Dict[str, Any]]) -> List[SourceCandidate]:
    """Parses PubMed ESummary JSON into SourceCandidate objects."""
    candidates = []
    for paper in results:
        title = paper.get("title") or "Untitled"
        uid = paper.get("uid") or ""
        url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/" if uid else ""
        pub_date = paper.get("pubdate") or paper.get("sortpubdate", "")[:10] or None

        authors = [a.get("name", "") for a in (paper.get("authors") or []) if isinstance(a, dict) and a.get("name")]

        doi = None
        for art_id in (paper.get("articleids") or []):
            if isinstance(art_id, dict) and art_id.get("idtype") == "doi":
                doi_val = art_id.get("value")
                doi = f"https://doi.org/{doi_val}" if doi_val else None

        source_venue = paper.get("source") or ""
        abstract = f"Published in {source_venue} ({pub_date}). PMID: {uid}"

        candidates.append(
            SourceCandidate(
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                doi=doi,
                citation_count=None,
                published_date=pub_date,
                source_api="pubmed",
            )
        )
    return candidates


@observe(type="tool", description="Queries PubMed database for biomedical and clinical literature")
async def search_pubmed(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """Searches PubMed via NCBI Entrez."""
    disp = dispatcher or scholarly_dispatcher
    try:
        raw_items = await disp.call(_fetch_pubmed_raw, query, max_results)
        return parse_pubmed_json(raw_items)
    except Exception as e:
        logger.warning(f"[SCHOLARLY] PubMed search failed for '{query}': {e}")
        return []


# ==============================================================================
# 6. Literature Snowballing Engine
# ==============================================================================

@observe(type="tool", description="Snowballs academic literature via citation traversal and neural recommendations")
async def snowball_literature_graph(
    seed_candidates: List[SourceCandidate],
    max_recommendations: int = 3,
    max_citations: int = 3,
    max_references: int = 2,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """
    Expands seed research papers into a deeper literature graph using:
    1. Neural Recommendations based on top seed paper IDs.
    2. Forward Citations (subsequent papers citing seeds).
    3. Backward References (foundational papers in seeds' bibliographies).
    """
    disp = dispatcher or s2_dispatcher
    seed_paper_ids = [s.paper_id for s in seed_candidates if s.paper_id]
    if not seed_paper_ids:
        return []

    logger.info(f"[SNOWBALL] Expanding literature graph for {len(seed_paper_ids)} seed paper IDs...")
    print(f"\n[INFO] [SNOWBALL] Expanding literature graph from {len(seed_paper_ids)} seed papers...")

    tasks = []
    # 1. Recommendations task
    tasks.append(get_paper_recommendations(seed_paper_ids[:3], limit=max_recommendations, dispatcher=disp))

    # 2. Citations & References for top 2 seeds
    for pid in seed_paper_ids[:2]:
        tasks.append(get_paper_citations(pid, limit=max_citations, dispatcher=disp))
        tasks.append(get_paper_references(pid, limit=max_references, dispatcher=disp))

    results_lists = await asyncio.gather(*tasks, return_exceptions=True)

    snowballed_candidates: List[SourceCandidate] = []
    seen_keys = {re.sub(r"[^a-zA-Z0-9]", "", s.title.lower()) for s in seed_candidates}

    for res in results_lists:
        if isinstance(res, list):
            for cand in res:
                norm_title = re.sub(r"[^a-zA-Z0-9]", "", cand.title.lower())
                key = cand.doi or cand.arxiv_id or cand.paper_id or norm_title
                if key and norm_title not in seen_keys:
                    seen_keys.add(norm_title)
                    snowballed_candidates.append(cand)

    # Multi-Corpus Fallback: If S2 returned no connected candidates (e.g. rate-limited), query OpenAlex related works
    if not snowballed_candidates:
        logger.info("[SNOWBALL] S2 returned 0 connected papers. Attempting OpenAlex related works fallback...")
        openalex_fallback = await _snowball_openalex_fallback(seed_candidates, limit=max_recommendations)
        for cand in openalex_fallback:
            norm_title = re.sub(r"[^a-zA-Z0-9]", "", cand.title.lower())
            if norm_title not in seen_keys:
                seen_keys.add(norm_title)
                snowballed_candidates.append(cand)

    logger.info(f"[SNOWBALL] Discovered {len(snowballed_candidates)} connected papers through citation & recommendation graph.")
    print(f"[INFO] [SNOWBALL] Discovered {len(snowballed_candidates)} connected papers.")
    return snowballed_candidates


async def _snowball_openalex_fallback(seeds: List[SourceCandidate], limit: int = 3) -> List[SourceCandidate]:
    """Fallback snowballing using OpenAlex related works when S2 is rate-limited."""
    candidates: List[SourceCandidate] = []
    headers = {"User-Agent": "Thoth-Academic-Snowballer/1.0"}
    async with httpx.AsyncClient(timeout=12.0) as client:
        for seed in seeds[:2]:
            query = seed.doi or seed.title
            if not query:
                continue
            try:
                r = await client.get("https://api.openalex.org/works", params={"search": query, "per-page": 1}, headers=headers)
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    if results:
                        related_urls = results[0].get("related_works", [])[:limit]
                        for r_url in related_urls:
                            rw_res = await client.get(r_url, headers=headers)
                            if rw_res.status_code == 200:
                                parsed = parse_openalex_json({"results": [rw_res.json()]})
                                for p in parsed:
                                    p.relation = "recommended"
                                    candidates.extend(parsed)
            except Exception as e:
                logger.debug(f"[SNOWBALL FALLBACK] OpenAlex fallback failed for {query}: {e}")
    return candidates



# ==============================================================================
# 7. Tavily Web Search Client (Fallback Adapter)
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


@observe(type="tool", description="Queries Tavily search engine for recent web intelligence and fallback discovery")
async def search_tavily(
    query: str,
    max_results: int = 5,
    dispatcher: Optional[Dispatcher] = None
) -> List[SourceCandidate]:
    """Searches Tavily and returns results formatted as SourceCandidate objects."""
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


def _sanitize_academic_query(query: str, max_chars: int = 150) -> str:
    """
    Sanitizes raw user/agent queries for academic APIs (arXiv, S2, EuropePMC, PubMed, OpenAlex).
    Removes multiline report dumps, parenthetical instructions, quotes, and cleans excess whitespace.
    """
    if not query:
        return ""
    # If multiline or paragraph, take first substantive line
    lines = [line.strip() for line in query.splitlines() if line.strip()]
    cleaned = lines[0] if lines else query
    
    # Remove outer quotes and markdown symbols
    cleaned = re.sub(r'[\r\n\t]+', ' ', cleaned)
    cleaned = re.sub(r'[#*`_~\[\](){}<>]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # If still too long, extract primary key clause
    if len(cleaned) > max_chars:
        parts = re.split(r'[\.;\?!]', cleaned)
        if parts and len(parts[0].strip()) >= 15:
            cleaned = parts[0].strip()
        else:
            cleaned = cleaned[:max_chars].rsplit(' ', 1)[0]
    return cleaned.strip()


# ==============================================================================
# 8. Unified Multi-Source Scholarly Search Aggregator
# ==============================================================================

async def search_scholarly_sources(
    query: str,
    max_results: int = 5,
    min_scholarly_results: int = 3,
    dispatcher: Optional[Dispatcher] = None,
    enable_snowball: bool = False
) -> List[SourceCandidate]:
    """
    Federates search across academic sources (arXiv, Semantic Scholar, OpenAlex, Europe PMC, PubMed)
    concurrently, deduplicates candidates, optionally snowballs citation graph, and falls back to
    Tavily web search if fewer than `min_scholarly_results` academic candidates are found.
    """
    disp = dispatcher or scholarly_dispatcher
    clean_query = _sanitize_academic_query(query)
    if not clean_query:
        clean_query = query[:100]

    # Concurrently query all federated academic endpoints
    academic_tasks = [
        search_arxiv(clean_query, max_results=max_results, dispatcher=disp),
        search_semantic_scholar(clean_query, max_results=max_results, dispatcher=s2_dispatcher),
        search_openalex(clean_query, max_results=max_results, dispatcher=disp),
        search_europepmc(clean_query, max_results=max_results, dispatcher=disp),
        search_pubmed(clean_query, max_results=max_results, dispatcher=disp),
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
        key = candidate.doi or candidate.arxiv_id or candidate.paper_id or norm_title or candidate.url
        if key and norm_title not in seen_keys:
            seen_keys.add(norm_title)
            deduped_candidates.append(candidate)

    # Optional Snowballing
    if enable_snowball and deduped_candidates:
        snowballed = await snowball_literature_graph(deduped_candidates[:3], dispatcher=s2_dispatcher)
        for cand in snowballed:
            norm_title = re.sub(r"[^a-zA-Z0-9]", "", cand.title.lower())
            if norm_title not in seen_keys:
                seen_keys.add(norm_title)
                deduped_candidates.append(cand)

    # If insufficient academic results, fall back/supplement with Tavily web search
    if len(deduped_candidates) < min_scholarly_results:
        logger.info(f"[SCHOLARLY] Only {len(deduped_candidates)} academic results found. Supplementing with Tavily web search...")
        tavily_candidates = await search_tavily(query, max_results=max_results, dispatcher=disp)
        for cand in tavily_candidates:
            norm_title = re.sub(r"[^a-zA-Z0-9]", "", cand.title.lower())
            key = cand.url or norm_title
            if key and norm_title not in seen_keys:
                seen_keys.add(norm_title)
                deduped_candidates.append(cand)

    return deduped_candidates[:max_results]
