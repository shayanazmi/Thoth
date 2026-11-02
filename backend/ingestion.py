# Thoth · Developed by Shayan Azmi
"""
backend.ingestion
=================
Scholarly document ingestion engine.
Provides safe content-type discrimination, robust PDF and HTML extraction,
preservation of source identifiers and page demarcations, and explicit failure
and truncation tracking.
"""

import io
import os
import re
from typing import Optional, Tuple, Union


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


