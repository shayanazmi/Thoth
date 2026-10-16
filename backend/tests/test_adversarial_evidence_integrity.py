"""
Comprehensive adversarial and integration test suite for the Evidence Integrity
Verification and Regression Gate in THOTH.

Covers:
  1. Explicit support.
  2. Explicit contradiction.
  3. Right keywords but no established relationship.
  4. Omitted negation / reversed direction.
  5. Statistically non-significant result claimed as demonstrated effect.
  6. Correlation reported, claimed as causation.
  7. Narrower population (in vitro / murine) claimed as human general.
  8. Two sources disagree on the empirical finding.
  9. Quantitative value, multiplier, or sample size mismatch.
  10. Quotation taken out of context from a refutation or myth debunking.
  11. Missing, truncated, or misattributed passage.
  12. Pipeline integration: Writer receives later page passages.
  13. Pipeline integration: Verifier evaluates actual cited evidence with locators.
  14. Pipeline integration: Contradicted claims cannot pass integrity gate or reach verified status.
  15. Pipeline integration: Retry loop incorporates verifier feedback with bounded attempts.
  16. Pipeline integration: Deterministic bibliography preserves provenance locators and identifiers.
"""

import pytest
import json
from typing import Dict, Any, List

from backend.ingestion import (
    create_bounded_passages,
    select_representative_passages,
    format_passages_for_context,
)
from backend.agents import (
    EvidencePassage,
    ReportClaim,
    ReportIntegrityResult,
)
from backend.intellectual_rigour.integrity_gate import (
    evaluate_claim_support,
    audit_report_integrity,
    verify_quote_provenance,
    verify_quantitative_claim,
    generate_deterministic_bibliography,
)


# ==============================================================================
# SECTION 1: ADVERSARIAL EVIDENCE CASES
# ==============================================================================

def test_adv_1_explicit_support():
    """Case 1: Source explicitly corroborates the claim."""
    source = {
        "id": "src-crispr_cas9",
        "title": "High-Efficiency Base Editing",
        "url": "https://doi.org/10.1038/s41586-023-0001",
        "scrape_status": "success",
        "extracted_text": (
            "Our optimized adenine base editor achieved 82% target nucleotide conversion "
            "with undetectable bystander mutations across ten genomic loci."
        )
    }
    claim = "The optimized adenine base editor achieved 82% target nucleotide conversion."
    status, reason, meta = evaluate_claim_support(claim, source)
    assert status == "SUPPORTED"
    assert "82%" in reason or "corroborated" in reason.lower()


def test_adv_2_explicit_contradiction():
    """Case 2: Source explicitly contradicts the claim."""
    source = {
        "id": "src-stat_trial",
        "title": "Clinical Efficacy of Statin Y",
        "url": "https://doi.org/10.1016/j.lancet.2023.01.001",
        "scrape_status": "success",
        "extracted_text": (
            "Contrary to prior hypotheses, treatment with Statin Y showed no evidence that it "
            "reduces arterial plaque volume in high-risk cardiovascular patients."
        )
    }
    claim = "Treatment with Statin Y reduces arterial plaque volume in high-risk patients."
    status, reason, meta = evaluate_claim_support(claim, source)
    assert status == "CONTRADICTED"
    assert "no evidence that" in reason.lower() or "contradicts" in reason.lower()


def test_adv_3_right_keywords_without_relationship():
    """Case 3: Right keywords appear, but text does not establish the claimed relationship."""
    source = {
        "id": "src-pilot_study",
        "title": "Aviation Human Factors",
        "url": "https://example.org/aviation",
        "scrape_status": "success",
        "extracted_text": (
            "We surveyed commercial airline pilots regarding Model X flight deck displays. "
            "Future empirical studies are required to determine cognitive workload effects."
        )
    }
    # Claim asserts a demonstrated empirical finding that displays increased cognitive workload
    claim = "Model X flight deck displays increased cognitive workload in commercial pilots."
    status, reason, meta = evaluate_claim_support(claim, source)
    # Must be marked INSUFFICIENT, not falsely marked SUPPORTED
    assert status == "INSUFFICIENT"
    assert "inconclusive" in reason.lower() or "insufficient" in reason.lower()


def test_adv_4_claim_omits_negation_or_reverses_direction():
    """Case 4: Claim omits negation or reverses finding direction."""
    source = {
        "id": "src-oncology_trial",
        "title": "Kinase Inhibitor in Melanoma",
        "url": "https://example.org/oncology",
        "scrape_status": "success",
        "extracted_text": (
            "In our Phase II trial, the novel kinase inhibitor failed to prevent tumor progression "
            "in patients with BRAF V600E mutations."
        )
    }
    # Omitted negation:
    claim = "The novel kinase inhibitor prevented tumor progression in patients with BRAF mutations."
    status, reason, _ = evaluate_claim_support(claim, source)
    assert status == "CONTRADICTED"
    assert "failed to" in reason.lower() or "contradicts" in reason.lower()

    # Reversed direction: source asserts significant improvement, claim asserts it failed
    pos_source = {
        "id": "src-pos_oncology",
        "title": "Targeted Therapy",
        "url": "https://example.org/pos",
        "scrape_status": "success",
        "extracted_text": "The targeted therapy significantly reduced tumor progression by 45%."
    }
    rev_claim = "The targeted therapy failed to reduce tumor progression."
    status_rev, reason_rev, _ = evaluate_claim_support(rev_claim, pos_source)
    assert status_rev == "CONTRADICTED"


def test_adv_5_non_significant_result_claimed_as_effect():
    """Case 5: Paper reports non-significant result, claim asserts demonstrated effect."""
    source = {
        "id": "src-sepsis_trial",
        "title": "Antioxidant Therapy in Sepsis",
        "url": "https://example.org/sepsis",
        "scrape_status": "success",
        "extracted_text": (
            "Patients receiving high-dose Vitamin C showed no statistically significant difference "
            "in 28-day mortality (p = 0.38) compared to placebo."
        )
    }
    claim = "High-dose Vitamin C demonstrated a statistically significant reduction in 28-day mortality."
    status, reason, _ = evaluate_claim_support(claim, source)
    assert status == "CONTRADICTED"
    assert "significant" in reason.lower() or "contradicts" in reason.lower()


def test_adv_6_correlation_reported_claimed_as_causation():
    """Case 6: Source reports correlation, claim asserts causation."""
    source = {
        "id": "src-epidemiology",
        "title": "Dietary Habits and Cardiovascular Health",
        "url": "https://example.org/diet_epi",
        "scrape_status": "success",
        "extracted_text": (
            "Moderate coffee intake was correlated with lower all-cause mortality; however, "
            "this correlation does not prove causation and unmeasured lifestyle confounders may exist."
        )
    }
    claim = "Moderate coffee intake directly causes lower all-cause mortality."
    status, reason, _ = evaluate_claim_support(claim, source)
    assert status == "CONTRADICTED"
    assert "causation" in reason.lower() or "contradicts" in reason.lower()


def test_adv_7_narrower_population_claimed_as_general():
    """Case 7: Source supports narrower model (in vitro/murine), claim generalizes to humans."""
    source = {
        "id": "src-preclinical",
        "title": "Preclinical Evaluation of Compound K",
        "url": "https://example.org/compk",
        "scrape_status": "success",
        "extracted_text": (
            "Compound K demonstrated potent cytotoxic activity exclusively in in-vitro murine "
            "leukemia cell cultures and has not been evaluated in humans."
        )
    }
    claim = "Compound K is an effective therapeutic for human leukemia patients."
    status, reason, _ = evaluate_claim_support(claim, source)
    assert status == "CONTRADICTED"
    assert "humans" in reason.lower() or "narrow" in reason.lower() or "contradicts" in reason.lower()


def test_adv_8_two_sources_disagree():
    """Case 8: Two cited sources disagree on the empirical finding."""
    source_a = {
        "id": "src-trial_boston",
        "title": "Boston Trial of Drug M",
        "url": "https://example.org/boston",
        "scrape_status": "success",
        "extracted_text": "Our randomized trial showed Drug M significantly improved patient mobility scores."
    }
    source_b = {
        "id": "src-trial_oxford",
        "title": "Oxford Multi-Center Trial of Drug M",
        "url": "https://example.org/oxford",
        "scrape_status": "success",
        "extracted_text": "In a rigorous replicate study, Drug M failed to improve patient mobility scores."
    }
    claim = "Drug M significantly improved patient mobility scores."

    raw_verifier = {
        "results": [
            {
                "claim_id": "claim-disagree-1",
                "claim": claim,
                "source_ids": ["src-trial_boston", "src-trial_oxford"],
                "supporting_source_id": "src-trial_boston",
                "is_valid": True,
                "verification_status": "DIRECTLY_SUPPORTED"
            }
        ]
    }
    report = f"## Mobility\n{claim} [[src-trial_boston]] [[src-trial_oxford]]"
    audit = audit_report_integrity(report, [source_a, source_b], raw_verifier)

    # Must detect the disagreement and fail the audit
    assert audit.status == "FAILED"
    assert audit.is_verified is False
    assert audit.claims[0].support_status == "CONTRADICTED"
    assert "disagreement" in audit.claims[0].reason.lower() or "contradicts" in audit.claims[0].reason.lower()


def test_adv_9_quantitative_value_unit_multiplier_mismatch():
    """Case 9: Quantitative claim changes percentage, multiplier, or sample size."""
    # Sub-case A: Percentage change (15% in source vs 75% in claim)
    source_pct = {
        "id": "src-cache_perf",
        "title": "Cache Compression",
        "url": "https://example.org/cache",
        "scrape_status": "success",
        "extracted_text": "Algorithm C reduced memory footprint by 15% across SPEC benchmarks."
    }
    claim_pct = "Algorithm C reduced memory footprint by 75%."
    status_pct, reason_pct = verify_quantitative_claim(claim_pct, "src-cache_perf", [source_pct])
    assert status_pct == "CONTRADICTED"
    assert "75" in reason_pct and "15" in reason_pct

    # Sub-case B: Multiplier speedup mismatch (1.5x in source vs 10x in claim)
    source_mult = {
        "id": "src-gpu_speed",
        "title": "GPU Acceleration",
        "url": "https://example.org/gpu",
        "scrape_status": "success",
        "extracted_text": "Our kernel achieved 1.5x speedup compared tocuBLAS."
    }
    claim_mult = "Our kernel achieved 10x speedup compared to cuBLAS."
    status_mult, reason_mult = verify_quantitative_claim(claim_mult, "src-gpu_speed", [source_mult])
    assert status_mult == "CONTRADICTED"
    assert "10" in reason_mult and "1.5" in reason_mult

    # Sub-case C: Sample size mismatch (N = 100 in source vs N = 10,000 in claim)
    source_n = {
        "id": "src-survey_n",
        "title": "Clinical Cohort",
        "url": "https://example.org/n",
        "scrape_status": "success",
        "extracted_text": "We enrolled a cohort of n = 100 participants."
    }
    claim_n = "In a multicenter cohort of n = 10000 participants."
    status_n, reason_n = verify_quantitative_claim(claim_n, "src-survey_n", [source_n])
    assert status_n == "CONTRADICTED"
    assert "10000" in reason_n and "100" in reason_n


def test_adv_10_quotation_taken_out_of_context():
    """Case 10: Quotation is correct verbatim but taken out of context from a myth refutation."""
    source = {
        "id": "src-vaccine_review",
        "title": "Immunization Safety Review",
        "url": "https://example.org/vaccine",
        "scrape_status": "success",
        "extracted_text": (
            "It is a dangerous myth that MMR vaccines cause autism; comprehensive worldwide "
            "epidemiological data have disproven this hypothesis."
        )
    }
    # Verbatim substring from the source, but completely inverting meaning
    claim = "MMR vaccines cause autism."
    quoted_evidence = "MMR vaccines cause autism"

    status, reason, meta = evaluate_claim_support(
        claim_text=claim,
        source_record=source,
        quoted_evidence=quoted_evidence
    )
    assert status == "CONTRADICTED"
    assert "myth" in reason.lower() or "out of context" in reason.lower() or "contradicts" in reason.lower()


def test_adv_11_missing_truncated_misattributed_passage():
    """Case 11: Quoted passage is missing, truncated, or misattributed to another source."""
    source_a = {
        "id": "src-quantum_a",
        "title": "Quantum Optics",
        "url": "https://example.org/qa",
        "scrape_status": "success",
        "extracted_text": "Superconducting qubits maintain coherence for 100 microseconds."
    }
    source_b = {
        "id": "src-bio_b",
        "title": "Cell Biology",
        "url": "https://example.org/bb",
        "scrape_status": "success",
        "extracted_text": "Mitochondria regulate ATP synthesis in mammalian cells."
    }

    # Quotation from source_a misattributed to source_b
    ok, err = verify_quote_provenance(
        quote="Superconducting qubits maintain coherence for 100 microseconds.",
        source_id="src-bio_b",
        cumulative_sources=[source_a, source_b]
    )
    assert ok is False
    assert "could not be located" in err.lower()

    # Completely invented quotation on source_a
    ok_inv, err_inv = verify_quote_provenance(
        quote="Qubits achieved 100% fidelity without error correction.",
        source_id="src-quantum_a",
        cumulative_sources=[source_a, source_b]
    )
    assert ok_inv is False


# ==============================================================================
# SECTION 2: PIPELINE INTEGRATION VERIFICATION
# ==============================================================================

def test_integration_writer_receives_later_pages():
    """Verify that writer_node catalog receives representative passages from later pages."""
    # 4-page PDF text
    pdf_text = (
        "[Page 1]\nIntroduction to High-Energy Physics.\n\n"
        "[Page 2]\nDetector design and drift chamber wire alignments.\n\n"
        "[Page 3]\nLuminosity calibration and beam background veto filters.\n\n"
        "[Page 4]\nFinal Measurements: The Higgs boson decay to muon pairs was observed at 5.2 sigma significance."
    )
    passages = create_bounded_passages(pdf_text, content_type="pdf", source_uri="https://cern.ch/paper")
    selected = select_representative_passages(passages, max_chars=1600, max_passages=3)
    formatted = format_passages_for_context(selected, max_chars=1600)

    # Must contain page locator and page 4 discovery
    assert "Page 4" in formatted
    assert "5.2 sigma significance" in formatted


def test_integration_verifier_evaluates_actual_evidence():
    """Verify that verifier evaluates representative multi-page passages with exact locators."""
    pdf_text = (
        "[Page 1]\nSurvey of transformer attention mechanisms.\n\n"
        "[Page 3]\nEmpirical Evaluation: FlashAttention-3 achieves 75% FLOP utilization on H100 SXM5."
    )
    passages = create_bounded_passages(pdf_text, content_type="pdf", source_uri="https://arxiv.org/abs/2407.0001")
    source_record = {
        "id": "src-flash3",
        "title": "FlashAttention-3",
        "url": "https://arxiv.org/abs/2407.0001",
        "scrape_status": "success",
        "passages": passages,
        "extracted_text": pdf_text
    }

    claim = "FlashAttention-3 achieves 75% FLOP utilization on H100 hardware."
    status, reason, meta = evaluate_claim_support(claim, source_record)
    assert status == "SUPPORTED"
    assert "75%" in reason or "corroborated" in reason.lower()


def test_integration_contradicted_claims_cannot_pass_vault():
    """Verify that contradicted or unresolved claims cannot receive status PASSED."""
    contradicting_source = {
        "id": "src-replication_failed",
        "title": "Failed Replication of Room-Temperature Superconductivity",
        "url": "https://doi.org/10.1038/nature12345",
        "scrape_status": "success",
        "extracted_text": "Independent measurements showed zero diamagnetism and non-zero resistivity. The claim is disproven."
    }
    claim = "Room-temperature superconductivity was replicated successfully."

    # Model hallucinated that claim is valid
    hallucinated_verifier = {
        "results": [
            {
                "claim_id": "c-1",
                "claim": claim,
                "source_ids": ["src-replication_failed"],
                "supporting_source_id": "src-replication_failed",
                "is_valid": True,
                "verification_status": "DIRECTLY_SUPPORTED"
            }
        ]
    }
    report = f"## Physics\n{claim} [[src-replication_failed]]"
    audit = audit_report_integrity(report, [contradicting_source], hallucinated_verifier)

    assert audit.status == "FAILED"
    assert audit.is_verified is False
    assert audit.claims[0].verification_status == "CONTRADICTED"
    assert audit.claims[0].support_status == "CONTRADICTED"
    assert audit.claims[0].disposition == "remove"


def test_integration_retry_feedback_incorporation():
    """Verify that verifier feedback is structured to be passed to writer revisions."""
    source = {
        "id": "src-failed_trial",
        "title": "Failed Trial",
        "url": "https://example.org/ft",
        "scrape_status": "success",
        "extracted_text": "The drug failed to show efficacy in clinical trials."
    }
    claim = "The drug demonstrated clear efficacy in clinical trials."
    mock_verifier = {
        "results": [
            {
                "claim_id": "claim-fail",
                "claim": claim,
                "source_ids": ["src-failed_trial"],
                "supporting_source_id": "src-failed_trial",
                "is_valid": True,
                "verification_status": "DIRECTLY_SUPPORTED"
            }
        ]
    }
    report = f"## Trial\n{claim} [[src-failed_trial]]"
    audit = audit_report_integrity(report, [source], mock_verifier)

    # Audit must generate human-readable failure explanations
    assert len(audit.failure_explanations) >= 1
    feedback_line = audit.failure_explanations[0]
    assert "Contradiction" in feedback_line or "failed to show" in feedback_line


def test_integration_deterministic_references_preserve_provenance():
    """Verify that bibliography generation preserves persistent identifiers and locators."""
    source = {
        "id": "src-quantum_computing",
        "title": "Quantum Supremacy Using a Programmable Superconducting Processor",
        "authors": ["F. Arute", "K. Arya", "R. Babbush"],
        "published_date": "2019",
        "url": "https://nature.com/articles/s41586-019-1666-5",
        "doi": "10.1038/s41586-019-1666-5",
        "arxiv_id": "1910.11333"
    }
    report_body = "The Sycamore processor took 200 seconds to sample quantum circuits [[src-quantum_computing]]."
    final_report, deduped, unresolved = generate_deterministic_bibliography(report_body, [source])

    assert len(deduped) == 1
    assert len(unresolved) == 0
    assert "10.1038/s41586-019-1666-5" in final_report
    assert "1910.11333" in final_report
    assert "Arute" in final_report
