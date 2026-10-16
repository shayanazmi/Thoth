import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import requests
import pypdf

from backend.ingestion import (
    IngestionResult,
    detect_content_type,
    extract_text_from_pdf,
    extract_text_from_html,
    ingest_document,
)
from backend.tools import scrape_url, _scrape_url_with_retry
from backend.orchestrator import concurrent_scrape_urls
from backend.dispatcher import Dispatcher


def _create_synthetic_text_pdf(text: str) -> bytes:
    """Helper to build a valid, minimal PDF 1.4 byte stream containing explicit text."""
    escaped_text = text.replace("(", "\\(").replace(")", "\\)")
    text_len = len(escaped_text) + 20
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length " + str(text_len).encode("ascii") + b" >> stream\n"
        b"BT /F1 12 Tf 72 712 Td (" + escaped_text.encode("latin-1", "replace") + b") Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000261 00000 n \n0000000367 00000 n \ntrailer << /Size 6 /Root 1 0 R >>\nstartxref\n450\n%%EOF\n"
    )
    return pdf_content


def _create_blank_pdf() -> bytes:
    """Helper to build a valid PDF with 1 blank page (simulating empty / scanned PDF)."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestDocumentIngestionMilestone(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for the Phase 0 scholarly document ingestion milestone.
    Covers:
    1. Valid text-based PDF (HTTP mock and local user-provided file).
    2. HTML article extraction with tag stripping.
    3. URL returning unexpected content type (e.g. ZIP, JPEG).
    4. Empty, malformed, or unreadable PDF.
    5. Timeout or inaccessible URL (HTTP 403, 404, network timeout).
    6. Preservation of source identity and evidence provenance.
    7. Tool compatibility and downstream orchestrator visibility.
    """

    # 1. Valid text-based PDF
    @patch("backend.ingestion._http_get_with_retry")
    def test_valid_text_based_pdf_http_extraction(self, mock_get):
        pdf_bytes = _create_synthetic_text_pdf("Experimental results show 99.8% precision on benchmark datasets.")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.content = pdf_bytes
        mock_resp.text = pdf_bytes.decode("latin-1")
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = ingest_document("https://arxiv.org/pdf/2401.12345v1")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.content_type, "pdf")
        self.assertGreaterEqual(result.num_pages, 1)
        self.assertIn("99.8% precision", result.text)
        self.assertIn("[Page 1]", result.text)
        self.assertIsNone(result.error_message)

    def test_valid_text_based_pdf_local_user_provided_file(self):
        pdf_bytes = _create_synthetic_text_pdf("User uploaded manuscript draft discussing epistemic validation.")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            f.flush()
            temp_path = f.name

        try:
            result = ingest_document(temp_path)
            self.assertEqual(result.status, "success")
            self.assertEqual(result.content_type, "pdf")
            self.assertIn("epistemic validation", result.text)
            self.assertTrue(result.metadata.get("is_local_file"))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # 2. HTML article extraction
    @patch("backend.ingestion._http_get_with_retry")
    def test_html_article_extraction_cleans_tags(self, mock_get):
        html_markup = (
            "<!DOCTYPE html><html><head><title>Quantum Computing</title>"
            "<style>body { color: red; }</style>"
            "<script>alert('track');</script></head>"
            "<body><nav>Home | Archive | Contact</nav>"
            "<article><h1>Qubit Coherence Study</h1>"
            "<p>Superconducting circuits achieved a relaxation time of 120 microseconds at 15 mK.</p></article>"
            "<footer>Copyright 2026 Academic Press</footer></body></html>"
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.content = html_markup.encode("utf-8")
        mock_resp.text = html_markup
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = ingest_document("https://journals.example.org/articles/quantum-01")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.content_type, "html")
        self.assertIn("relaxation time of 120 microseconds", result.text)
        self.assertNotIn("alert('track')", result.text)
        self.assertNotIn("Home | Archive", result.text)
        self.assertNotIn("Copyright 2026", result.text)

    # 3. Unexpected content type
    @patch("backend.ingestion._http_get_with_retry")
    def test_unexpected_binary_content_type_rejected(self, mock_get):
        zip_bytes = b"PK\x03\x04\x14\x00\x00\x00\x08\x00\x00\x00\x00\x00fakezipbinarydata"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/zip"}
        mock_resp.content = zip_bytes
        mock_resp.text = ""
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = ingest_document("https://example.org/dataset.zip")
        self.assertEqual(result.status, "unsupported")
        self.assertEqual(result.content_type, "unsupported")
        self.assertEqual(result.text, "")
        self.assertIn("Unsupported content type", result.error_message)

        # Scrape tool should surface the failure gracefully
        tool_output = scrape_url.invoke({"url": "https://example.org/dataset.zip"})
        self.assertTrue(tool_output.startswith("Could not scrape URL: Unsupported content type"))

    # 4. Empty, malformed, or unreadable PDF
    @patch("backend.ingestion._http_get_with_retry")
    def test_malformed_pdf_reports_explicit_failure(self, mock_get):
        corrupt_bytes = b"%PDF-1.4\n\x00\xff\xfe corrupted binary stream that is not valid pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.content = corrupt_bytes
        mock_resp.text = ""
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = ingest_document("https://arxiv.org/pdf/corrupt")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.content_type, "pdf")
        self.assertEqual(result.text, "")
        self.assertIn("Malformed or corrupted PDF", result.error_message)

    @patch("backend.ingestion._http_get_with_retry")
    def test_blank_scanned_pdf_reports_empty_status(self, mock_get):
        blank_bytes = _create_blank_pdf()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.content = blank_bytes
        mock_resp.text = ""
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = ingest_document("https://arxiv.org/pdf/blank")
        self.assertEqual(result.status, "empty")
        self.assertEqual(result.content_type, "pdf")
        self.assertEqual(result.text, "")
        self.assertIn("yielded no extractable text", result.error_message)

    # 5. Timeout and inaccessible URLs
    @patch("backend.ingestion._http_get_with_retry")
    def test_network_timeout_reports_failed_status(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        result = ingest_document("https://slow-repository.edu/paper.pdf", timeout=3)
        self.assertEqual(result.status, "failed")
        self.assertIn("Network timeout", result.error_message)

        tool_output = scrape_url.invoke({"url": "https://slow-repository.edu/paper.pdf"})
        self.assertTrue(tool_output.startswith("Could not scrape URL: Network timeout"))

    @patch("backend.ingestion._http_get_with_retry")
    def test_paywalled_403_reports_inaccessible_status(self, mock_get):
        resp_403 = MagicMock()
        resp_403.status_code = 403
        http_err = requests.exceptions.HTTPError("403 Client Error: Forbidden", response=resp_403)
        mock_get.side_effect = http_err

        result = ingest_document("https://paywalled-publisher.com/article/12345")
        self.assertEqual(result.status, "failed")
        self.assertIn("HTTP 403 Forbidden: Inaccessible or paywalled document", result.error_message)

    # 6. Preservation of source identity and evidence provenance
    @patch("backend.ingestion._http_get_with_retry")
    async def test_concurrent_scrape_preserves_provenance_and_content_type(self, mock_get):
        pdf_bytes = _create_synthetic_text_pdf("Detailed empirical methodology for distributed multi-agent consensus.")

        def mock_fetch(url, *args, **kwargs):
            resp = MagicMock()
            if "arxiv.org/pdf" in url:
                resp.status_code = 200
                resp.headers = {"Content-Type": "application/pdf"}
                resp.content = pdf_bytes
                resp.text = pdf_bytes.decode("latin-1")
                resp.raise_for_status.return_value = None
                return resp
            elif "html-journal" in url:
                html_txt = "<html><body><article><p>HTML evidence body discussing distributed state machines.</p></article></body></html>"
                resp.status_code = 200
                resp.headers = {"Content-Type": "text/html"}
                resp.content = html_txt.encode("utf-8")
                resp.text = html_txt
                resp.raise_for_status.return_value = None
                return resp
            else:
                resp_404 = MagicMock()
                resp_404.status_code = 404
                raise requests.exceptions.HTTPError("404 Client Error: Not Found", response=resp_404)

        mock_get.side_effect = mock_fetch

        urls = [
            "https://arxiv.org/pdf/2401.99999",
            "https://html-journal.org/article-42",
            "https://broken-link.org/missing",
        ]
        dispatcher = Dispatcher(max_concurrent=3, max_attempts=1, base_delay=0.01)

        content, sources = await concurrent_scrape_urls(urls, dispatcher)

        self.assertEqual(len(sources), 3)

        pdf_src = next(s for s in sources if "arxiv" in s["url"])
        self.assertEqual(pdf_src["scrape_status"], "success")
        self.assertEqual(pdf_src["content_type"], "pdf")
        self.assertIn("empirical methodology", pdf_src["extracted_text"])

        html_src = next(s for s in sources if "html-journal" in s["url"])
        self.assertEqual(html_src["scrape_status"], "success")
        self.assertEqual(html_src["content_type"], "html")
        self.assertIn("distributed state machines", html_src["extracted_text"])

        fail_src = next(s for s in sources if "broken-link" in s["url"])
        self.assertEqual(fail_src["scrape_status"], "failed")
        self.assertEqual(fail_src["extracted_text"], "")
        self.assertIn("404", fail_src["scrape_error"])

    # 7. Safe local text file support
    def test_local_text_and_markdown_file_ingestion(self):
        plain_content = "# Academic Manuscript Notes\nPreliminary hypothesis: neural routing improves convergence."
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
            f.write(plain_content)
            f.flush()
            temp_path = f.name

        try:
            result = ingest_document(temp_path)
            self.assertEqual(result.status, "success")
            self.assertEqual(result.content_type, "plain")
            self.assertIn("neural routing", result.text)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
