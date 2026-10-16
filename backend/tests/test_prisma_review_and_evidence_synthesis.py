import os
import sys
import tempfile
import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.intellectual_rigour.prisma import (
    ScreeningStage,
    ScreeningDisposition,
    ReviewerType,
    HypothesisRelation,
    ReviewProtocol,
    ScreeningDecision,
    StudyAppraisal,
    ContradictionEntry,
    EvidenceMatrix,
    PRISMAFlowCounts,
    PRISMAReviewLedger,
    group_sources_into_studies,
    screen_source_title_abstract,
    screen_source_full_text,
    appraise_included_study,
    map_contradictions,
    compute_prisma_flow,
    generate_prisma_mermaid_diagram,
    run_prisma_review_workflow,
)
from backend.memory.db import (
    init_db,
    save_brief_db,
    save_prisma_review_db,
    get_prisma_review_db,
    list_prisma_reviews_db,
    save_screening_decision_db,
    get_screening_decision_db,
    list_screening_decisions_db,
    update_screening_decision_db,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


# ============================================================================
# 1. PRISMA 2020 Flow Accounting & Mathematical Invariant Tests
# ============================================================================

def test_prisma_flow_accounting_mathematical_invariants():
    """Verify that flow counts satisfy PRISMA 2020 transition equations without count leaks."""
    counts = PRISMAFlowCounts(
        identified_databases=12,
        identified_registries_web=5,
        identified_snowball=3,
        total_identified=20,
        duplicates_removed=4,
        records_screened=16,
        records_excluded_title_abstract=6,
        reports_sought_for_retrieval=10,
        reports_not_retrieved=2,
        reports_assessed_for_eligibility=8,
        reports_excluded_full_text=3,
        included_reports=5,
        included_studies=4,  # e.g., 2 reports belong to the same multi-report trial
    )
    is_valid, issues = counts.verify_accounting_integrity()
    assert is_valid is True, f"Integrity check failed: {issues}"
    assert len(issues) == 0


def test_prisma_flow_accounting_detects_count_inflation_or_leak():
    """Verify that corrupted or inflated counts fail the invariant verification."""
    # Inflated records screened
    bad_counts = PRISMAFlowCounts(
        identified_databases=10,
        identified_registries_web=0,
        identified_snowball=0,
        total_identified=10,
        duplicates_removed=2,
        records_screened=12,  # Corrupted: 10 - 2 != 12
        records_excluded_title_abstract=2,
        reports_sought_for_retrieval=6,
        reports_not_retrieved=0,
        reports_assessed_for_eligibility=6,
        reports_excluded_full_text=0,
        included_reports=6,
        included_studies=6,
    )
    is_valid, issues = bad_counts.verify_accounting_integrity()
    assert is_valid is False
    assert any("Screening count mismatch" in i for i in issues)

    # Studies count exceeding reports count
    bad_studies = PRISMAFlowCounts(
        identified_databases=5,
        total_identified=5,
        duplicates_removed=0,
        records_screened=5,
        records_excluded_title_abstract=0,
        reports_sought_for_retrieval=5,
        reports_not_retrieved=0,
        reports_assessed_for_eligibility=5,
        reports_excluded_full_text=0,
        included_reports=5,
        included_studies=7,  # Corrupted: studies cannot exceed reports
    )
    is_valid_studies, issues_studies = bad_studies.verify_accounting_integrity()
    assert is_valid_studies is False
    assert any("Study count cannot exceed report count" in i for i in issues_studies)


def test_prisma_mermaid_diagram_generation():
    """Verify that generate_prisma_mermaid_diagram outputs valid mermaid diagram syntax."""
    counts = PRISMAFlowCounts(
        identified_databases=8,
        identified_registries_web=2,
        identified_snowball=1,
        total_identified=11,
        duplicates_removed=1,
        records_screened=10,
        records_excluded_title_abstract=3,
        reports_sought_for_retrieval=7,
        reports_not_retrieved=1,
        reports_assessed_for_eligibility=6,
        reports_excluded_full_text=2,
        included_reports=4,
        included_studies=3,
    )
    diagram = generate_prisma_mermaid_diagram(counts, topic="Attention Mechanisms in Transformers")
    assert "```mermaid" in diagram
    assert "flowchart TD" in diagram
    assert "Total records identified<br/>(n = 11)" in diagram
    assert "Duplicates removed prior to screening<br/>(n = 1)" in diagram
    assert "Records screened (Title & Abstract)<br/>(n = 10)" in diagram
    assert "Reports sought for retrieval<br/>(n = 7)" in diagram
    assert "Reports not retrieved (Paywalled / Inaccessible)<br/>(n = 1)" in diagram
    assert "Reports assessed for full-text eligibility<br/>(n = 6)" in diagram
    assert "Reports: 4 | Unique Studies: 3" in diagram


# ============================================================================
# 2. Source Deduplication & Multi-Report Study Grouping Tests
# ============================================================================

def test_group_sources_into_studies_by_doi_and_arxiv():
    """
    Ensure reports belonging to the same study (e.g., arXiv preprint and conference proceedings)
    are linked to one study ID rather than double-counted as separate investigations.
    """
    sources = [
        {
            "id": "src-1",
            "title": "Scaling Laws for Neural Language Models",
            "doi": "10.1234/scaling2020",
            "arxiv_id": "2001.08361",
            "url": "https://arxiv.org/abs/2001.08361",
        },
        {
            "id": "src-2",
            "title": "Scaling Laws for Neural Language Models (Conference Version)",
            "doi": "10.1234/scaling2020",  # Same DOI
            "url": "https://doi.org/10.1234/scaling2020",
        },
        {
            "id": "src-3",
            "title": "Chinchilla: Training Compute-Optimal Large Language Models",
            "arxiv_id": "2203.15556",
            "url": "https://arxiv.org/abs/2203.15556",
        },
    ]

    grouped = group_sources_into_studies(sources)
    # We should have exactly 2 distinct studies, where study 1 contains src-1 and src-2
    assert len(grouped) == 2
    study_lens = [len(reports) for reports in grouped.values()]
    assert 2 in study_lens
    assert 1 in study_lens


# ============================================================================
# 3. Screening & Eligibility Decision Ledger Tests (Deliverable B)
# ============================================================================

def test_title_abstract_screening_relevance_and_criteria():
    """Verify title/abstract screening applies brief selection criteria and flags off-topic."""
    criteria = [
        "Include empirical investigations evaluating transformer scaling",
        "Exclude opinion pieces and non-empirical editorials",
    ]

    # Valid empirical candidate
    good_source = {
        "id": "src-good",
        "title": "Empirical Analysis of Transformer Scaling Laws Across Compute Budgets",
        "abstract": "We empirically measure transformer performance across 6 orders of magnitude in compute.",
        "url": "https://arxiv.org/abs/2001.01",
    }
    dec_good = screen_source_title_abstract(good_source, criteria, topic="Transformer Scaling")
    assert dec_good.disposition == ScreeningDisposition.INCLUDED
    assert dec_good.stage == ScreeningStage.TITLE_ABSTRACT
    assert dec_good.reviewer_type == ReviewerType.AI_RECOMMENDED

    # Explicit exclusion: editorial/opinion
    bad_source = {
        "id": "src-editorial",
        "title": "Editorial: The Hype Around Transformer Scaling",
        "abstract": "In this commentary and opinion piece, we discuss industry sentiment without benchmarks.",
        "url": "https://example.com/editorial",
    }
    dec_bad = screen_source_title_abstract(bad_source, criteria, topic="Transformer Scaling")
    assert dec_bad.disposition == ScreeningDisposition.EXCLUDED
    assert "opinion piece" in (dec_bad.exclusion_reason or "").lower()

    # Off-topic source
    off_topic = {
        "id": "src-farming",
        "title": "Agricultural Crop Rotation and Soil Microbiome Dynamics in Sub-Saharan Africa",
        "abstract": "We evaluate wheat yield changes across traditional legume rotation cycles.",
        "url": "https://agri.org/crops",
    }
    dec_off = screen_source_title_abstract(off_topic, criteria, topic="Transformer Scaling")
    assert dec_off.disposition == ScreeningDisposition.EXCLUDED
    assert "off-topic" in (dec_off.exclusion_reason or "").lower()


def test_full_text_screening_distinguishes_retrieval_failure_from_ineligibility():
    """
    CRITICAL PRISMA REQUIREMENT:
    A retrieval failure (paywall, scrape error, 403) MUST be recorded as NOT_RETRIEVED,
    and NEVER falsely classified as an eligibility criterion exclusion.
    """
    criteria = ["Include controlled empirical baseline comparisons"]

    # Case 1: Retrieval failure
    paywalled_source = {
        "id": "src-paywalled",
        "title": "Proprietary Scaling Architecture",
        "url": "https://publisher.com/closed-paper",
        "scrape_status": "failed",
        "extraction_quality": "inaccessible",
        "scrape_error": "HTTP 403 Forbidden: Institutional Subscription Required",
        "extracted_text": "",
    }
    dec_fail = screen_source_full_text(paywalled_source, criteria)
    assert dec_fail.disposition == ScreeningDisposition.NOT_RETRIEVED
    assert dec_fail.stage == ScreeningStage.FULL_TEXT_ELIGIBILITY
    assert "retrieval failure" in (dec_fail.exclusion_reason or "").lower()

    # Case 2: Full text retrieved, but fails eligibility criteria (missing baseline controls)
    retrieved_ineligible = {
        "id": "src-no-baseline",
        "title": "Anecdotal Tokenizer Adjustments",
        "url": "https://openaccess.org/tokenizer",
        "scrape_status": "success",
        "extraction_quality": "full",
        "extracted_text": "We ran our model on text. We did not run any baseline comparisons or control experiments.",
    }
    dec_excl = screen_source_full_text(retrieved_ineligible, criteria)
    assert dec_excl.disposition == ScreeningDisposition.EXCLUDED
    assert dec_excl.stage == ScreeningStage.FULL_TEXT_ELIGIBILITY
    assert "baseline" in (dec_excl.exclusion_reason or "").lower()

    # Case 3: Full text retrieved and satisfies criteria
    retrieved_eligible = {
        "id": "src-eligible",
        "title": "Rigorous Evaluation with Baselines",
        "url": "https://openaccess.org/rigorous",
        "scrape_status": "success",
        "extraction_quality": "full",
        "extracted_text": "We evaluate against state-of-the-art baseline models with full control groups and benchmark suites.",
        "passages": [{"text": "Comparative baseline performance table demonstrating 12% gain with p < 0.01."}],
    }
    dec_inc = screen_source_full_text(retrieved_eligible, criteria)
    assert dec_inc.disposition == ScreeningDisposition.INCLUDED
    assert dec_inc.stage == ScreeningStage.FULL_TEXT_ELIGIBILITY


# ============================================================================
# 4. Evidence Appraisal & Contradiction Mapping Tests (Deliverable C)
# ============================================================================

def test_study_appraisal_characteristics_and_limitations():
    """Verify study appraisal infers design, methodological rigor, limitations, and stance."""
    source = {
        "id": "src-study-1",
        "title": "Scaling Law Limits in Over-parameterized Neural Networks",
        "authors": ["Kaplan, J.", "McCandlish, S."],
        "published_date": "2020-01-15",
        "doi": "10.1234/test",
        "extracted_text": (
            "We test on a dataset of 10,000,000 tokens using standard benchmark suites. "
            "We report p < 0.001 significance tests and baseline comparisons. "
            "Our code is open-source at github.com/test/repo. "
            "A notable limitation is that our observations do not extend to recurrent topologies."
        ),
        "passages": [{"text": "Results confirm power-law scaling across compute regimes."}],
    }

    appraisal = appraise_included_study(source, focal_hypothesis="Scaling improves performance")
    assert appraisal.study_design == "benchmark_evaluation"
    assert appraisal.methodological_indicators["baseline_controls"] is True
    assert appraisal.methodological_indicators["reproducibility_artifacts"] is True
    assert appraisal.methodological_indicators["statistical_validation"] is True
    assert appraisal.hypothesis_relation == HypothesisRelation.SUPPORTS
    assert any("limitation" in lim.lower() for lim in appraisal.reported_limitations)


def test_dialectic_contradiction_mapping_with_counter_evidence():
    """
    Verify dialectic contradiction mapping pairs supporting and counter-evidence studies
    (including Phase 3.2 counter-evidence) and analyzes divergence reasons.
    """
    study_supp = StudyAppraisal(
        study_id="study-supp-1",
        title="Power-Law Scaling Holds Across Massive Compute",
        study_design="benchmark_evaluation",
        sample_or_dataset="WebText 40B tokens",
        hypothesis_relation=HypothesisRelation.SUPPORTS,
    )
    study_counter = StudyAppraisal(
        study_id="study-ch-1",
        title="Breakdown of Scaling Laws Under Low-Precision Quantization",
        study_design="controlled_experiment",
        sample_or_dataset="Synthetic Quantized Cohort",
        hypothesis_relation=HypothesisRelation.CHALLENGES,
    )

    contradictions = map_contradictions(
        [study_supp, study_counter],
        focal_hypothesis="Scaling power laws are invariant to quantization",
    )

    assert len(contradictions) == 1
    c = contradictions[0]
    assert "study-supp-1" in c.supporting_study_ids
    assert "study-ch-1" in c.counter_study_ids
    assert "Design divergence" in c.substantive_divergence or "divergence" in c.substantive_divergence.lower()
    assert len(c.resolution_requirements) > 20


def test_evidence_matrix_markdown_table_rendering():
    """Verify EvidenceMatrix renders a clean markdown table for human inspection."""
    studies = [
        StudyAppraisal(
            study_id="s1",
            title="Study Alpha on Transformers",
            authors=["Vaswani, A."],
            published_year="2017",
            study_design="benchmark_evaluation",
            sample_or_dataset="WMT 2014 En-De",
            methodological_indicators={"baseline_controls": True, "reproducibility_artifacts": True, "statistical_validation": False},
            reported_limitations=["Memory complexity scales quadratically with sequence length"],
            hypothesis_relation=HypothesisRelation.SUPPORTS,
        )
    ]
    matrix = EvidenceMatrix(studies=studies)
    md = matrix.to_markdown_table()
    assert "| Study / Citation | Design |" in md
    assert "Vaswani et al. (2017)" in md
    assert "Baselines ✓" in md
    assert "Open Data/Code ✓" in md
    assert "`SUPPORTS`" in md


# ============================================================================
# 5. Database Persistence & Human Audit Confirmation Tests (Deliverable B)
# ============================================================================

def test_prisma_review_and_decisions_sqlite_crud(temp_db):
    """Verify SQLite persistence and roundtrip retrieval for reviews and decisions."""
    # 1. Save and retrieve PRISMA review
    review_data = {
        "review_id": "rev-test-101",
        "brief_id": "brief-alpha",
        "session_id": "sess-alpha",
        "topic": "Neural Scaling Dynamics",
        "protocol": {
            "protocol_id": "proto-1",
            "brief_id": "brief-alpha",
            "topic": "Neural Scaling Dynamics",
            "selection_criteria": ["Empirical benchmark"],
        },
        "flow_counts": {
            "total_identified": 10,
            "records_screened": 10,
            "included_reports": 4,
            "included_studies": 3,
        },
        "mermaid_diagram": "flowchart TD\nTotal-->Inc",
    }
    saved_rev = save_prisma_review_db(review_data, db_path=temp_db)
    assert saved_rev["review_id"] == "rev-test-101"

    retrieved = get_prisma_review_db("rev-test-101", db_path=temp_db)
    assert retrieved is not None
    assert retrieved["topic"] == "Neural Scaling Dynamics"
    assert retrieved["flow_counts"]["included_reports"] == 4

    # 2. Save screening decision
    dec_data = {
        "decision_id": "dec-101",
        "review_id": "rev-test-101",
        "brief_id": "brief-alpha",
        "source_id": "src-x",
        "source_url": "https://arxiv.org/abs/2001.01",
        "title": "Scaling Law paper",
        "stage": "TITLE_ABSTRACT",
        "disposition": "INCLUDED",
        "criteria_applied": ["Empirical benchmark"],
        "rationale": "Relevant empirical content",
        "reviewer_type": "AI_RECOMMENDED",
    }
    saved_dec = save_screening_decision_db(dec_data, db_path=temp_db)
    assert saved_dec["decision_id"] == "dec-101"

    # 3. Human reviewer override/confirmation
    success = update_screening_decision_db(
        decision_id="dec-101",
        disposition="EXCLUDED",
        reviewer_notes="Reviewer audited: sample size is under-powered.",
        reviewer_type="REVIEWER_CONFIRMED",
        db_path=temp_db,
    )
    assert success is True

    updated_dec = get_screening_decision_db("dec-101", db_path=temp_db)
    assert updated_dec["disposition"] == "EXCLUDED"
    assert updated_dec["reviewer_type"] == "REVIEWER_CONFIRMED"
    assert "Reviewer audited: sample size is under-powered." in updated_dec["rationale"]


# ============================================================================
# 6. Workflow Runner & Pipeline Integration Tests (Deliverable A & C)
# ============================================================================

def test_run_prisma_review_workflow_end_to_end(temp_db):
    """
    Verify complete autonomous workflow execution:
    brief -> candidate records -> screening -> full-text check -> appraisal -> contradiction mapping -> flow counts.
    """
    brief = {
        "brief_id": "brief-auto-1",
        "session_id": "sess-auto",
        "topic": "Graph Neural Network Over-smoothing",
        "research_question": "Do residual connections mitigate exponential over-smoothing in deep GNNs?",
        "selection_criteria": [
            "Include empirical benchmarks on multi-layer GNN architectures",
            "Exclude non-empirical editorials and opinion pieces",
            "Include controlled baseline comparisons",
        ],
        "hypotheses": ["Residual connections mitigate exponential over-smoothing in deep GNNs"],
    }
    save_brief_db(brief, db_path=temp_db)

    sources = [
        # Source 1: Valid empirical study
        {
            "id": "src-gnn-1",
            "title": "Mitigating Over-smoothing in Deep Graph Neural Networks with Initial Residuals",
            "abstract": "We empirically test multi-layer GNNs on Cora and CiteSeer with controlled baseline comparisons.",
            "url": "https://arxiv.org/abs/2007.02133",
            "source_api": "arxiv",
            "scrape_status": "success",
            "extraction_quality": "full",
            "extracted_text": (
                "We evaluate deep GNN architectures up to 64 layers with baseline models. "
                "Results demonstrate statistically significant gains (p < 0.01). "
                "Open source code available at github.com/gnn/repo. "
                "A stated limitation is reliance on standard benchmark homophilous graphs."
            ),
            "passages": [{"text": "Residual connections improve 64-layer GNN accuracy by 15%."}],
        },
        # Source 2: Counter-evidence study (Phase 3.2 integration)
        {
            "id": "src-gnn-2",
            "title": "Limitations of Residual Connections in Heterophilous Graph Regimes",
            "abstract": "We analyze deep GNN architectures and find residual connections fail on heterophilous graphs.",
            "url": "https://arxiv.org/abs/2105.08888",
            "source_api": "arxiv",
            "relation": "counter_evidence",
            "scrape_status": "success",
            "extraction_quality": "full",
            "extracted_text": (
                "Our empirical benchmark demonstrates a complete failure to replicate gains in heterophilous graphs. "
                "Residual connections breakdown when node label assortativity is negative."
            ),
            "passages": [{"text": "Failure to replicate: negative result in heterophilous datasets."}],
        },
        # Source 3: Paywalled / retrieval failure
        {
            "id": "src-gnn-3",
            "title": "Paywalled Proprietary Graph Study",
            "abstract": "Proprietary study on graph embeddings.",
            "url": "https://publisher.com/gnn-closed",
            "source_api": "scholarly",
            "scrape_status": "failed",
            "extraction_quality": "inaccessible",
            "scrape_error": "Connection timed out",
            "extracted_text": "",
        },
        # Source 4: Off-topic / excluded
        {
            "id": "src-gnn-4",
            "title": "Economic Inflation Trends in North America",
            "abstract": "Analysis of Federal Reserve interest rates.",
            "url": "https://econ.org/inflation",
            "source_api": "web",
            "scrape_status": "success",
            "extraction_quality": "full",
            "extracted_text": "Inflation rose 2.1%.",
        },
    ]

    ledger = run_prisma_review_workflow(
        topic=brief["topic"],
        sources=sources,
        brief=brief,
        session_id=brief["session_id"],
        db_path=temp_db,
    )

    # Invariants verification
    is_valid, issues = ledger.flow_counts.verify_accounting_integrity()
    assert is_valid is True, f"Invariant failure: {issues}"

    # Flow count assertions
    assert ledger.flow_counts.total_identified == 4
    assert ledger.flow_counts.records_screened == 4
    # Off-topic source excluded at Title/Abstract screening
    assert ledger.flow_counts.records_excluded_title_abstract == 1
    assert ledger.flow_counts.reports_sought_for_retrieval == 3
    # Paywalled source marked NOT_RETRIEVED
    assert ledger.flow_counts.reports_not_retrieved == 1
    assert ledger.flow_counts.reports_assessed_for_eligibility == 2
    # 2 remaining sources included (1 supporting, 1 challenging)
    assert ledger.flow_counts.included_reports == 2
    assert ledger.flow_counts.included_studies == 2

    # Evidence matrix & Contradiction mapping verification
    assert len(ledger.evidence_matrix.studies) == 2
    stances = [s.hypothesis_relation for s in ledger.evidence_matrix.studies]
    assert HypothesisRelation.SUPPORTS in stances
    assert HypothesisRelation.CHALLENGES in stances

    # Phase 3.2 Counter-evidence paired in contradiction
    assert len(ledger.evidence_matrix.contradictions) == 1
    c = ledger.evidence_matrix.contradictions[0]
    supp_study = [s for s in ledger.evidence_matrix.studies if s.study_id in c.supporting_study_ids][0]
    assert "src-gnn-1" in supp_study.report_ids
    counter_study = [s for s in ledger.evidence_matrix.studies if s.study_id in c.counter_study_ids][0]
    assert "src-gnn-2" in counter_study.report_ids

    # Verify persistence
    persisted_rev = get_prisma_review_db(ledger.review_id, db_path=temp_db)
    assert persisted_rev is not None
    assert persisted_rev["flow_counts"]["included_reports"] == 2


# ============================================================================
# 7. REST API Endpoints Test (TestClient)
# ============================================================================

def test_prisma_rest_api_endpoints(temp_db):
    """Test FastAPI REST endpoints for review inspection and reviewer confirmation."""
    client = TestClient(app)

    # Seed brief
    brief = {
        "brief_id": "brief-api-test",
        "session_id": "sess-api",
        "topic": "Reinforcement Learning from Human Feedback",
        "research_question": "Does RLHF improve instruction following alignment in language models?",
        "selection_criteria": ["Empirical alignment evaluation"],
    }
    save_brief_db(brief, db_path=temp_db)

    # 1. Execute review via POST /api/prisma/reviews
    exec_resp = client.post(
        f"/api/prisma/reviews?db_path={temp_db}",
        json={
            "brief_id": "brief-api-test",
            "sources": [
                {
                    "id": "src-rlhf-1",
                    "title": "Training language models to follow instructions with human feedback",
                    "abstract": "We evaluate RLHF models on human preference datasets.",
                    "url": "https://arxiv.org/abs/2203.02155",
                    "source_api": "arxiv",
                    "scrape_status": "success",
                    "extraction_quality": "full",
                    "extracted_text": "We evaluate against supervised baselines with human preferences.",
                }
            ],
        },
    )
    assert exec_resp.status_code == 201
    rev_data = exec_resp.json()
    review_id = rev_data["review_id"]
    assert rev_data["flow_counts"]["included_reports"] == 1

    # 2. Get review via GET /api/prisma/reviews/{id}
    get_resp = client.get(f"/api/prisma/reviews/{review_id}?db_path={temp_db}")
    assert get_resp.status_code == 200
    assert get_resp.json()["topic"] == "Reinforcement Learning from Human Feedback"

    # 3. List decisions via GET /api/prisma/reviews/{id}/decisions
    dec_resp = client.get(f"/api/prisma/reviews/{review_id}/decisions?db_path={temp_db}")
    assert dec_resp.status_code == 200
    decisions = dec_resp.json()
    assert len(decisions) >= 1
    target_dec_id = decisions[0]["decision_id"]

    # 4. Confirm/Override decision via POST /api/prisma/reviews/{id}/decisions/{dec_id}/confirm
    confirm_resp = client.post(
        f"/api/prisma/reviews/{review_id}/decisions/{target_dec_id}/confirm?db_path={temp_db}",
        json={
            "disposition": "INCLUDED",
            "reviewer_notes": "Expert confirmation: Methodology meets rigorous standards.",
            "reviewer_type": "REVIEWER_CONFIRMED",
        },
    )
    assert confirm_resp.status_code == 200
    conf_json = confirm_resp.json()
    assert conf_json["status"] == "confirmed"
    assert conf_json["decision"]["reviewer_type"] == "REVIEWER_CONFIRMED"

    # 5. Get Evidence Matrix via GET /api/prisma/reviews/{id}/evidence-matrix
    matrix_resp = client.get(f"/api/prisma/reviews/{review_id}/evidence-matrix?db_path={temp_db}")
    assert matrix_resp.status_code == 200
    assert "studies" in matrix_resp.json()

    # 6. Get Mermaid flowchart via GET /api/prisma/reviews/{id}/mermaid
    mermaid_resp = client.get(f"/api/prisma/reviews/{review_id}/mermaid?db_path={temp_db}")
    assert mermaid_resp.status_code == 200
    assert "flowchart TD" in mermaid_resp.text
