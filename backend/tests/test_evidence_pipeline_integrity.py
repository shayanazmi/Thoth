"""
Deterministic test suite for the Evidence Pipeline Integrity Milestone in THOTH.
Covers:
  1. Evidence from later pages surviving bounded passage selection.
  2. Correct source and page provenance for selected passages.
  3. Genuinely supported claims marked SUPPORTED.
  4. Contradicted claims despite high lexical overlap marked CONTRADICTED.
  5. Claims with insufficient evidence or inconclusive sources marked INSUFFICIENT.
  6. Failed or empty extractions marked UNVERIFIABLE and not represented as verified.
  7. Backward compatibility for legacy sources, bibliography generation, and ingestion.
"""

import pytest
from typing import Dict, Any, List

from backend.ingestion import (
    create_bounded_passages,
    select_representative_passages,
    format_passages_for_context,
    ingest_document,
    IngestionResult,
)
from backend.agents import (
    EvidencePassage,
    ReportClaim,
    ReportIntegrityResult,
)
from backend.intellectual_rigour.integrity_gate import (
    evaluate_claim_support,
    audit_report_integrity,
    generate_deterministic_bibliography,
)


def test_later_page_evidence_survives_passage_selection():
    """
    Scenario 1: Multi-page document where empirical findings on Page 4 & 5
    survive bounded passage selection and reach the formatted context.
    """
    # Simulate a 5-page PDF document (~4000 characters)
    p1 = "[Page 1]\nIntroduction to Quantum Error Correction. We outline foundational principles of surface codes."
    p2 = "\n\n[Page 2]\nTheoretical Hamiltonian formulation and stabilizer syndrome measurement operators."
    p3 = "\n\n[Page 3]\nCryogenic hardware setup and dilution refrigerator microwave line attenuation calibrations."
    p4 = "\n\n[Page 4]\nEmpirical Results: The 17-qubit distance-3 surface code achieved a logical error rate of 2.1 x 10^-3 per cycle, outperforming the physical qubit baseline."
    p5 = "\n\n[Page 5]\nDiscussion and Conclusion: Threshold scaling indicates fault-tolerant advantage under sub-microsecond decoding."

    full_text = p1 + p2 + p3 + p4 + p5
    passages = create_bounded_passages(
        text=full_text,
        content_type="application/pdf",
        source_uri="https://arxiv.org/abs/2301.99999",
        target_passage_chars=300
    )

    assert len(passages) >= 4, f"Expected multiple bounded passages, got {len(passages)}"
    
    # Verify passages contain page metadata
    pages_present = {p.get("page_num") for p in passages if p.get("page_num") is not None}
    assert 4 in pages_present, "Page 4 should be identified in created passages"
    assert 5 in pages_present, "Page 5 should be identified in created passages"

    # Select representative passages across the document
    selected = select_representative_passages(passages, max_chars=1200, max_passages=4)
    selected_pages = [p.get("page_num") for p in selected if p.get("page_num") is not None]
    
    # Page 4 or 5 must survive selection
    assert any(page in (4, 5) for page in selected_pages), (
        f"Later page evidence failed to survive passage selection: {selected_pages}"
    )

    # Context formatting must include page annotations
    formatted_context = format_passages_for_context(selected, max_chars=1500)
    assert "Page " in formatted_context
    assert any(f"Page {p}" in formatted_context for p in (4, 5))
    assert "logical error rate" in formatted_context or "Threshold scaling" in formatted_context


def test_correct_source_and_page_provenance():
    """
    Scenario 2: Correct source, page number, and character offset provenance
    are preserved for each passage.
    """
    sample_text = (
        "[Page 1]\nFoundational survey of retrieval augmented generation.\n\n"
        "[Page 2]\nEmpirical benchmarks show hybrid dense-sparse retrieval achieves 0.89 MRR."
    )
    passages = create_bounded_passages(
        text=sample_text,
        content_type="application/pdf",
        source_uri="https://doi.org/10.1000/182",
        target_passage_chars=200
    )

    p2_passages = [p for p in passages if p.get("page_num") == 2]
    assert len(p2_passages) >= 1, "Expected at least one passage on Page 2"

    target_passage = p2_passages[0]
    assert target_passage["source_uri"] == "https://doi.org/10.1000/182"
    assert target_passage["page_num"] == 2
    assert target_passage["char_start"] >= 0
    assert target_passage["char_end"] > target_passage["char_start"]
    assert "0.89 MRR" in target_passage["text"]

    # Verify EvidencePassage model mapping
    ev_obj = EvidencePassage(
        source_id="src-rag_benchmarks",
        title="RAG Benchmarks",
        url="https://doi.org/10.1000/182",
        quote=target_passage["text"],
        page_num=target_passage["page_num"],
        char_start=target_passage["char_start"],
        char_end=target_passage["char_end"],
        extraction_status=target_passage.get("extraction_status", "success")
    )
    assert ev_obj.page_num == 2
    assert ev_obj.char_start == target_passage["char_start"]
    assert ev_obj.source_id == "src-rag_benchmarks"


def test_source_supports_claim():
    """
    Scenario 3: A source that genuinely corroborates a factual assertion
    is evaluated as SUPPORTED.
    """
    source_record = {
        "id": "src-cgm_trials",
        "title": "Continuous Glucose Monitoring in Type 1 Diabetes",
        "url": "https://doi.org/10.2337/dc20-0001",
        "doi": "10.2337/dc20-0001",
        "scrape_status": "success",
        "extracted_text": (
            "In our multicenter randomized trial of 300 participants, continuous glucose monitoring "
            "significantly reduced HbA1c levels compared to standard fingerstick testing."
        )
    }

    claim = "Continuous glucose monitoring significantly reduced HbA1c levels in type 1 diabetes."
    status, reason, meta = evaluate_claim_support(
        claim_text=claim,
        source_record=source_record
    )

    assert status == "SUPPORTED", f"Expected SUPPORTED, got {status} ({reason})"
    assert meta is not None
    assert "passage" in meta

    # End-to-end audit integration check
    mock_raw_verifier = {
        "results": [
            {
                "claim_id": "claim-1",
                "claim": claim,
                "source_ids": ["src-cgm_trials"],
                "supporting_source_id": "src-cgm_trials",
                "is_valid": True,
                "verification_status": "DIRECTLY_SUPPORTED"
            }
        ]
    }
    report = f"## Results\n{claim} [[src-cgm_trials]]"
    audit = audit_report_integrity(report, [source_record], mock_raw_verifier)

    assert audit.status == "PASSED"
    assert audit.is_verified is True
    assert len(audit.claims) == 1
    assert audit.claims[0].support_status == "SUPPORTED"
    assert audit.claims[0].verification_status == "DIRECTLY_SUPPORTED"


def test_source_contradicts_claim_despite_lexical_overlap():
    """
    Scenario 4: A source explicitly contradicts a claim despite sharing
    almost identical words (polarity reversal / negation).
    Must be marked CONTRADICTED, NOT falsely marked SUPPORTED.
    """
    # The source contains the exact entity, verb, and disease, but with clear negation
    source_record = {
        "id": "src-ad_trial",
        "title": "Phase III Trial of Compound X in Alzheimer's",
        "url": "https://doi.org/10.1056/NEJMoa2000000",
        "scrape_status": "success",
        "extracted_text": (
            "We evaluated Compound X in a double-blind study. Our results showed that Compound X "
            "failed to reduce cognitive decline in Alzheimer's patients."
        )
    }

    # Claim makes the positive assertion using matching words
    false_claim = "Compound X reduces cognitive decline in Alzheimer's patients."

    status, reason, meta = evaluate_claim_support(
        claim_text=false_claim,
        source_record=source_record
    )

    assert status == "CONTRADICTED", f"Expected CONTRADICTED despite lexical overlap, got {status} ({reason})"
    assert "failed to" in reason.lower() or "contradict" in reason.lower()

    # Even if an ungrounded or hallucinating model marked this claim as is_valid=True,
    # the integrity gate must override it to CONTRADICTED and fail the audit.
    mock_hallucinated_verifier = {
        "results": [
            {
                "claim_id": "claim-false-1",
                "claim": false_claim,
                "source_ids": ["src-ad_trial"],
                "supporting_source_id": "src-ad_trial",
                "is_valid": True,  # Model hallucinated that it was supported
                "verification_status": "DIRECTLY_SUPPORTED"
            }
        ]
    }
    report = f"## Findings\n{false_claim} [[src-ad_trial]]"
    audit = audit_report_integrity(report, [source_record], mock_hallucinated_verifier)

    assert audit.status == "FAILED", "Integrity gate must fail when a contradicted claim is present"
    assert audit.is_verified is False
    assert len(audit.claims) == 1
    assert audit.claims[0].support_status == "CONTRADICTED"
    assert audit.claims[0].verification_status == "CONTRADICTED"
    assert audit.claims[0].disposition == "remove"


def test_claim_insufficient_or_inconclusive():
    """
    Scenario 5: A claim for which the source text is insufficient (e.g. topic
    is mentioned in passing or source states findings remain inconclusive).
    """
    # Source A: explicitly inconclusive
    source_inconclusive = {
        "id": "src-diet_study",
        "title": "Dietary Interventions in Longevity",
        "url": "https://example.org/diet",
        "scrape_status": "success",
        "extracted_text": "Evidence regarding intermittent fasting and human lifespan extension remains inconclusive."
    }
    claim_a = "Intermittent fasting extends human lifespan."
    status_a, reason_a, _ = evaluate_claim_support(claim_a, source_inconclusive)
    assert status_a == "INSUFFICIENT"
    assert "inconclusive" in reason_a.lower()

    # Source B: missing specific quantitative metric claimed
    source_no_metric = {
        "id": "src-model_y",
        "title": "Model Y Architecture",
        "url": "https://example.org/modely",
        "scrape_status": "success",
        "extracted_text": "Model Y is an autoregressive transformer trained on open-source web text."
    }
    claim_b = "Model Y achieved a 10x throughput speedup on mobile devices."
    status_b, reason_b, _ = evaluate_claim_support(claim_b, source_no_metric)
    assert status_b == "INSUFFICIENT"

    # In audit_report_integrity, an INSUFFICIENT claim cannot pass as directly supported
    mock_verifier = {
        "results": [
            {
                "claim_id": "claim-b",
                "claim": claim_b,
                "source_ids": ["src-model_y"],
                "supporting_source_id": "src-model_y",
                "is_valid": True,
                "verification_status": "DIRECTLY_SUPPORTED"
            }
        ]
    }
    report = f"## Model Speed\n{claim_b} [[src-model_y]]"
    audit = audit_report_integrity(report, [source_no_metric], mock_verifier)
    assert audit.claims[0].support_status == "INSUFFICIENT"
    assert audit.claims[0].verification_status == "UNSUPPORTED"
    assert audit.status == "FAILED"


def test_failed_or_empty_extraction_unverifiable():
    """
    Scenario 6: A failed or empty extraction is marked UNVERIFIABLE and
    cannot be represented as a successfully reviewed paper.
    """
    failed_source = {
        "id": "src-paywalled_paper",
        "title": "Paywalled Journal Article",
        "url": "https://nature.com/articles/s41586-023-00000",
        "scrape_status": "failed",
        "scrape_error": "403 Forbidden: Institutional Subscription Required",
        "extracted_text": ""
    }

    claim = "The new superconductor exhibits zero resistance at 300K."
    status, reason, meta = evaluate_claim_support(claim, failed_source)

    assert status == "UNVERIFIABLE"
    assert "failed" in reason or "403" in reason

    # Empty source
    empty_source = {
        "id": "src-empty_doc",
        "title": "Empty Document",
        "url": "https://example.org/empty.pdf",
        "scrape_status": "empty",
        "extracted_text": ""
    }
    status_empty, reason_empty, _ = evaluate_claim_support(claim, empty_source)
    assert status_empty == "UNVERIFIABLE"

    mock_verifier = {
        "results": [
            {
                "claim_id": "claim-unverif",
                "claim": claim,
                "source_ids": ["src-paywalled_paper"],
                "supporting_source_id": "src-paywalled_paper",
                "is_valid": True,
                "verification_status": "DIRECTLY_SUPPORTED"
            }
        ]
    }
    report = f"## Discovery\n{claim} [[src-paywalled_paper]]"
    audit = audit_report_integrity(report, [failed_source], mock_verifier)
    assert audit.status in ("INCOMPLETE", "FAILED")
    assert audit.claims[0].support_status == "UNVERIFIABLE"
    assert audit.claims[0].verification_status == "UNRESOLVED"


def test_existing_citation_and_ingestion_compatibility(tmp_path):
    """
    Scenario 7: Ensure backward compatibility with existing citation formats,
    legacy sources without passages, and deterministic bibliography generation.
    """
    # 1. Ingestion of plain text returns IngestionResult with auto-created passages
    doc_path = tmp_path / "overview.txt"
    doc_path.write_text(
        "Thoth is an open-source autonomous scientific research assistant. "
        "It integrates multi-agent orchestration, literature snowballing, and SLM truth-guarding."
    )
    result = ingest_document(str(doc_path))
    assert isinstance(result, IngestionResult)
    assert result.content_type == "plain"
    assert len(result.passages) >= 1
    assert result.passages[0]["source_uri"] == str(doc_path)

    # 2. Legacy source without passages key still functions in evaluate_claim_support
    legacy_source = {
        "id": "src-legacy_ai",
        "title": "Legacy AI Survey",
        "url": "https://arxiv.org/abs/2101.00001",
        "doi": "10.1000/123",
        "extracted_text": "Transformer self-attention enables parallel computation over sequence tokens."
    }
    status, _, _ = evaluate_claim_support(
        "Transformer self-attention enables parallel computation over sequence tokens.",
        legacy_source
    )
    assert status == "SUPPORTED"

    # 3. Deterministic bibliography generation continues to work
    report = (
        "## Summary\n"
        "Transformers scale effectively [[src-legacy_ai]].\n\n"
        "## References\n"
        "1. Hallucinated Reference"
    )
    clean_report, deduped, unres = generate_deterministic_bibliography(report, [legacy_source])
    assert "Legacy AI Survey" in clean_report
    assert "Hallucinated Reference" not in clean_report
    assert len(deduped) == 1
    assert len(unres) == 0
