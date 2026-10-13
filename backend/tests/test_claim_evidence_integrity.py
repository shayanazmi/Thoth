"""
Deterministic regression tests for Prompt 16:
Claim-to-evidence verification, deterministic provenance and quantitative checks,
deterministic bibliography generation, and the fail-closed research integrity gate.
"""

import unittest
import json
import tempfile
import os
import shutil
from unittest.mock import patch, MagicMock, AsyncMock

from backend.agents import (
    ReportClaim,
    EvidencePassage,
    ReportIntegrityResult,
    VerificationResult,
    FactVerificationReport,
    CriticScore,
    verifier_chain,
    safe_extract_json
)
from backend.intellectual_rigour.integrity_gate import (
    verify_source_identity,
    verify_quote_provenance,
    verify_identifier_consistency,
    verify_quantitative_claim,
    verify_claim_coverage,
    audit_report_integrity,
    generate_deterministic_bibliography
)
from backend.pipeline import verifier_node, writer_node
from backend.orchestrator import (
    stream_research_pipeline,
    persist_turn_to_vault,
    create_initial_state
)


class TestClaimEvidenceVerificationAndIntegrityGate(unittest.TestCase):

    def setUp(self):
        self.sources = [
            {
                "id": "src-quantum_entanglement",
                "title": "Quantum Entanglement in Microcavities",
                "url": "https://nature.com/articles/s41586-024-00123",
                "authors": ["Alice Smith", "Bob Jones"],
                "abstract": "We observe robust qubit entanglement in high-Q optical resonators.",
                "extracted_text": "Experimental results demonstrate that single atoms achieved 99.8% fidelity in microcavity traps with coherence time of 1.2 seconds.",
                "doi": "10.1038/s41586-024-00123",
                "arxiv_id": "2401.12345",
                "pmid": "38800001",
                "scrape_status": "success"
            },
            {
                "id": "src-materials_science",
                "title": "Superconducting Resonator Fabrication",
                "url": "https://journals.aps.org/prb/abstract/10.1103/PhysRevB.99.001",
                "authors": ["Carol White"],
                "abstract": "High-purity niobium films reduce dielectric losses.",
                "extracted_text": "Dielectric loss tangent was measured at 1.4e-6 at 15 mK.",
                "doi": "10.1103/PhysRevB.99.001",
                "scrape_status": "success"
            }
        ]

    # Test 1: A factual claim supported by a genuine, matching source passage
    def test_1_factual_claim_supported_by_genuine_matching_passage(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Single atoms achieved 99.8% fidelity in microcavity traps.",
                    "claim_type": "factual_finding",
                    "source_ids": ["src-quantum_entanglement"],
                    "supporting_source_id": "src-quantum_entanglement",
                    "quoted_evidence": "single atoms achieved 99.8% fidelity in microcavity traps",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "Single atoms achieved 99.8% fidelity in microcavity traps [[src-quantum_entanglement]]."
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "PASSED")
        self.assertTrue(audit.is_verified)
        self.assertEqual(audit.directly_supported_count, 1)
        self.assertEqual(len(audit.provenance_errors), 0)
        self.assertTrue(audit.claims[0].provenance_verified)

    # Test 2: A valid source ID with an invented quotation
    def test_2_valid_source_id_with_invented_quotation(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Laser output exceeded 100 megawatts.",
                    "claim_type": "factual_finding",
                    "source_ids": ["src-quantum_entanglement"],
                    "supporting_source_id": "src-quantum_entanglement",
                    "quoted_evidence": "laser output exceeded 100 megawatts continuous wave power",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "Laser output exceeded 100 megawatts [[src-quantum_entanglement]]."
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertFalse(audit.claims[0].provenance_verified)
        self.assertTrue(any("Quote provenance failure" in err for err in audit.provenance_errors))

    # Test 3: A fabricated or unknown source ID
    def test_3_fabricated_or_unknown_source_id(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Dark matter particles were detected.",
                    "claim_type": "factual_finding",
                    "source_ids": ["src-fabricated_cosmology_2026"],
                    "supporting_source_id": "src-fabricated_cosmology_2026",
                    "quoted_evidence": "Dark matter detected",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "Dark matter particles were detected [[src-fabricated_cosmology_2026]]."
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("Unknown or fabricated source ID" in err for err in audit.provenance_errors))

    # Test 4: A real source whose text is irrelevant to the attributed claim
    def test_4_real_source_whose_text_is_irrelevant_to_claim(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Cognitive behavioral therapy cured treatment-resistant depression.",
                    "claim_type": "factual_finding",
                    "source_ids": ["src-quantum_entanglement"],
                    "supporting_source_id": "",
                    "quoted_evidence": "",
                    "verification_status": "UNSUPPORTED",
                    "is_valid": False,
                    "reason_if_failed": "Source pertains strictly to quantum optics and microcavities, containing zero clinical depression data."
                }
            ]
        })

        report_text = "Cognitive behavioral therapy cured depression [[src-quantum_entanglement]]."
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertEqual(audit.unsupported_or_contradicted_count, 1)

    # Test 5: A DOI or arXiv identifier that conflicts with the corresponding source record
    def test_5_doi_or_arxiv_identifier_conflicts_with_source_record(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Findings published in Nature under DOI 10.1145/3318464.3389700 and arXiv:2605.05444.",
                    "claim_type": "factual_finding",
                    "source_ids": ["src-quantum_entanglement"],
                    "supporting_source_id": "src-quantum_entanglement",
                    "quoted_evidence": "Experimental results demonstrate",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "Findings published under DOI 10.1145/3318464.3389700 [[src-quantum_entanglement]]."
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("DOI conflict" in err for err in audit.provenance_errors))

    # Test 6: An unsupported quantitative claim
    def test_6_unsupported_quantitative_claim(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "The algorithm achieved an AUC of 0.82-0.89 across clinical trials.",
                    "claim_type": "empirical_metric",
                    "source_ids": ["src-quantum_entanglement"],
                    "supporting_source_id": "src-quantum_entanglement",
                    "quoted_evidence": "",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "The algorithm achieved an AUC of 0.82-0.89 [[src-quantum_entanglement]]."
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("AUC assertion" in expl for expl in audit.failure_explanations))

    # Test 7: A contradictory numerical result (correlation r = 0.48 vs r = -0.12)
    def test_7_contradictory_numerical_result(self):
        source_with_neg_corr = {
            "id": "src-economic_sentiment",
            "title": "Economic Sentiment and Market Returns",
            "url": "https://finance-journal.org/paper",
            "extracted_text": "We found an inverse correlation between consumer fear and equity returns with r = -0.12 across all quarters."
        }
        all_sources = self.sources + [source_with_neg_corr]

        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Market returns exhibited strong positive correlation with r = 0.48.",
                    "claim_type": "empirical_metric",
                    "source_ids": ["src-economic_sentiment"],
                    "supporting_source_id": "src-economic_sentiment",
                    "quoted_evidence": "r = -0.12",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "Market returns exhibited strong correlation r = 0.48 [[src-economic_sentiment]]."
        audit = audit_report_integrity(report_text, all_sources, raw_response)

        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("Contradictory correlation direction" in expl for expl in audit.failure_explanations))

    # Test 8: A correct numerical value attached to the wrong metric
    def test_8_correct_numerical_value_attached_to_wrong_metric(self):
        source_with_p_val = {
            "id": "src-stats_test",
            "title": "Statistical Significance in Trials",
            "url": "https://stats.org/paper",
            "extracted_text": "The null hypothesis could not be rejected as the significance test yielded p = 0.48."
        }
        all_sources = self.sources + [source_with_p_val]

        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "The asset class yielded correlation r = 0.48.",
                    "claim_type": "empirical_metric",
                    "source_ids": ["src-stats_test"],
                    "supporting_source_id": "src-stats_test",
                    "quoted_evidence": "p = 0.48",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "The asset class yielded correlation r = 0.48 [[src-stats_test]]."
        audit = audit_report_integrity(report_text, all_sources, raw_response)

        self.assertEqual(audit.status, "FAILED")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("Metric mismatch" in expl for expl in audit.failure_explanations))

    # Test 9: An empirical claim with missing evidence (failed scrape / no text)
    def test_9_empirical_claim_with_missing_evidence(self):
        unscraped_source = {
            "id": "src-paywalled_clinical_trial",
            "title": "Clinical Trial Phase 3",
            "url": "https://paywall.com/trial",
            "extracted_text": "",
            "abstract": "",
            "snippet": "",
            "scrape_status": "failed",
            "scrape_error": "HTTP 403 Forbidden"
        }
        all_sources = self.sources + [unscraped_source]

        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Drug X reduced mortality by 40% in phase 3 trial.",
                    "claim_type": "empirical_metric",
                    "source_ids": ["src-paywalled_clinical_trial"],
                    "supporting_source_id": "src-paywalled_clinical_trial",
                    "quoted_evidence": "Drug X reduced mortality by 40%",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "Drug X reduced mortality by 40% [[src-paywalled_clinical_trial]]."
        audit = audit_report_integrity(report_text, all_sources, raw_response)

        self.assertIn(audit.status, ("FAILED", "INCOMPLETE"))
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("no substantive retained text" in err for err in audit.provenance_errors))

    # Test 10: A qualified theoretical synthesis grounded in multiple sources
    def test_10_qualified_theoretical_synthesis_grounded_in_multiple_sources(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Integrating low-loss niobium resonators with optical microcavity traps offers a viable pathway for hybrid quantum interconnects.",
                    "claim_type": "theoretical_synthesis",
                    "source_ids": ["src-quantum_entanglement", "src-materials_science"],
                    "supporting_source_id": "src-quantum_entanglement",
                    "quoted_evidence": "",
                    "verification_status": "QUALIFIED_SUPPORT",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        report_text = "Integrating low-loss niobium resonators with optical traps offers hybrid interconnects [[src-quantum_entanglement]] [[src-materials_science]]."
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "PASSED")
        self.assertTrue(audit.is_verified)
        self.assertEqual(audit.qualified_count, 1)
        self.assertEqual(audit.claims[0].disposition, "qualify")

    # Test 11: Malformed or incomplete structured verification output
    def test_11_malformed_structured_verification_output(self):
        garbled_output = "I am an LLM and I think this report is good { broken json..."
        report_text = "Some substantive report content discussing quantum mechanics and physics."
        audit = audit_report_integrity(report_text, self.sources, garbled_output)

        self.assertEqual(audit.status, "INCOMPLETE")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("malformed" in expl for expl in audit.failure_explanations))

    # Test 12: A report containing factual claims that are not represented in the audit
    def test_12_report_containing_claims_not_represented_in_audit(self):
        raw_response = json.dumps({
            "results": [
                {
                    "claim_id": "claim-1",
                    "claim": "Single atoms achieved 99.8% fidelity.",
                    "claim_type": "factual_finding",
                    "source_ids": ["src-quantum_entanglement"],
                    "supporting_source_id": "src-quantum_entanglement",
                    "quoted_evidence": "single atoms achieved 99.8% fidelity in microcavity traps",
                    "verification_status": "DIRECTLY_SUPPORTED",
                    "is_valid": True,
                    "reason_if_failed": ""
                }
            ]
        })

        # Report cites BOTH src-quantum_entanglement AND src-materials_science, but audit completely omitted materials_science!
        report_text = (
            "## Key Findings\n"
            "- Single atoms achieved 99.8% fidelity [[src-quantum_entanglement]].\n"
            "- Dielectric loss was measured at 1.4e-6 [[src-materials_science]]."
        )
        audit = audit_report_integrity(report_text, self.sources, raw_response)

        self.assertEqual(audit.status, "INCOMPLETE")
        self.assertFalse(audit.is_verified)
        self.assertTrue(any("src-materials_science" in err for err in audit.provenance_errors))

    # Test 13: A Writer attempting to cite a nonexistent source
    def test_13_writer_attempting_to_cite_nonexistent_source(self):
        report_with_fake_citation = "Quantum supremacy was achieved in 2026 [[src-fake_quantum_computer]]."
        final_report, deduped, unresolved = generate_deterministic_bibliography(report_with_fake_citation, self.sources)

        self.assertIn("src-fake_quantum_computer", unresolved)
        self.assertEqual(len(deduped), 0)

    # Test 14: A hallucinated bibliography entry
    def test_14_hallucinated_bibliography_entry_stripped(self):
        report_with_hallucinated_bib = (
            "Superconducting qubits utilize niobium films [[src-materials_science]].\n\n"
            "## References\n"
            "1. Fake Author (2025). The Imaginary Universe. Nature 999:123.\n"
            "2. Fabricated Paper on AI. Journal of Hallucinations."
        )

        final_report, deduped, unresolved = generate_deterministic_bibliography(report_with_hallucinated_bib, self.sources)

        self.assertNotIn("The Imaginary Universe", final_report)
        self.assertNotIn("Journal of Hallucinations", final_report)
        self.assertIn("Superconducting Resonator Fabrication", final_report)
        self.assertIn("Carol White", final_report)
        self.assertEqual(len(deduped), 1)

    # Test 15: Duplicate bibliography records for same confirmed persistent identifier
    def test_15_duplicate_bibliography_records_deduplicated(self):
        duplicate_sources = self.sources + [
            {
                "id": "src-quantum_entanglement_mirror",
                "title": "Quantum Entanglement in Microcavities (Mirror)",
                "url": "https://mirror.nature.com/articles/s41586-024-00123",
                "doi": "10.1038/s41586-024-00123",  # Identical DOI
                "authors": ["Alice Smith", "Bob Jones"]
            }
        ]

        report_text = (
            "We cite paper A [[src-quantum_entanglement]] and paper B [[src-quantum_entanglement_mirror]]."
        )
        final_report, deduped, unresolved = generate_deterministic_bibliography(report_text, duplicate_sources)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(final_report.count("Quantum Entanglement in Microcavities"), 1)

    # Test 16: A report that fails verification after all allowed retries
    def test_16_report_fails_verification_after_all_allowed_retries(self):
        mock_search = MagicMock(return_value={"search_results": "Data", "cumulative_sources": self.sources})
        mock_snowball = MagicMock(return_value={"cumulative_sources": self.sources})
        mock_writer = MagicMock(return_value={"report": "Perpetual motion engine operates with 120% efficiency [[src-quantum_entanglement]].", "attempt": 1})

        mock_ver_crit = AsyncMock(return_value=(
            {
                "verifier_feedback": "- CLAIM: Perpetual motion engine -> Thermodynamically impossible",
                "verification_results": [{"claim": "Perpetual motion", "is_valid": False}],
                "integrity_status": "FAILED",
                "is_verified": False,
                "integrity_result": {"status": "FAILED", "failure_explanations": ["Thermodynamically impossible"]}
            },
            {
                "feedback": "Poor evidence",
                "score": 3.4
            }
        ))

        mock_mm = MagicMock(return_value={"mindmap": {"nodes": [], "edges": []}})
        mock_fu = MagicMock(return_value={"follow_up_questions": []})

        with patch("backend.orchestrator.search_node", mock_search), \
             patch("backend.orchestrator.snowball_node", mock_snowball), \
             patch("backend.orchestrator.concurrent_scrape_urls", return_value=("Scraped", self.sources)), \
             patch("backend.orchestrator.writer_node", mock_writer), \
             patch("backend.orchestrator.concurrent_verifier_and_critic", mock_ver_crit), \
             patch("backend.orchestrator.mindmap_node", mock_mm), \
             patch("backend.orchestrator.follow_up_node", mock_fu):

            final_state = None
            for node, update, state in stream_research_pipeline(topic="Perpetual Motion", max_retries=1):
                final_state = state

            self.assertIsNotNone(final_state)
            self.assertIn(final_state["integrity_status"], ("INTEGRITY_FAILED", "FAILED"))
            self.assertFalse(final_state["is_verified"])

    # Test 17: Proof that a high Critic score cannot override integrity failure
    def test_17_critic_high_score_cannot_override_integrity_failure(self):
        mock_search = MagicMock(return_value={"search_results": "Data", "cumulative_sources": self.sources})
        mock_snowball = MagicMock(return_value={"cumulative_sources": self.sources})
        mock_writer = MagicMock(return_value={"report": "Fabricated trial result asserting 100% cure rate [[src-quantum_entanglement]].", "attempt": 1})

        mock_ver_crit = AsyncMock(return_value=(
            {
                "verifier_feedback": "- CLAIM: Fabricated trial result -> Fabricated claim",
                "verification_results": [{"claim": "Fabricated trial result", "is_valid": False}],
                "integrity_status": "FAILED",
                "is_verified": False,
                "integrity_result": {"status": "FAILED", "failure_explanations": ["Fabricated claim"]}
            },
            {
                "feedback": "Outstanding writing style",
                "score": 9.8
            }
        ))

        mock_mm = MagicMock(return_value={"mindmap": {"nodes": [], "edges": []}})
        mock_fu = MagicMock(return_value={"follow_up_questions": []})

        with patch("backend.orchestrator.search_node", mock_search), \
             patch("backend.orchestrator.snowball_node", mock_snowball), \
             patch("backend.orchestrator.concurrent_scrape_urls", return_value=("Scraped", self.sources)), \
             patch("backend.orchestrator.writer_node", mock_writer), \
             patch("backend.orchestrator.concurrent_verifier_and_critic", mock_ver_crit), \
             patch("backend.orchestrator.mindmap_node", mock_mm), \
             patch("backend.orchestrator.follow_up_node", mock_fu):

            final_state = None
            for node, update, state in stream_research_pipeline(topic="Fabricated Breakthrough", max_retries=1):
                final_state = state

            # Integrity gate is FAIL-CLOSED: Critic 9.8 has ZERO authority to override!
            self.assertEqual(final_state["score"], 9.8)
            self.assertIn(final_state["integrity_status"], ("INTEGRITY_FAILED", "FAILED"))
            self.assertFalse(final_state["is_verified"])

            # Integrity gate is FAIL-CLOSED: Critic 9.8 has ZERO authority to override!
            self.assertEqual(final_state["score"], 9.8)
            self.assertIn(final_state["integrity_status"], ("INTEGRITY_FAILED", "FAILED"))
            self.assertFalse(final_state["is_verified"])

    # Test 18: Proof that a failed report cannot be recorded as research-verified in the Vault
    def test_18_failed_report_not_recorded_as_verified_in_vault(self):
        temp_dir = tempfile.mkdtemp()
        vault_dir = os.path.join(temp_dir, "vault")
        db_path = os.path.join(temp_dir, "vault.db")

        try:
            unverified_state = {
                "topic": "Unverified Clinical Trial",
                "report": "Unverified draft content...",
                "cumulative_sources": self.sources,
                "score": 9.5,
                "integrity_status": "INTEGRITY_FAILED",
                "is_verified": False,
                "verification_results": [
                    {
                        "claim": "Fake claim",
                        "is_valid": False,
                        "supporting_source_id": ""
                    }
                ]
            }

            persist_turn_to_vault(unverified_state, vault_dir=vault_dir, db_path=db_path)

            from backend.memory.vault import read_note
            topic_note = read_note("topic-unverified_clinical_trial", vault_dir=vault_dir)

            self.assertIsNotNone(topic_note)
            self.assertFalse(topic_note.frontmatter.get("verified"))
            self.assertEqual(topic_note.frontmatter.get("confidence"), 0.0)
            self.assertEqual(topic_note.frontmatter.get("integrity_status"), "INTEGRITY_FAILED")
            self.assertIn("Research Integrity Gate: INTEGRITY_FAILED", topic_note.content)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # Test 19: Successful completion preserves frontend SSE contract
    def test_19_successful_completion_preserves_frontend_contract(self):
        state = create_initial_state(topic="Quantum Mechanics")
        self.assertIn("integrity_status", state)
        self.assertIn("is_verified", state)
        self.assertIn("integrity_result", state)

        # Simulate clean_state from web_server.py
        clean_state = {
            "topic": state.get("topic", ""),
            "report": state.get("report", ""),
            "score": state.get("score", 0.0),
            "attempt": state.get("attempt", 0),
            "verification_results": state.get("verification_results", []),
            "mindmap": state.get("mindmap", {}),
            "cumulative_sources": state.get("cumulative_sources", []),
            "follow_up_questions": state.get("follow_up_questions", []),
            "chat_turns": state.get("chat_turns", []),
            "conversation_summary": state.get("conversation_summary", ""),
            "integrity_status": state.get("integrity_status", "PENDING"),
            "is_verified": state.get("is_verified", False),
            "integrity_result": state.get("integrity_result", {})
        }

        # Check all required keys exist
        for key in ["topic", "report", "score", "verification_results", "integrity_status", "is_verified"]:
            self.assertIn(key, clean_state)

    # Test 20: Regression coverage for Prompt 15 source provenance, scraping, and Truth Guard inputs
    def test_20_prompt_15_source_provenance_and_truth_guard_inputs(self):
        state = {
            "topic": "Microcavity Optics",
            "report": "Single atoms achieved 99.8% fidelity in microcavity traps [[src-quantum_entanglement]].",
            "cumulative_sources": self.sources
        }

        captured_inputs = {}
        mock_verifier = MagicMock()
        def mock_verifier_invoke(inputs):
            captured_inputs.update(inputs)
            return json.dumps({
                "results": [
                    {
                        "claim_id": "c1",
                        "claim": "Single atoms achieved 99.8% fidelity in microcavity traps.",
                        "claim_type": "factual_finding",
                        "source_ids": ["src-quantum_entanglement"],
                        "supporting_source_id": "src-quantum_entanglement",
                        "quoted_evidence": "single atoms achieved 99.8% fidelity in microcavity traps",
                        "verification_status": "DIRECTLY_SUPPORTED",
                        "is_valid": True,
                        "reason_if_failed": ""
                    }
                ]
            })
        mock_verifier.invoke.side_effect = mock_verifier_invoke

        with patch("backend.pipeline.verifier_chain", mock_verifier):
            res = verifier_node(state)

            self.assertIn("sources", captured_inputs)
            sources_text = captured_inputs["sources"]
            self.assertIn("[src-quantum_entanglement]", sources_text)
            self.assertIn("DOI: 10.1038/s41586-024-00123", sources_text)
            self.assertIn("Alice Smith, Bob Jones", sources_text)
            self.assertEqual(res["integrity_status"], "PASSED")
            self.assertEqual(res["verifier_feedback"], "")


if __name__ == "__main__":
    unittest.main()
