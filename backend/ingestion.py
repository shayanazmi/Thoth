"""
backend.ingestion
=================
Scholarly document ingestion engine.
Provides safe content-type discrimination, robust PDF and HTML extraction,
preservation of source identifiers and page demarcations, and explicit failure
and truncation tracking.
"""

from dataclasses import dataclass, field
import datetime
import io
import os
import re
from typing import Dict, Any, Optional, Tuple, Union, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:  # pragma: no cover
    pypdf = None
    PYPDF_AVAILABLE = False


PDF_MAGIC_BYTES = b"%PDF-"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 "
    "(Thoth Scholarly Research Companion)"
)


@dataclass
class IngestionResult:
    """Represents the structured result of document ingestion and text extraction."""
    source_uri: str
    content_type: str  # 'pdf', 'html', 'plain', 'snippet', 'unsupported', 'unknown'
    status: str        # 'success', 'empty', 'failed', 'unsupported'
    text: str = ""
    num_pages: int = 0
    char_count: int = 0
    is_truncated: bool = False
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    passages: List[Dict[str, Any]] = field(default_factory=list)
    extraction_quality: str = "full"  # 'full', 'partial', 'snippet_only', 'inaccessible', 'empty', 'unsupported'
    extraction_method: str = "unknown"  # 'pypdf', 'beautifulsoup', 'plain_text', 'search_snippet', 'unknown'
    extraction_warnings: List[str] = field(default_factory=list)
    retrieval_timestamp: Optional[str] = None

    def __post_init__(self):
        if self.retrieval_timestamp is None:
            self.retrieval_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Derive extraction_quality accurately based on status and metadata
        if self.status == "failed":
            self.extraction_quality = "inaccessible"
        elif self.status == "empty":
            self.extraction_quality = "empty"
        elif self.status == "unsupported":
            self.extraction_quality = "unsupported"
        elif self.status == "success":
            if self.content_type == "snippet":
                self.extraction_quality = "snippet_only"
            elif self.is_truncated:
                self.extraction_quality = "partial"
            elif not self.extraction_quality or self.extraction_quality == "unknown":
                self.extraction_quality = "full"

        # Derive extraction_method if not explicitly specified
        if not self.extraction_method or self.extraction_method == "unknown":
            if self.content_type in ("pdf", "application/pdf"):
                self.extraction_method = "pypdf"
            elif self.content_type in ("html", "text/html"):
                self.extraction_method = "beautifulsoup"
            elif self.content_type in ("plain", "text/plain"):
                self.extraction_method = "plain_text"
            elif self.content_type == "snippet":
                self.extraction_method = "search_snippet"
            elif self.content_type == "unsupported":
                self.extraction_method = "unsupported"

        # Record standard extraction warnings
        if self.error_message and self.error_message not in self.extraction_warnings:
            self.extraction_warnings.append(self.error_message)
        if self.is_truncated and "Document text truncated at character budget" not in self.extraction_warnings:
            self.extraction_warnings.append("Document text truncated at character budget")

        if not self.passages and self.text and self.status == "success":
            self.passages = create_bounded_passages(
                self.text,
                content_type=self.content_type,
                source_uri=self.source_uri,
                extraction_quality=self.extraction_quality
            )
        elif self.passages and self.extraction_quality != "full":
            for p in self.passages:
                if isinstance(p, dict):
                    p["extraction_quality"] = self.extraction_quality

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "content_type": self.content_type,
            "status": self.status,
            "text": self.text,
            "num_pages": self.num_pages,
            "char_count": self.char_count,
            "is_truncated": self.is_truncated,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "passages": self.passages,
            "extraction_quality": self.extraction_quality,
            "extraction_method": self.extraction_method,
            "extraction_warnings": self.extraction_warnings,
            "retrieval_timestamp": self.retrieval_timestamp,
        }


def create_bounded_passages(
    text: str,
    content_type: str = "plain",
    source_uri: str = "",
    target_passage_chars: int = 800,
    extraction_quality: str = "full",
) -> List[Dict[str, Any]]:
    """
    Partitions extracted document text into bounded, deterministically indexed passages
    with page numbers (where available) and character offsets.
    """
    if not text or not str(text).strip():
        return []

    passages: List[Dict[str, Any]] = []

    is_pdf_content = content_type in ("pdf", "application/pdf") or "[Page " in text
    if is_pdf_content and "[Page " in text:
        page_pattern = re.compile(r"\[Page\s+(\d+)\]\s*\n?")
        matches = list(page_pattern.finditer(text))

        if matches:
            for i, match in enumerate(matches):
                page_num = int(match.group(1))
                content_start = match.end()
                content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                page_raw = text[content_start:content_end]
                page_text = page_raw.strip()

                if not page_text:
                    continue

                if len(page_text) <= int(target_passage_chars * 1.5):
                    has_unreadable = "Unreadable page content:" in page_text
                    passages.append({
                        "passage_id": f"p{page_num}-1",
                        "source_uri": source_uri,
                        "page_num": page_num,
                        "char_start": content_start,
                        "char_end": content_start + len(page_text),
                        "text": page_text,
                        "extraction_status": "warning" if has_unreadable else "success",
                        "extraction_quality": "partial" if has_unreadable else "full",
                        "warnings": ["Unreadable page content detected"] if has_unreadable else [],
                    })
                else:
                    paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
                    if not paragraphs:
                        paragraphs = [page_text]
                    current_chunk = []
                    current_len = 0
                    p_offset = content_start
                    sub_idx = 1

                    for para in paragraphs:
                        if current_len + len(para) > target_passage_chars and current_chunk:
                            chunk_text = "\n\n".join(current_chunk)
                            has_unreadable = "Unreadable page content:" in chunk_text
                            passages.append({
                                "passage_id": f"p{page_num}-{sub_idx}",
                                "source_uri": source_uri,
                                "page_num": page_num,
                                "char_start": p_offset,
                                "char_end": p_offset + len(chunk_text),
                                "text": chunk_text,
                                "extraction_status": "warning" if has_unreadable else "success",
                                "extraction_quality": "partial" if has_unreadable else "full",
                                "warnings": ["Unreadable page content detected"] if has_unreadable else [],
                            })
                            p_offset += len(chunk_text) + 2
                            sub_idx += 1
                            current_chunk = [para]
                            current_len = len(para)
                        else:
                            current_chunk.append(para)
                            current_len += len(para) + 2

                    if current_chunk:
                        chunk_text = "\n\n".join(current_chunk)
                        has_unreadable = "Unreadable page content:" in chunk_text
                        passages.append({
                            "passage_id": f"p{page_num}-{sub_idx}",
                            "source_uri": source_uri,
                            "page_num": page_num,
                            "char_start": p_offset,
                            "char_end": p_offset + len(chunk_text),
                            "text": chunk_text,
                            "extraction_status": "warning" if has_unreadable else "success",
                            "extraction_quality": "partial" if (has_unreadable or extraction_quality == "partial") else extraction_quality,
                            "warnings": ["Unreadable page content detected"] if has_unreadable else [],
                        })
            if passages:
                return passages

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    current_chunk = []
    current_len = 0
    p_offset = 0
    idx = 1

    for para in paragraphs:
        if current_len + len(para) > target_passage_chars and current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            passages.append({
                "passage_id": f"sec-{idx}",
                "source_uri": source_uri,
                "page_num": None,
                "char_start": p_offset,
                "char_end": p_offset + len(chunk_text),
                "text": chunk_text,
                "extraction_status": "success",
                "extraction_quality": extraction_quality,
                "warnings": [],
            })
            p_offset += len(chunk_text) + 2
            idx += 1
            current_chunk = [para]
            current_len = len(para)
        else:
            current_chunk.append(para)
            current_len += len(para) + 2

    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        passages.append({
            "passage_id": f"sec-{idx}",
            "source_uri": source_uri,
            "page_num": None,
            "char_start": p_offset,
            "char_end": p_offset + len(chunk_text),
            "text": chunk_text,
            "extraction_status": "success",
            "extraction_quality": extraction_quality,
            "warnings": [],
        })

    return passages


def select_representative_passages(
    passages: List[Dict[str, Any]],
    max_chars: int = 2400,
    max_passages: int = 4,
    focus_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Selects a deterministic, representative set of bounded passages across the document
    (ensuring evidence from later pages survives) within a character budget.
    """
    if not passages:
        return []

    if len(passages) <= max_passages:
        selected = []
        total_len = 0
        for p in passages:
            p_len = len(p.get("text", ""))
            if total_len + p_len <= max_chars or not selected:
                selected.append(p)
                total_len += p_len
            else:
                break
        return selected

    chosen_indices: List[int] = []
    first_idx = 0
    last_idx = len(passages) - 1

    chosen_indices.append(first_idx)

    keywords = set(re.findall(r"\w+", (focus_query or "").lower())) if focus_query else set()
    keywords = {k for k in keywords if len(k) > 3}

    scored_candidates = []
    for idx in range(1, last_idx):
        p_text = passages[idx].get("text", "").lower()
        score = sum(1 for kw in keywords if kw in p_text) if keywords else 0
        scored_candidates.append((score, idx))

    if keywords and any(s > 0 for s, _ in scored_candidates):
        scored_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for _, c_idx in scored_candidates[:max_passages - 2]:
            if c_idx not in chosen_indices:
                chosen_indices.append(c_idx)
    else:
        step = (len(passages) - 1) / (max_passages - 1)
        for i in range(1, max_passages - 1):
            target_idx = int(round(i * step))
            if target_idx not in chosen_indices and target_idx < len(passages):
                chosen_indices.append(target_idx)

    if last_idx not in chosen_indices:
        chosen_indices.append(last_idx)

    chosen_indices.sort()

    selected = []
    total_len = 0
    for idx in chosen_indices:
        p = passages[idx]
        p_len = len(p.get("text", ""))
        if total_len + p_len <= max_chars or not selected:
            selected.append(p)
            total_len += p_len
        else:
            break

    return selected


def format_passages_for_context(passages: List[Dict[str, Any]], max_chars: int = 2400) -> str:
    """
    Formats a list of passages into an annotated evidence string with
    page numbers and character offsets for the writer or verifier.
    """
    if not passages:
        return "(No passages available)"

    lines = []
    current_len = 0
    for p in passages:
        p_id = p.get("passage_id", "p")
        pg = f"Page {p['page_num']}" if p.get("page_num") is not None else "Section"
        start = p.get("char_start", 0)
        end = p.get("char_end", 0)
        txt = p.get("text", "").strip()

        header = f"[{p_id} | {pg} (offset {start}-{end})]"
        entry = f"{header}\n{txt}"

        if current_len + len(entry) > max_chars and lines:
            break

        lines.append(entry)
        current_len += len(entry) + 4

    return "\n\n".join(lines)


def detect_content_type(
    headers: Optional[Any] = None,
    content_bytes: Optional[bytes] = None,
    uri: str = "",
) -> str:
    """
    Distinguishes PDF from HTML or unsupported content safely using
    response headers, magic byte signatures, and URI heuristics.
    """
    # 1. Check magic bytes first (most reliable ground truth against server misconfiguration)
    if content_bytes and len(content_bytes) >= 5:
        header_prefix = content_bytes[:1024]
        if header_prefix.startswith(PDF_MAGIC_BYTES) or PDF_MAGIC_BYTES in header_prefix:
            return "pdf"

    # 2. Check Content-Type header
    if headers and hasattr(headers, "get"):
        raw_ct = headers.get("Content-Type") or headers.get("content-type")
        if isinstance(raw_ct, str):
            ct = raw_ct.lower().split(";")[0].strip()
            if ct in ("application/pdf", "application/x-pdf", "application/acrobat", "applications/pdf"):
                return "pdf"
            if ct in ("text/html", "application/xhtml+xml"):
                return "html"
            if ct in ("text/plain", "text/markdown"):
                return "plain"
            if any(ct.startswith(prefix) for prefix in ("image/", "video/", "audio/", "font/")):
                return "unsupported"
            if ct in ("application/zip", "application/x-tar", "application/gzip", "application/octet-stream"):
                # If octet-stream didn't match PDF magic bytes, mark unsupported
                return "unsupported"

    # 3. Magic text check for HTML
    if content_bytes:
        header_sample = content_bytes[:1024].lower()
        if (
            b"<!doctype html" in header_sample
            or b"<html" in header_sample
            or b"<head" in header_sample
            or b"<body" in header_sample
        ):
            return "html"

    # 4. URI heuristics as fallback
    lower_uri = uri.lower()
    if lower_uri.endswith(".pdf") or "/pdf/" in lower_uri or ".pdf?" in lower_uri:
        return "pdf"
    if lower_uri.endswith((".html", ".htm")):
        return "html"
    if lower_uri.endswith((".txt", ".md")):
        return "plain"

    return "html"  # Default assumption for standard web content


def extract_text_from_pdf(
    source: Union[bytes, str, io.BytesIO],
    max_pages: int = 40,
    max_chars: int = 15000,
) -> Tuple[str, str, int, bool, Optional[str]]:
    """
    Extracts readable text from PDF bytes or local file path using pypdf.
    Returns: (extracted_text, status, num_pages, is_truncated, error_message)
    """
    if not PYPDF_AVAILABLE or pypdf is None:  # pragma: no cover
        return "", "failed", 0, False, "PDF processing library 'pypdf' is not installed or available"

    try:
        if isinstance(source, bytes):
            if not source:
                return "", "failed", 0, False, "Empty PDF byte stream received"
            stream = io.BytesIO(source)
            reader = pypdf.PdfReader(stream)
        elif isinstance(source, io.BytesIO):
            reader = pypdf.PdfReader(source)
        elif isinstance(source, str):
            if not os.path.exists(source):
                return "", "failed", 0, False, f"Local PDF file not found: {source}"
            reader = pypdf.PdfReader(source)
        else:
            return "", "failed", 0, False, f"Unsupported PDF source type: {type(source)}"

        # Check encryption / password protection
        if getattr(reader, "is_encrypted", False):
            try:
                decrypt_res = reader.decrypt("")
                if decrypt_res == 0:
                    return "", "failed", len(reader.pages), False, "PDF is password protected and cannot be read"
            except Exception as e:
                return "", "failed", 0, False, f"Failed decrypting password protected PDF: {e}"

        total_pages = len(reader.pages)
        if total_pages == 0:
            return "", "empty", 0, False, "PDF document contains 0 pages"

        pages_to_read = min(total_pages, max_pages)
        page_chunks = []
        for i in range(pages_to_read):
            try:
                page = reader.pages[i]
                txt = page.extract_text()
                if txt and txt.strip():
                    page_chunks.append(f"[Page {i+1}]\n{txt.strip()}")
            except Exception as pe:
                page_chunks.append(f"[Page {i+1}: Unreadable page content: {pe}]")

        full_extracted = "\n\n".join(page_chunks).strip()

        # Clean excessive internal whitespace
        full_extracted = re.sub(r"[ \t]+", " ", full_extracted)
        full_extracted = re.sub(r"\n{3,}", "\n\n", full_extracted)

        if not full_extracted:
            return (
                "",
                "empty",
                total_pages,
                False,
                "PDF document yielded no extractable text (likely a scanned image, protected, or blank document)",
            )

        is_truncated = False
        if len(full_extracted) > max_chars:
            full_extracted = full_extracted[:max_chars].rsplit(" ", 1)[0] + "... [Text truncated at character budget]"
            is_truncated = True

        return full_extracted, "success", total_pages, is_truncated, None

    except getattr(pypdf.errors, "PdfReadError", Exception) as pre:
        return "", "failed", 0, False, f"Malformed or corrupted PDF document: {str(pre)}"
    except Exception as e:
        return "", "failed", 0, False, f"Unexpected error reading PDF: {str(e)}"


def extract_text_from_html(
    html_content: Union[str, bytes],
    max_chars: int = 15000,
) -> Tuple[str, str, bool, Optional[str]]:
    """
    Extracts readable text from HTML markup, discarding non-content tags.
    Returns: (extracted_text, status, is_truncated, error_message)
    """
    try:
        if isinstance(html_content, bytes):
            try:
                html_str = html_content.decode("utf-8")
            except UnicodeDecodeError:
                html_str = html_content.decode("latin-1", errors="replace")
        else:
            html_str = str(html_content)

        if not html_str or not html_str.strip():
            return "", "empty", False, "Empty HTML response received"

        soup = BeautifulSoup(html_str, "html.parser")

        # Decompose non-content and layout navigation elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if not text:
            return "", "empty", False, "No readable text content found in HTML document"

        is_truncated = False
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0] + "... [Text truncated at character budget]"
            is_truncated = True

        return text, "success", is_truncated, None

    except Exception as e:
        return "", "failed", False, f"Failed parsing HTML: {str(e)}"


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(min=1, max=5),
    reraise=True,
)
def _http_get_with_retry(url: str, timeout: int = 6, user_agent: str = DEFAULT_USER_AGENT) -> requests.Response:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent})
    if resp.status_code in (429, 503):
        raise requests.exceptions.RequestException(f"HTTP {resp.status_code} Rate Limited/Unavailable")
    return resp


def ingest_document(
    uri_or_path: str,
    timeout: int = 6,
    max_chars: int = 12000,
    user_agent: str = DEFAULT_USER_AGENT,
) -> IngestionResult:
    """
    Main entrypoint for scholarly document ingestion.
    Supports HTTP(S) URLs and local user-provided PDF/text files.
    Distinguishes PDF from HTML, extracts text reliably, preserves provenance,
    and returns a structured IngestionResult.
    """
    if not uri_or_path or not str(uri_or_path).strip():
        return IngestionResult(
            source_uri=str(uri_or_path or ""),
            content_type="unknown",
            status="failed",
            error_message="Empty URI or file path provided",
        )

    uri = str(uri_or_path).strip()

    # 1. Check for local user-provided files (path on disk or file:// URI)
    local_path = uri[7:] if uri.startswith("file://") else uri

    if os.path.exists(local_path) and os.path.isfile(local_path):
        try:
            with open(local_path, "rb") as f:
                header_bytes = f.read(1024)
                f.seek(0)
                full_bytes = f.read()

            c_type = detect_content_type(content_bytes=header_bytes, uri=local_path)
            meta = {
                "file_path": local_path,
                "file_size": len(full_bytes),
                "is_local_file": True,
            }

            if c_type == "pdf":
                txt, status, pages, is_trunc, err = extract_text_from_pdf(
                    source=full_bytes, max_chars=max_chars
                )
                return IngestionResult(
                    source_uri=uri,
                    content_type="pdf",
                    status=status,
                    text=txt,
                    num_pages=pages,
                    char_count=len(txt),
                    is_truncated=is_trunc,
                    error_message=err,
                    metadata=meta,
                )
            elif c_type == "plain":
                txt = full_bytes.decode("utf-8", errors="replace")
                is_trunc = len(txt) > max_chars
                if is_trunc:
                    txt = txt[:max_chars] + "... [Text truncated at character budget]"
                return IngestionResult(
                    source_uri=uri,
                    content_type="plain",
                    status="success" if txt.strip() else "empty",
                    text=txt.strip(),
                    num_pages=1,
                    char_count=len(txt.strip()),
                    is_truncated=is_trunc,
                    metadata=meta,
                )
            elif c_type == "html":
                txt, status, is_trunc, err = extract_text_from_html(
                    full_bytes, max_chars=max_chars
                )
                return IngestionResult(
                    source_uri=uri,
                    content_type="html",
                    status=status,
                    text=txt,
                    num_pages=1,
                    char_count=len(txt),
                    is_truncated=is_trunc,
                    error_message=err,
                    metadata=meta,
                )
            else:
                return IngestionResult(
                    source_uri=uri,
                    content_type=c_type,
                    status="unsupported",
                    error_message=f"Unsupported local document format: '{local_path}'",
                    metadata=meta,
                )
        except Exception as e:
            return IngestionResult(
                source_uri=uri,
                content_type="unknown",
                status="failed",
                error_message=f"Failed reading local file: {str(e)}",
            )

    # 2. Check if valid HTTP(S) URL
    parsed = urlparse(uri)
    if not (parsed.scheme in ("http", "https") and parsed.netloc):
        return IngestionResult(
            source_uri=uri,
            content_type="unknown",
            status="failed",
            error_message=f"Invalid URL or non-existent file path: '{uri}'",
        )

    # 3. Remote HTTP(S) fetch with retry
    try:
        resp = _http_get_with_retry(uri, timeout=timeout, user_agent=user_agent)
    except requests.exceptions.Timeout:
        return IngestionResult(
            source_uri=uri,
            content_type="unknown",
            status="failed",
            error_message=f"Network timeout after {timeout}s",
        )
    except requests.exceptions.HTTPError as he:
        status_code = getattr(getattr(he, "response", None), "status_code", None)
        if status_code == 403:
            return IngestionResult(
                source_uri=uri,
                content_type="unknown",
                status="failed",
                error_message="HTTP 403 Forbidden: Inaccessible or paywalled document",
            )
        elif status_code == 404:
            return IngestionResult(
                source_uri=uri,
                content_type="unknown",
                status="failed",
                error_message="HTTP 404 Not Found",
            )
        return IngestionResult(
            source_uri=uri,
            content_type="unknown",
            status="failed",
            error_message=f"HTTP request failed: {str(he)}",
        )
    except requests.exceptions.RequestException as re_err:
        return IngestionResult(
            source_uri=uri,
            content_type="unknown",
            status="failed",
            error_message=f"Network error: {str(re_err)}",
        )
    except Exception as e:
        return IngestionResult(
            source_uri=uri,
            content_type="unknown",
            status="failed",
            error_message=f"Unexpected fetch failure: {str(e)}",
        )

    # Validate response status
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as he:
        status_code = getattr(resp, "status_code", 0)
        if status_code == 403:
            return IngestionResult(
                source_uri=uri,
                content_type="unknown",
                status="failed",
                error_message="HTTP 403 Forbidden: Inaccessible or paywalled document",
            )
        return IngestionResult(
            source_uri=uri,
            content_type="unknown",
            status="failed",
            error_message=f"HTTP {status_code} Error: {str(he)}",
        )

    # 4. Content Type Discrimination
    headers = getattr(resp, "headers", {})
    raw_content = getattr(resp, "content", None)
    raw_text = getattr(resp, "text", "")

    # Safeguard against mock responses where content is not set as bytes
    if raw_content is None or not isinstance(raw_content, (bytes, bytearray)):
        if isinstance(raw_text, str):
            raw_content = raw_text.encode("utf-8", errors="replace")
        else:
            raw_content = b""

    c_type = detect_content_type(headers=headers, content_bytes=raw_content, uri=uri)
    meta = {
        "status_code": getattr(resp, "status_code", 200),
        "url": getattr(resp, "url", uri),
    }

    # 5. Extraction by content type
    if c_type == "pdf":
        txt, status, pages, is_trunc, err = extract_text_from_pdf(
            source=raw_content, max_chars=max_chars
        )
        return IngestionResult(
            source_uri=uri,
            content_type="pdf",
            status=status,
            text=txt,
            num_pages=pages,
            char_count=len(txt),
            is_truncated=is_trunc,
            error_message=err,
            metadata=meta,
        )
    elif c_type == "unsupported":
        raw_ct = headers.get("Content-Type") if hasattr(headers, "get") else "binary/unknown"
        return IngestionResult(
            source_uri=uri,
            content_type="unsupported",
            status="unsupported",
            error_message=f"Unsupported content type ({raw_ct}) cannot be extracted as scholarly text",
            metadata=meta,
        )
    elif c_type == "plain":
        txt = raw_content.decode("utf-8", errors="replace")
        is_trunc = len(txt) > max_chars
        if is_trunc:
            txt = txt[:max_chars] + "... [Text truncated at character budget]"
        return IngestionResult(
            source_uri=uri,
            content_type="plain",
            status="success" if txt.strip() else "empty",
            text=txt.strip(),
            num_pages=1,
            char_count=len(txt.strip()),
            is_truncated=is_trunc,
            metadata=meta,
        )
    else:  # html
        txt, status, is_trunc, err = extract_text_from_html(
            html_content=raw_content if raw_content else raw_text,
            max_chars=max_chars,
        )
        return IngestionResult(
            source_uri=uri,
            content_type="html",
            status=status,
            text=txt,
            num_pages=1,
            char_count=len(txt),
            is_truncated=is_trunc,
            error_message=err,
            metadata=meta,
        )


def ingest_snippet(
    uri: str,
    snippet_text: str,
    title: str = "",
    source_id: str = "",
) -> IngestionResult:
    """
    Explicitly ingests a search-result snippet or abstract when full text was not retrieved.
    Guarantees extraction_quality='snippet_only' so THOTH does not imply full-text review.
    """
    clean_text = (snippet_text or "").strip()
    return IngestionResult(
        source_uri=uri,
        content_type="snippet",
        status="success" if clean_text else "empty",
        text=clean_text,
        num_pages=0,
        char_count=len(clean_text),
        is_truncated=False,
        error_message=None if clean_text else "Empty snippet provided",
        metadata={"title": title, "source_id": source_id, "is_snippet": True},
        extraction_quality="snippet_only",
        extraction_method="search_snippet",
        extraction_warnings=["Full text was not retrieved; only search snippet or abstract was available."],
    )

