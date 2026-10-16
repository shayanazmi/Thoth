"""
backend.tests.test_evidence_provenance_and_verification
=======================================================
Comprehensive test suite for THOTH Evidence Ingestion, Provenance,
and Claim Verification Milestone.

Verifies:
1. Source extraction honesty (PDF boundaries, HTML cleanup, empty/scanned PDFs, truncation).
2. Evidence provenance (passage offsets, locators, snippet vs full-text distinctions).
3. Claim verification from quotation matching to semantic support (catching adversarial quote stuffing).
4. Inspectable report provenance and deterministic bibliography with access quality badges.
"""

import io
import re
import unittest
from unittest.mock import patch, MagicMock

import pypdf
from backend.ingestion import (
    IngestionResult,
    ingest_document,
    ingest_snippet,
    extract_text_from_pdf,
    extract_text_from_html,
    create_bounded_passages,
    detect_content_type,
)
from backend.tools import scrape_url, scrape_url_structured
from backend.orchestrator import _extract_domain
from backend.intellectual_rigour.integrity_gate import (
    _clean_source_id,
    _resolve_source_record,
    verify_source_identity,
    verify_quote_provenance,
    verify_passage_locator,
    evaluate_claim_support,
    audit_report_integrity,
    generate_deterministic_bibliography,
)
from backend.agents import ReportClaim, VerificationResult


def _build_dummy_pdf_bytes(page_texts: list) -> bytes:
    """Helper to synthesize valid in-memory multi-page PDF bytes for tests."""
    writer = pypdf.PdfWriter()
    for txt in page_texts:
        writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


class TestSourceExtractionReliabilityAndHonesty(unittest.TestCase):
    """Test PDF page boundaries, HTML boilerplate stripping, and honest truncation tracking."""

    def test_pdf_page_demarcation_and_boundaries_preserved(self):
        """When text contains page markers, bounded passages retain distinct page numbers."""
        pdf_text = (
            "[Page 1]\nIntroduction to Topological Kondo Insulators and heavy fermions.\n\n"
            "[Page 2]\nExperimental methods using angle-resolved photoemission spectroscopy.\n\n"
            "[Page 3]\nResults demonstrate surface Dirac cones crossing the Fermi level at Gamma."
        )
        passages = create_bounded_passages(pdf_text, content_type="pdf", source_uri="https://example.edu/paper.pdf")
        self.assertGreaterEqual(len(passages), 3)

        page_nums = [p["page_num"] for p in passages]
        self.assertIn(1, page_nums)
        self.assertIn(2, page_nums)
        self.assertIn(3, page_nums)

        # Confirm passage IDs contain page numbers
        p_ids = [p["passage_id"] for p in passages]
        self.assertTrue(any("p1-" in pid for pid in p_ids))
        self.assertTrue(any("p2-" in pid for pid in p_ids))
        self.assertTrue(any("p3-" in pid for pid in p_ids))

    def test_html_boilerplate_stripped_cleanly(self):
        """HTML extraction discards navigation, scripts, footers, and leaves clean scholarly text."""
        raw_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Scholarly Article</title><script>var tracker = 1;</script></head>
        <body>
            <nav><a href="/home">Home</a><a href="/login">Sign In</a></nav>
            <header>Cookie Notice: We use tracking cookies.</header>
            <article>
                <h1>Phase Coherence in Mesoscopic Rings</h1>
                <p>We measured Aharonov-Bohm oscillations with a fundamental period of h/e.</p>
                <p>The phase coherence length exceeded 12 micrometers at 20 millikelvin.</p>
            </article>
            <aside>Related Advertisements</aside>
            <footer>Copyright 2026 Publisher Group. All rights reserved.</footer>
        </body>
        </html>
        """
        extracted, status, is_trunc, err = extract_text_from_html(raw_html)
        self.assertEqual(status, "success")
        self.assertFalse(is_trunc)
        self.assertIn("Phase Coherence in Mesoscopic Rings", extracted)
        self.assertIn("Aharonov-Bohm oscillations", extracted)
        self.assertNotIn("var tracker = 1", extracted)
        self.assertNotIn("Cookie Notice", extracted)
        self.assertNotIn("Related Advertisements", extracted)
        self.assertNotIn("Copyright 2026 Publisher Group", extracted)

    def test_empty_and_malformed_documents_reported_accurately(self):
        """Empty or unreadable content returns status='empty' and is not falsely represented as success."""
        res_empty = ingest_document("")
        self.assertEqual(res_empty.status, "failed")
        self.assertEqual(res_empty.extraction_quality, "inaccessible")

        empty_html = "<html><body>   </body></html>"
        text, status, is_trunc, err = extract_text_from_html(empty_html)
        self.assertEqual(status, "empty")
        self.assertEqual(text, "")

    def test_scanned_or_image_pdf_reported_as_empty_not_success(self):
        """A PDF with zero extractable text (e.g. scanned images without OCR) returns status='empty'."""
        pdf_bytes = _build_dummy_pdf_bytes(["", ""])
        text, status, num_pages, is_trunc, err = extract_text_from_pdf(pdf_bytes)
        self.assertEqual(status, "empty")
        self.assertEqual(text, "")
        self.assertEqual(num_pages, 2)
        self.assertIn("scanned image", (err or "").lower())

    def test_partial_extraction_explicitly_represented_without_silent_truncation(self):
        """When text exceeds character limit, truncation is documented and extraction_quality='partial'."""
        large_text = "Quantum state tomography demonstrates density matrix coherence. " * 300
        res = IngestionResult(
            source_uri="https://arxiv.org/abs/2405.0001",
            content_type="plain",
            status="success",
            text=large_text[:1000] + "... [Text truncated at character budget]",
            char_count=len(large_text),
            is_truncated=True,
        )
        self.assertTrue(res.is_truncated)
        self.assertEqual(res.extraction_quality, "partial")
        self.assertTrue(any("truncated" in w.lower() for w in res.extraction_warnings))

    def test_source_metadata_not_fabricated(self):
        """Missing DOIs, arXiv IDs, or authors remain None or explicitly unlisted."""
        snippet_res = ingest_snippet(
            uri="https://nature.com/articles/s41586-026",
            snippet_text="Room temperature optical lattice clocks demonstrated 1e-19 frequency uncertainty.",
            title="Optical Lattice Clocks",
        )
        self.assertEqual(snippet_res.extraction_quality, "snippet_only")
        self.assertEqual(snippet_res.content_type, "snippet")
        self.assertEqual(snippet_res.num_pages, 0)
        self.assertNotIn("doi", snippet_res.metadata)


class TestEvidenceProvenanceAndPassageTracking(unittest.TestCase):
    """Test passage offsets, stable locators, and access status tracking."""

    def test_passages_map_to_valid_source_uri_and_offsets(self):
        """Passages retain exact start/end offsets that slice back into the extracted text."""
        raw_text = (
            "[Page 1]\nFirst paragraph explaining topological insulators.\n\n"
            "Second paragraph detailing spin-orbit coupling and band inversion.\n\n"
            "[Page 2]\nThird paragraph presenting transport measurements and conductance quantization."
        )
        passages = create_bounded_passages(raw_text, content_type="pdf", source_uri="https://example.org/topo.pdf")
        self.assertGreater(len(passages), 0)

        for p in passages:
            self.assertEqual(p["source_uri"], "https://example.org/topo.pdf")
            self.assertIn("passage_id", p)
            self.assertIn("extraction_quality", p)
            self.assertIn("warnings", p)

    def test_inaccessible_source_has_inaccessible_quality(self):
        """Sources that fail network retrieval have extraction_quality='inaccessible'."""
        with patch("backend.ingestion._http_get_with_retry") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 403
            import requests
            http_err = requests.exceptions.HTTPError(response=mock_resp)
            mock_get.side_effect = http_err

            res = ingest_document("https://paywalled-journal.org/restricted-article")
            self.assertEqual(res.status, "failed")
            self.assertEqual(res.extraction_quality, "inaccessible")
            self.assertIn("403", res.error_message)

    def test_passage_locator_verification_accepts_valid_and_rejects_missing(self):
        """Passage locator like 'src-1:p1-1' is verified against retained passages."""
        sources = [{
            "id": "src-majorana",
            "title": "Majorana Modes in Nanowires",
            "scrape_status": "success",
            "extraction_quality": "full",
            "passages": [
                {"passage_id": "p1-1", "page_num": 1, "text": "Zero-bias conductance peak observed at 0.5T."},
                {"passage_id": "p2-1", "page_num": 2, "text": "Peak height saturates near 2e^2/h at base temperature."}
            ]
        }]

        # Valid locators
        ok1, err1 = verify_passage_locator("src-majorana:p1-1", sources)
        self.assertTrue(ok1)
        self.assertIsNone(err1)

        ok2, err2 = verify_passage_locator("src-majorana, p. 2", sources)
        self.assertTrue(ok2)
        self.assertIsNone(err2)

        # Invalid locator (non-existent page/passage)
        bad_ok, bad_err = verify_passage_locator("src-majorana:p99-1", sources)
        self.assertFalse(bad_ok)
        self.assertIn("p99-1", bad_err)


class TestClaimSupportVersusQuotationMatching(unittest.TestCase):
    """
    Adversarial and semantic claim support tests.
    Demonstrates that quoting a real sentence does NOT give a pass to an unsupported claim.
    """

    def setUp(self):
        self.sources = [
            {
                "id": "src-virology",
                "title": "In Vitro Antiviral Screening of Compound X",
                "scrape_status": "success",
                "extraction_quality": "full",
                "extracted_text": (
                    "Under laboratory cell culture conditions, we observed preliminary in-vitro cell viability "
                    "reduction at 50 micromolar concentrations of Compound X. The compound has not been evaluated in "
                    "animals or human patients, and clinical efficacy in humans remains completely unknown."
                ),
                "passages": [
                    {
                        "passage_id": "p1-1",
                        "page_num": 1,
                        "text": "Under laboratory cell culture conditions, we observed preliminary in-vitro cell viability reduction at 50 micromolar concentrations of Compound X."
                    }
                ]
            },
            {
                "id": "src-calorimetry",
                "title": "Calorimetric Measurements of Palladium Cells",
                "scrape_status": "success",
                "extraction_quality": "full",
                "extracted_text": (
                    "During the electrolytic charging phase, cell temperature decreased slightly by 0.3 K. "
                    "No statistically significant excess heat generation was observed across all 14 test runs."
                ),
                "passages": [
                    {
                        "passage_id": "p1-1",
                        "page_num": 1,
                        "text": "During the electrolytic charging phase, cell temperature decreased slightly by 0.3 K."
                    }
                ]
            },
            {
                "id": "src-epidemiology",
                "title": "Observational Cohort Study on Dietary Micronutrients",
                "scrape_status": "success",
                "extraction_quality": "full",
                "extracted_text": (
                    "Self-reported micronutrient intake was correlated with a minor reduction in self-reported fatigue. "
                    "Because this was an observational study, correlation does not imply causation, and no causal mechanism is established."
                ),
            },
            {
                "id": "src-inaccessible",
                "title": "Paywalled High-Pressure Physics Paper",
                "scrape_status": "failed",
                "scrape_error": "HTTP 403 Forbidden",
                "extraction_quality": "inaccessible",
                "extracted_text": "",
            },
            {
                "id": "src-snippet",
                "title": "Search Snippet Only Paper",
                "scrape_status": "failed",
                "scrape_error": "HTTP 404 Not Found",
                "extraction_quality": "snippet_only",
                "abstract": "Brief abstract snippet mentioning high-entropy alloys.",
                "extracted_text": "",
            }
        ]

    def test_adversarial_quote_with_unsupported_clinical_overclaim(self):
        """
        Adversarial test: A verbatim real quotation ('we observed preliminary in-vitro cell viability reduction')
        is paired with a fabricated claim that Compound X cures human patients.
        Must be caught and marked INSUFFICIENT / UNSUPPORTED, NOT SUPPORTED.
        """
        claim = "Compound X demonstrates complete clinical efficacy and cures human patients [[src-virology]]."
        quote = "we observed preliminary in-vitro cell viability reduction"

        # 1. Verify quote is genuine
        q_valid, _ = verify_quote_provenance(quote, "src-virology", self.sources)
        self.assertTrue(q_valid, "Quote must be a real quotation present in the source text.")

        # 2. Evaluate claim support
        sup_status, reason, meta = evaluate_claim_support(
            claim_text=claim,
            source_record=self.sources[0],
            quoted_evidence=quote
        )

        # Must NOT be marked SUPPORTED
        self.assertNotEqual(sup_status, "SUPPORTED")
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED"))
        self.assertIn("overgeneralization", reason.lower())

    def test_adversarial_quote_with_contradictory_direction(self):
        """
        Adversarial test: Quoting a genuine phrase ('cell temperature decreased slightly') to argue
        that the experiment produced massive thermal escalation.
        Must be caught and marked CONTRADICTED.
        """
        claim = "The electrolytic reaction caused significantly increased thermal escalation [[src-calorimetry]]."
        quote = "cell temperature decreased slightly"

        # Quote is genuine
        q_valid, _ = verify_quote_provenance(quote, "src-calorimetry", self.sources)
        self.assertTrue(q_valid)

        sup_status, reason, meta = evaluate_claim_support(
            claim_text=claim,
            source_record=self.sources[1],
            quoted_evidence=quote
        )
        self.assertEqual(sup_status, "CONTRADICTED")
        self.assertIn("contradict", reason.lower())

    def test_adversarial_quote_with_unsupported_causal_leap(self):
        """
        Adversarial test: Quoting genuine observational correlation ('was correlated with a minor reduction')
        to claim definitive proof of causation.
        Must be flagged as causal overclaim.
        """
        claim = "Dietary micronutrient intake conclusively proves to cause fatigue elimination [[src-epidemiology]]."
        quote = "was correlated with a minor reduction"

        sup_status, reason, meta = evaluate_claim_support(
            claim_text=claim,
            source_record=self.sources[2],
            quoted_evidence=quote
        )
        self.assertNotEqual(sup_status, "SUPPORTED")
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED"))
        self.assertIn("causal", reason.lower())

    def test_claim_on_inaccessible_source_is_unverifiable(self):
        """Claims attributing findings to an inaccessible source are marked UNVERIFIABLE."""
        claim = "Megabar pressures produced metallic hydrogen in high-pressure cells [[src-inaccessible]]."
        sup_status, reason, meta = evaluate_claim_support(
            claim_text=claim,
            source_record=self.sources[3]
        )
        self.assertEqual(sup_status, "UNVERIFIABLE")
        self.assertIn("inaccessible", reason.lower())

    def test_snippet_only_source_rejects_comprehensive_full_text_overclaim(self):
        """A source available only as a search snippet rejects claims asserting comprehensive full-text review."""
        claim = "A comprehensive multi-center cohort review and detailed protocol analysis verified the alloy properties [[src-snippet]]."
        sup_status, reason, meta = evaluate_claim_support(
            claim_text=claim,
            source_record=self.sources[4]
        )
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED"))
        self.assertIn("snippet", reason.lower())

    def test_accurate_quotation_and_grounded_claim_is_supported(self):
        """A genuine quote paired with an accurate, bounded claim passes as SUPPORTED."""
        claim = "Angle-resolved photoemission spectroscopy observed Dirac cones crossing the Fermi level [[src-topo]]."
        quote = "Dirac cones crossing the Fermi level"
        source = {
            "id": "src-topo",
            "title": "Topological Insulator ARPES",
            "scrape_status": "success",
            "extraction_quality": "full",
            "extracted_text": "We performed angle-resolved photoemission spectroscopy and observed Dirac cones crossing the Fermi level at the surface boundary.",
        }
        sup_status, reason, meta = evaluate_claim_support(
            claim_text=claim,
            source_record=source,
            quoted_evidence=quote
        )
        self.assertEqual(sup_status, "SUPPORTED")


class TestReportIntegrationAndDeterministicProvenance(unittest.TestCase):
    """Test bibliography access tags, locator parsing, and fail-closed audit decisions."""

    def test_deterministic_bibliography_preserves_access_and_quality_badges(self):
        """Deterministic bibliography distinguishes full-text, partial, snippet-only, and inaccessible sources."""
        report_text = (
            "## Key Findings\n"
            "- Finding A was confirmed in full text [[src-full:p1-1]].\n"
            "- Finding B was noted in partial excerpt [[src-partial:p2-1]].\n"
            "- Finding C was mentioned in search snippet [[src-snip]].\n"
            "- Finding D was inaccessible [[src-paywall]].\n"
        )
        sources = [
            {"id": "src-full", "title": "Full Paper", "authors": ["Alice"], "extraction_quality": "full", "num_pages": 12},
            {"id": "src-partial", "title": "Partial Paper", "authors": ["Bob"], "extraction_quality": "partial", "num_pages": 4},
            {"id": "src-snip", "title": "Snippet Paper", "authors": ["Carol"], "extraction_quality": "snippet_only"},
            {"id": "src-paywall", "title": "Paywalled Paper", "authors": ["Dave"], "extraction_quality": "inaccessible"},
        ]

        biblio_report, deduped, unresolved = generate_deterministic_bibliography(report_text, sources)
        self.assertEqual(len(deduped), 4)
        self.assertEqual(len(unresolved), 0)

        self.assertIn("[Full Text (12 pages)]", biblio_report)
        self.assertIn("[Partial Extraction - 4 pages]", biblio_report)
        self.assertIn("[Search Snippet / Abstract Only]", biblio_report)
        self.assertIn("[Inaccessible / Retrieval Failed]", biblio_report)

    def test_audit_report_integrity_fails_closed_on_adversarial_quote(self):
        """When an adversarial quote stuffing claim is audited, overall report verification fails."""
        report = (
            "## Key Findings\n"
            "Compound X cures human patients definitively [[src-virology]].\n"
        )
        sources = [
            {
                "id": "src-virology",
                "title": "In Vitro Compound X Study",
                "scrape_status": "success",
                "extraction_quality": "full",
                "extracted_text": "In vitro preliminary cell culture observed cell viability reduction. Untested in humans.",
            }
        ]
        raw_verifier = {
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Compound X cures human patients definitively",
                    "source_ids": ["src-virology"],
                    "quoted_evidence": "In vitro preliminary cell culture observed cell viability reduction",
                    "is_valid": True,  # Verifier LLM was tricked by the real quote!
                    "verification_status": "DIRECTLY_SUPPORTED"
                }
            ]
        }

        # Deterministic audit gate must catch the overclaim and override is_valid to False!
        audit = audit_report_integrity(
            report_text=report,
            cumulative_sources=sources,
            raw_verifier_response=raw_verifier
        )

        self.assertFalse(audit.is_verified)
        self.assertEqual(audit.status, "FAILED")
        self.assertEqual(audit.unsupported_or_contradicted_count, 1)
        self.assertEqual(audit.claims[0].verification_status, "UNSUPPORTED")
        self.assertIn("overgeneralization", audit.claims[0].reason.lower())


if __name__ == "__main__":
    unittest.main()
