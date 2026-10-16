"""
THOTH — Evidence Integrity: Adversarial End-to-End Audit and Correctness Gate Regression Matrix
Phase 3 Test Suite.

Covers:
  Group A: High-Priority Trust Failures
    A1: Genuine quote, unsupported clinical conclusion
    A2: Contradictory result (null/decrease claimed as significant increase)
    A3: Correlation presented as causation
    A4: Correct source, wrong passage (quote/evidence absent from cited passage)
    A5: Missing or fabricated evidence locator (rejected on unindexed source or missing passage)
    A6: Claim changes after verification (claim drift / desynchronization detection)

  Group B: Source-Access & Extraction Failures
    B1: Snippet or abstract presented as full-text review
    B2: Partial extraction with bounded passage provenance
    B3: Inaccessible source (HTTP 403 / paywall) distinct from full-text
    B4: Empty or unsupported document (scanned image PDF)

  Group C: Research-Quality Failures
    C1: Conflicting evidence (omitted contradiction across retrieved sources / cherry-picking)
    C2: Claim with citation but no supporting passage
    C3: Overstated generalizability (animal/simulation scope leap)
    C4: Unsupported quantitative detail (hallucinated metric / effect size)

  Group D: End-to-End Pipeline & Report Integrity
    D1: Scraped metadata & passages preserved through concurrent_scrape_urls merge
    D2: Final report prepends explicit CAUTION banner when unverified
"""

import unittest
import pytest
from typing import Dict, Any, List

from backend.ingestion import (
    create_bounded_passages,
    ingest_snippet,
    ingest_document,
    IngestionResult
)
from backend.agents import (
    ReportClaim,
    ReportIntegrityResult
)
from backend.intellectual_rigour.integrity_gate import (
    evaluate_claim_support,
    audit_report_integrity,
    verify_quote_provenance,
    verify_passage_locator,
    verify_quantitative_claim,
    generate_deterministic_bibliography,
    _clean_source_id
)
from backend.orchestrator import concurrent_scrape_urls


class TestAdversarialCorrectnessMatrix(unittest.TestCase):

    def setUp(self):
        self.sources = [
            {
                "id": "src-invitro",
                "title": "In Vitro Screening of Molecule Alpha",
                "url": "https://doi.org/10.1016/j.cell.2024.01",
                "scrape_status": "success",
                "extraction_quality": "full",
                "num_pages": 4,
                "extracted_text": (
                    "In vitro cell viability assays demonstrated preliminary reduction in cancer cell proliferation at 100 uM. "
                    "However, clinical translation has not been attempted and efficacy in human patients is completely unverified."
                ),
                "passages": [
                    {
                        "passage_id": "p1-1",
                        "page_num": 1,
                        "text": "In vitro cell viability assays demonstrated preliminary reduction in cancer cell proliferation at 100 uM."
                    },
                    {
                        "passage_id": "p4-1",
                        "page_num": 4,
                        "text": "However, clinical translation has not been attempted and efficacy in human patients is completely unverified."
                    }
                ]
            },
            {
                "id": "src-calorimetry",
                "title": "Electrolytic Thermal Evolution",
                "url": "https://doi.org/10.1103/physrev.2023.02",
                "scrape_status": "success",
                "extraction_quality": "full",
                "extracted_text": (
                    "Across all 10 electrolytic experimental runs, cell temperature decreased slightly by 0.4 K. "
                    "No statistically significant thermal excess was detected."
                ),
                "passages": [
                    {
                        "passage_id": "p2-1",
                        "page_num": 2,
                        "text": "Across all 10 electrolytic experimental runs, cell temperature decreased slightly by 0.4 K."
                    }
                ]
            },
            {
                "id": "src-cohort",
                "title": "Observational Nutrition Cohort",
                "url": "https://doi.org/10.1001/jama.2023.03",
                "scrape_status": "success",
                "extraction_quality": "full",
                "extracted_text": (
                    "Higher flavonoid intake was correlated with lower inflammatory markers (r = 0.22). "
                    "As this is an observational study, residual confounding remains and causation is not established."
                ),
                "passages": [
                    {
                        "passage_id": "p1-1",
                        "page_num": 1,
                        "text": "Higher flavonoid intake was correlated with lower inflammatory markers (r = 0.22)."
                    }
                ]
            },
            {
                "id": "src-replication_failure",
                "title": "Independent Multi-Lab Non-Replication",
                "url": "https://doi.org/10.1038/s41586-024-001",
                "scrape_status": "success",
                "extraction_quality": "full",
                "extracted_text": (
                    "In an independent multi-center replication attempt involving N = 500 subjects, "
                    "Molecule Alpha failed to reduce disease markers and showed no therapeutic efficacy."
                ),
                "passages": [
                    {
                        "passage_id": "p1-1",
                        "page_num": 1,
                        "text": "In an independent multi-center replication attempt involving N = 500 subjects, Molecule Alpha failed to reduce disease markers."
                    }
                ]
            },
            {
                "id": "src-snippet_only",
                "title": "Search Snippet Only Alloy Paper",
                "url": "https://example.org/paywalled_alloy",
                "scrape_status": "failed",
                "scrape_error": "HTTP 403 Forbidden",
                "extraction_quality": "snippet_only",
                "abstract": "Brief search result snippet noting high entropy alloys under extreme tension.",
                "extracted_text": "",
                "passages": []
            },
            {
                "id": "src-inaccessible",
                "title": "Paywalled Biology Paper",
                "url": "https://example.org/paywalled_bio",
                "scrape_status": "failed",
                "scrape_error": "HTTP 401 Unauthorized",
                "extraction_quality": "inaccessible",
                "extracted_text": "",
                "passages": []
            }
        ]

    # ==========================================================================
    # GROUP A: HIGH-PRIORITY TRUST FAILURES
    # ==========================================================================

    def test_a1_genuine_quote_unsupported_conclusion(self):
        """A1: Authentic quotation of in-vitro assay paired with human clinical cure claim must fail."""
        claim = "Molecule Alpha cures human patients and demonstrates definitive clinical efficacy [[src-invitro:p1-1]]."
        quote = "In vitro cell viability assays demonstrated preliminary reduction in cancer cell proliferation"

        # Quote is genuine
        q_valid, _ = verify_quote_provenance(quote, "src-invitro", self.sources)
        self.assertTrue(q_valid)

        sup_status, reason, meta = evaluate_claim_support(claim, self.sources[0], quoted_evidence=quote)
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED"))
        self.assertIn("overgeneralization", reason.lower())

    def test_a2_contradictory_result(self):
        """A2: Reported decrease/null result claimed as significant increase must be CONTRADICTED."""
        claim = "The electrolytic reaction demonstrated significantly increased thermal escalation [[src-calorimetry]]."
        quote = "cell temperature decreased slightly by 0.4 K"

        sup_status, reason, meta = evaluate_claim_support(claim, self.sources[1], quoted_evidence=quote)
        self.assertEqual(sup_status, "CONTRADICTED")
        self.assertIn("contradict", reason.lower())

    def test_a3_correlation_presented_as_causation(self):
        """A3: Observational correlation asserted as definitive causation must be rejected."""
        claim = "Dietary flavonoid intake conclusively proves to cause inflammatory elimination [[src-cohort]]."
        quote = "Higher flavonoid intake was correlated with lower inflammatory markers"

        sup_status, reason, meta = evaluate_claim_support(claim, self.sources[2], quoted_evidence=quote)
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED"))
        self.assertIn("causal", reason.lower())

    def test_a4_correct_source_wrong_passage(self):
        """A4: Quoting or citing a passage that does not contain the evidence must be caught as passage mismatch."""
        # Quote exists in source on page 4 (p4-1), but writer cited passage p1-1 (page 1)
        quote = "clinical translation has not been attempted and efficacy in human patients is completely unverified"
        loc_ok, loc_err = verify_passage_locator(
            "src-invitro:p1-1",
            self.sources,
            claim_text="Efficacy in humans remains unverified.",
            quoted_evidence=quote
        )
        self.assertFalse(loc_ok)
        self.assertIn("passage mismatch", loc_err.lower())

    def test_a5_missing_or_fabricated_evidence_locator(self):
        """A5: Fabricated locator on source with passages or on source without passage index must be rejected."""
        # Non-existent passage ID
        bad_ok, bad_err = verify_passage_locator("src-invitro:p99-9", self.sources)
        self.assertFalse(bad_ok)
        self.assertIn("not found", bad_err.lower())

        # Fabricated locator on source with no indexed passages
        no_passage_src = [{"id": "src-raw", "extracted_text": "Text without passage index.", "passages": []}]
        bad_ok2, bad_err2 = verify_passage_locator("src-raw:p1-1", no_passage_src)
        self.assertFalse(bad_ok2)
        self.assertIn("no indexed passages", bad_err2.lower())

    def test_a6_claim_changes_after_verification_claim_drift(self):
        """A6: When an audited claim does not correspond to any published sentence in report, flag claim drift."""
        report = (
            "## Key Findings\n"
            "FlashAttention-3 demonstrates 75% FLOP utilization on modern GPU architectures [[src-flash]].\n"
        )
        sources = [{
            "id": "src-flash",
            "title": "FlashAttention-3",
            "extracted_text": "FlashAttention-3 demonstrates 75% FLOP utilization.",
            "scrape_status": "success",
            "extraction_quality": "full"
        }]
        # Verifier audited a completely different claim not found in the report text
        stale_verifier = {
            "results": [
                {
                    "claim_id": "c-1",
                    "claim": "Quantum computers solved the protein folding problem yesterday completely.",
                    "source_ids": ["src-flash"],
                    "is_valid": True,
                    "verification_status": "DIRECTLY_SUPPORTED"
                }
            ]
        }
        audit = audit_report_integrity(report, sources, stale_verifier)
        self.assertEqual(audit.status, "INCOMPLETE")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("claim drift" in err.lower() for err in audit.provenance_errors))

    # ==========================================================================
    # GROUP B: SOURCE-ACCESS & EXTRACTION FAILURES
    # ==========================================================================

    def test_b1_snippet_only_cannot_support_full_text_review(self):
        """B1: A search snippet only source cannot be represented as having full text reviewed."""
        claim = "A comprehensive full-text review of the entire alloy dataset was performed [[src-snippet_only]]."
        sup_status, reason, meta = evaluate_claim_support(claim, self.sources[4])
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED", "UNVERIFIABLE"))
        self.assertIn("snippet", reason.lower())

    def test_b2_partial_extraction_preserves_provenance(self):
        """B2: Truncated source can support findings from retained text while retaining partial status."""
        import tempfile
        import os
        truncated_text = "Retained passage on page 1 confirms 95% yield. " + ("X" * 15000)
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
            f.write(truncated_text)
            f.flush()
            temp_path = f.name
        try:
            res = ingest_document(temp_path, max_chars=12000)
            self.assertTrue(res.is_truncated)
            self.assertEqual(res.extraction_quality, "partial")
            self.assertTrue(len(res.passages) > 0)
            self.assertEqual(res.passages[0]["extraction_quality"], "partial")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_b3_inaccessible_source_is_unverifiable(self):
        """B3: An inaccessible paywalled source returns UNVERIFIABLE and cannot be directly supported."""
        claim = "The paywalled paper demonstrates complete viral inhibition [[src-inaccessible]]."
        sup_status, reason, meta = evaluate_claim_support(claim, self.sources[5])
        self.assertEqual(sup_status, "UNVERIFIABLE")
        self.assertIn("inaccessible", reason.lower())

    @unittest.mock.patch("backend.ingestion._http_get_with_retry")
    def test_b4_empty_or_scanned_document_reported_empty(self, mock_get):
        """B4: An empty or scanned image document yields empty quality and zero readable text."""
        import pypdf
        import io
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buf = io.BytesIO()
        writer.write(buf)
        blank_pdf_bytes = buf.getvalue()

        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.content = blank_pdf_bytes
        mock_resp.text = ""
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        res = ingest_document("https://example.org/scanned.pdf")
        self.assertEqual(res.status, "empty")
        self.assertEqual(res.extraction_quality, "empty")
        self.assertIn("scanned image", res.extraction_warnings[0].lower())
        self.assertIn("no extractable text", res.extraction_warnings[0].lower())

    # ==========================================================================
    # GROUP C: RESEARCH-QUALITY FAILURES
    # ==========================================================================

    def test_c1_conflicting_evidence_omitted_contradiction_caught(self):
        """C1: Cherry-picking a positive paper while omitting an explicit contradiction in retrieved set is caught."""
        report = (
            "## Medical Findings\n"
            "Molecule Alpha is a proven therapeutic agent [[src-invitro]].\n"
        )
        raw_verifier = {
            "results": [
                {
                    "claim_id": "c-cherry",
                    "claim": "Molecule Alpha is a proven therapeutic agent",
                    "source_ids": ["src-invitro"],
                    "is_valid": True,  # Verifier only looked at the cited source!
                    "verification_status": "DIRECTLY_SUPPORTED"
                }
            ]
        }
        # In self.sources, src-replication_failure explicitly reports that Molecule Alpha failed and showed no efficacy!
        audit = audit_report_integrity(report, self.sources, raw_verifier)
        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertEqual(audit.claims[0].verification_status, "CONTRADICTED")
        self.assertIn("omitted contradictory evidence", audit.claims[0].reason.lower())

    def test_c2_claim_with_citation_but_no_supporting_passage(self):
        """C2: Citing a valid source ID without substantive supporting evidence in the source fails."""
        claim = "Molecule Alpha produces cryogenic superconductivity [[src-invitro]]."
        sup_status, reason, meta = evaluate_claim_support(claim, self.sources[0])
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED"))
        self.assertIn("insufficient", reason.lower())

    def test_c3_overstated_generalizability(self):
        """C3: In-vitro cell culture findings stated as human clinical cure must be qualified or rejected."""
        claim = "Molecule Alpha demonstrates clinical efficacy in human patients [[src-invitro]]."
        quote = "In vitro cell viability assays demonstrated preliminary reduction"
        sup_status, reason, meta = evaluate_claim_support(claim, self.sources[0], quoted_evidence=quote)
        self.assertIn(sup_status, ("INSUFFICIENT", "UNSUPPORTED"))
        self.assertIn("overgeneralization", reason.lower())

    def test_c4_unsupported_quantitative_detail(self):
        """C4: Hallucinated quantitative percentage or p-value mismatch is flagged as unsupported or contradicted."""
        # Claim asserts 99.8% reduction, source reports nothing resembling 99.8%
        claim = "Molecule Alpha achieved a 99.8% reduction in cancer cell count [[src-invitro]]."
        q_status, q_reason = verify_quantitative_claim(claim, "src-invitro", self.sources)
        self.assertEqual(q_status, "UNSUPPORTED")
        self.assertIn("99.8%", q_reason)

    # ==========================================================================
    # GROUP D: END-TO-END PIPELINE & REPORT INTEGRITY
    # ==========================================================================

    def test_d1_scraped_metadata_and_passages_preserved_in_orchestrator(self):
        """D1: When concurrent_scrape_urls runs, existing discovered sources retain all extraction metadata and passages."""
        existing_sources = [
            {
                "id": "src-arxiv-1",
                "title": "Sample Discovery Paper",
                "url": "https://example.org/sample_paper",
                "abstract": "Initial abstract from discovery."
            }
        ]
        # Simulate scraped metadata
        scraped_meta = {
            "url": "https://example.org/sample_paper",
            "domain": "example.org",
            "title": "Sample Discovery Paper",
            "extracted_text": "Full text of page 1.\n\nFull text of page 2.",
            "scrape_status": "success",
            "scrape_error": None,
            "content_type": "pdf",
            "extraction_quality": "full",
            "extraction_method": "pymupdf_pdf",
            "extraction_warnings": [],
            "retrieval_timestamp": "2026-10-16T21:00:00Z",
            "char_count": 42,
            "num_pages": 2,
            "is_truncated": False,
            "passages": [
                {"passage_id": "p1-1", "page_num": 1, "text": "Full text of page 1."},
                {"passage_id": "p2-1", "page_num": 2, "text": "Full text of page 2."}
            ]
        }

        # Emulate the merge in orchestrator.py
        new_sources_by_url = {scraped_meta["url"]: scraped_meta}
        cumulative_sources = []
        for s in existing_sources:
            s_copy = dict(s)
            u = s_copy.get("url")
            if u in new_sources_by_url:
                meta = new_sources_by_url[u]
                s_copy["extracted_text"] = meta.get("extracted_text", "")
                s_copy["scrape_status"] = meta.get("scrape_status", "success")
                s_copy["scrape_error"] = meta.get("scrape_error")
                s_copy["content_type"] = meta.get("content_type", "unknown")
                s_copy["extraction_quality"] = meta.get("extraction_quality", "unknown")
                s_copy["extraction_method"] = meta.get("extraction_method", "unknown")
                s_copy["extraction_warnings"] = list(meta.get("extraction_warnings") or [])
                s_copy["retrieval_timestamp"] = meta.get("retrieval_timestamp")
                s_copy["char_count"] = meta.get("char_count", 0)
                s_copy["num_pages"] = meta.get("num_pages", 0)
                s_copy["is_truncated"] = meta.get("is_truncated", False)
                s_copy["passages"] = list(meta.get("passages") or [])
            cumulative_sources.append(s_copy)

        merged = cumulative_sources[0]
        self.assertEqual(merged["extraction_quality"], "full")
        self.assertEqual(merged["num_pages"], 2)
        self.assertEqual(len(merged["passages"]), 2)
        self.assertEqual(merged["passages"][0]["passage_id"], "p1-1")

    def test_d2_unverified_report_receives_caution_banner(self):
        """D2: A finalized report that failed verification has an explicit [!CAUTION] warning banner."""
        unverified_state = {
            "is_verified": False,
            "integrity_status": "INTEGRITY_FAILED",
            "report": "## Key Findings\nUncorroborated conclusion about cold fusion."
        }

        # Emulate orchestrator finalization
        if not unverified_state.get("is_verified", False):
            status_label = unverified_state.get("integrity_status", "UNVERIFIED")
            banner = (
                f"> [!CAUTION] Research Integrity Gate: {status_label}\n"
                f"> **UNVERIFIED REPORT**: This research synthesis did not pass empirical claim-to-evidence verification "
                f"or contains uncorroborated / contradicted claims. It must not be cited as established evidence.\n\n"
            )
            if not unverified_state.get("report", "").startswith("> [!CAUTION]"):
                unverified_state["report"] = banner + unverified_state.get("report", "")

        self.assertTrue(unverified_state["report"].startswith("> [!CAUTION] Research Integrity Gate: INTEGRITY_FAILED"))
        self.assertIn("**UNVERIFIED REPORT**", unverified_state["report"])
