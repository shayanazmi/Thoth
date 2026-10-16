"""
THOTH Phase 5 Comprehensive Verification Test Suite
Phase 5 — Persistent Research Workspace & Manuscript Engine

Covers:
1. Deliverable A: Project-scoped persistence, artifact associations, workspace loading, and boundary isolation.
2. Deliverable B: Structured manuscript representation, claim-level provenance, multi-revision diffs, collision detection, and counter-evidence qualification proposals.
3. Deliverable C: Multi-format export engine (academic Markdown, compilable LaTeX, verified BibTeX, and publication-ready HTML).
4. Deliverable D: Interactive evidence matrix drill-down, review flow node records, and bidirectional claim-to-study traceability.
5. API Integration: FastAPI endpoints for projects, manuscripts, revisions, exports, and traceability.
"""

import os
import sys
import tempfile
import json
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.memory.db import (
    init_db,
    save_brief_db,
    save_idea_db,
    save_prisma_review_db,
    save_screening_decision_db,
    save_report,
    get_project_db,
    get_manuscript_db,
    get_manuscript_revision_db,
    list_manuscripts_db,
)
from backend.workspace.project import (
    ResearchProject,
    ProjectWorkspace,
    create_project,
    get_project,
    list_projects,
    archive_project,
    delete_project,
    associate_artifact,
    load_project_workspace,
    verify_project_access,
)
from backend.workspace.manuscript import (
    Manuscript,
    ManuscriptRevision,
    ManuscriptClaim,
    create_manuscript,
    create_manuscript_from_brief_and_review,
    save_manuscript_revision,
    get_manuscript,
    get_manuscript_revision,
    list_manuscripts,
    list_manuscript_revisions,
    propose_claim_qualifications_from_evidence,
)
from backend.workspace.exporter import (
    ExportFormat,
    ExportResult,
    export_manuscript,
    export_to_markdown,
    export_to_latex,
    export_to_bibtex,
    export_to_html,
)
from backend.workspace.traceability import (
    StudyDetail,
    DrillDownResult,
    drill_down_study_record,
    get_flow_node_records,
    get_claim_traceability,
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
# 1. Deliverable A: Project Workspace & Isolation Tests
# ============================================================================

def test_project_crud_and_boundary_isolation(temp_db):
    """Test project lifecycle and session boundary isolation."""
    # Create project
    proj = create_project(
        title="CRISPR Off-Target Epigenetic Study",
        description="Workspace investigating off-target chromatin dynamics",
        session_id="session-user-1",
        metadata={"domain": "Genomics", "lead_author": "Dr. Thoth"},
        db_path=temp_db,
    )
    assert proj.project_id.startswith("proj_")
    assert proj.title == "CRISPR Off-Target Epigenetic Study"
    assert proj.status == "ACTIVE"

    # Get project
    fetched = get_project(proj.project_id, db_path=temp_db)
    assert fetched is not None
    assert fetched.project_id == proj.project_id
    assert fetched.metadata.get("domain") == "Genomics"

    # Access verification
    assert verify_project_access(proj.project_id, session_id="session-user-1", db_path=temp_db) is True
    assert verify_project_access(proj.project_id, session_id="session-unauthorized-2", db_path=temp_db) is False

    # List projects
    user1_projs = list_projects(session_id="session-user-1", db_path=temp_db)
    assert len(user1_projs) == 1
    user2_projs = list_projects(session_id="session-user-2", db_path=temp_db)
    assert len(user2_projs) == 0

    # Archive
    assert archive_project(proj.project_id, db_path=temp_db) is True
    archived = get_project(proj.project_id, db_path=temp_db)
    assert archived.status == "ARCHIVED"

    # Delete
    assert delete_project(proj.project_id, db_path=temp_db) is True
    assert get_project(proj.project_id, db_path=temp_db) is None


def test_project_workspace_artifact_aggregation_and_lineage(temp_db):
    """Verify that load_project_workspace unifies ideas, briefs, reviews, reports, and manuscripts."""
    proj = create_project(
        title="Unified Immunology Project",
        session_id="sess-immuno-1",
        db_path=temp_db,
    )

    # 1. Seed Idea with Revision History
    save_idea_db({
        "idea_id": "idea-tcell-001",
        "session_id": "sess-immuno-1",
        "title": "T-Cell Exhaustion Reversal",
        "description": "Hypothesis on checkpoint blockade",
        "hypothesis": "PD-1 blockade restores progenitor exhausted T-cells.",
        "status": "REVISED",
        "revision_version": 1,
        "created_at": "2026-10-10T00:00:00Z",
        "updated_at": "2026-10-10T00:00:00Z",
    }, db_path=temp_db)

    save_idea_db({
        "idea_id": "idea-tcell-002",
        "session_id": "sess-immuno-1",
        "title": "T-Cell Exhaustion Reversal (Refined)",
        "description": "Refined with dialectical sparring",
        "hypothesis": "PD-1 blockade restores progenitor exhausted T-cells.",
        "status": "PROMOTED",
        "parent_idea_id": "idea-tcell-001",
        "revision_version": 2,
        "created_at": "2026-10-11T00:00:00Z",
        "updated_at": "2026-10-11T00:00:00Z",
    }, db_path=temp_db)

    associate_artifact(proj.project_id, "idea", "idea-tcell-001", db_path=temp_db)
    associate_artifact(proj.project_id, "idea", "idea-tcell-002", db_path=temp_db)


    # 2. Seed Research Brief
    save_brief_db({
        "brief_id": "brief-immuno-101",
        "session_id": "sess-immuno-1",
        "topic": "T-Cell Exhaustion Checkpoints",
        "research_question": "Does anti-PD-1 reinvigorate progenitor exhausted T cells?",
        "objectives": ["Identify epigenetic markers", "Synthesize clinical trials"],
        "hypotheses": ["PD-1 blockade restores progenitor exhausted T-cells."],
        "approval_status": "APPROVED",
        "approved_version": 1,
    }, db_path=temp_db)
    associate_artifact(proj.project_id, "brief", "brief-immuno-101", db_path=temp_db)

    # 3. Seed PRISMA Review
    save_prisma_review_db({
        "review_id": "rev-prisma-555",
        "brief_id": "brief-immuno-101",
        "session_id": "sess-immuno-1",
        "topic": "T-Cell Exhaustion Checkpoints",
        "protocol": {"databases": ["PubMed", "Europe PMC"]},
        "flow_counts": {"identified_databases": 15, "included_studies": 3},
        "evidence_matrix": {
            "included_studies": [
                {"study_id": "study-miller-2019", "synthesized_findings": "Progenitor exhausted T cells respond to PD-1", "doi": "10.1038/s41590-019-0312-6"}
            ]
        },
    }, db_path=temp_db)

    # 4. Seed Manuscript
    ms, rev = create_manuscript(
        project_id=proj.project_id,
        title="T-Cell Reinvigoration Manuscript",
        brief_id="brief-immuno-101",
        review_id="rev-prisma-555",
        db_path=temp_db,
    )

    # 5. Load consolidated workspace
    workspace = load_project_workspace(proj.project_id, session_id="sess-immuno-1", db_path=temp_db)
    assert workspace.project.project_id == proj.project_id
    assert len(workspace.ideas) == 2
    assert workspace.ideas[0]["idea_id"] == "idea-tcell-001"
    assert len(workspace.ideas[0]["revisions"]) == 2  # Lineage preserved!
    assert len(workspace.briefs) == 1

    assert workspace.briefs[0]["brief_id"] == "brief-immuno-101"
    assert len(workspace.prisma_reviews) == 1
    assert workspace.prisma_reviews[0]["review_id"] == "rev-prisma-555"
    assert len(workspace.manuscripts) == 1
    assert workspace.manuscripts[0]["manuscript_id"] == ms.manuscript_id

    # Scope Isolation: Attempting unauthorized load raises PermissionError
    with pytest.raises(PermissionError):
        load_project_workspace(proj.project_id, session_id="unauthorized-intruder", db_path=temp_db)


# ============================================================================
# 2. Deliverable B: Manuscript Engine & Claim Evolution Tests
# ============================================================================

def test_manuscript_creation_from_brief_and_review(temp_db):
    """Verify automatic structured academic manuscript instantiation from PRISMA review."""
    proj = create_project(title="Quantum Computing Benchmarks", db_path=temp_db)

    # Seed brief
    save_brief_db({
        "brief_id": "brief-qc-01",
        "topic": "Quantum Annealing vs Gate-Model Optimization",
        "research_question": "Does quantum annealing provide verifiable quantum speedup in QUBO problems?",
        "objectives": ["Synthesize benchmark results", "Evaluate noise mitigation"],
        "hypotheses": ["Quantum annealing achieves polynomial speedup on specific planar Ising spin-glass lattices."],
        "unresolved_questions": ["Is thermal noise masquerading as quantum tunneling?"],
    }, db_path=temp_db)

    # Seed review with included studies and dialectical contradictions
    save_prisma_review_db({
        "review_id": "rev-qc-99",
        "brief_id": "brief-qc-01",
        "topic": "Quantum Annealing Benchmarks",
        "protocol": {"databases": ["ArXiv", "IEEE Xplore"], "eligibility_criteria": ["Empirical benchmark"]},
        "evidence_matrix": {
            "included_studies": [
                {
                    "study_id": "study-dwave-2021",
                    "synthesized_findings": "Observed 10x runtime improvement on Chimera graph QUBOs",
                    "doi": "10.1103/PhysRevX.11.041001",
                }
            ],
            "dialectical_contradictions": [
                {
                    "hypothesis": "Quantum annealing achieves polynomial speedup on specific planar Ising spin-glass lattices.",
                    "supporting_study_id": "study-dwave-2021",
                    "opposing_finding": "Classical simulated annealing with path-integral Monte Carlo matches observed scaling.",
                    "synthesis_notes": "Quantum speedup remains contested under classical cluster updates.",
                }
            ],
        },
    }, db_path=temp_db)

    ms, rev = create_manuscript_from_brief_and_review(
        project_id=proj.project_id,
        brief_id="brief-qc-01",
        review_id="rev-qc-99",
        db_path=temp_db,
    )

    assert ms.project_id == proj.project_id
    assert ms.current_version == 1
    assert "abstract" in rev.sections
    assert "methodology" in rev.sections
    assert "results" in rev.sections
    assert "discussion" in rev.sections
    assert "limitations" in rev.sections
    assert "conclusion" in rev.sections

    # Check that claims were formulated from brief hypotheses and connected to studies
    assert len(rev.claims) == 1
    claim = rev.claims[0]
    assert claim["section"] == "results"
    assert "Quantum annealing achieves polynomial speedup" in claim["claim_text"]
    assert claim["evidence_status"] == "QUALIFIED"  # Because contradictions were present!
    assert len(claim["supporting_sources"]) == 1
    assert claim["supporting_sources"][0]["study_id"] == "study-dwave-2021"
    assert len(claim["counter_sources"]) == 1
    assert "Classical simulated annealing" in claim["counter_sources"][0]["counter_finding"]


def test_manuscript_multi_revision_evolution_and_stale_edit_prevention(temp_db):
    """Test non-destructive revision saving, claim diff calculation, and collision guards."""
    proj = create_project(title="Neuroplasticity Workspace", db_path=temp_db)

    ms, v1_rev = create_manuscript(
        project_id=proj.project_id,
        title="BDNF Regulation in Synaptogenesis",
        initial_claims=[
            {
                "claim_id": "clm_bdnf_1",
                "section": "Results",
                "claim_text": "Aerobic exercise upregulates hippocampal BDNF transcription by 40%.",
                "evidence_status": "SUPPORTED",
                "supporting_sources": [{"study_id": "study-cotman-2002", "citation_key": "cotman_2002"}],
            }
        ],
        db_path=temp_db,
    )
    assert ms.current_version == 1

    # Stale edit collision test: Attempting to save v2 specifying base_version=0 must fail
    with pytest.raises(ValueError) as excinfo:
        save_manuscript_revision(
            manuscript_id=ms.manuscript_id,
            title="BDNF Regulation in Synaptogenesis v2",
            sections=v1_rev.sections,
            claims=v1_rev.claims,
            references=v1_rev.references,
            author_notes="Concurrent collision edit",
            base_version=0,  # Invalid base version!
            db_path=temp_db,
        )
    assert "Stale edit conflict" in str(excinfo.value)

    # Valid revision save to v2: Modify claim text and add a new claim
    new_sections = dict(v1_rev.sections)
    new_sections["discussion"]["content"] = "Updated discussion with newly published cohort data."

    new_claims = [
        {
            "claim_id": "clm_bdnf_1",  # Same claim ID, changed wording
            "section": "Results",
            "claim_text": "Aerobic exercise reliably elevates hippocampal BDNF mRNA expression in adult mammals.",
            "evidence_status": "SUPPORTED",
            "supporting_sources": [{"study_id": "study-cotman-2002", "citation_key": "cotman_2002"}],
        },
        {
            "claim_id": "clm_bdnf_2",  # Newly added claim
            "section": "Results",
            "claim_text": "Resistance training yields localized IGF-1 upregulation but minimal BDNF release.",
            "evidence_status": "UNVERIFIED",
            "supporting_sources": [],
        },
    ]

    v2_rev = save_manuscript_revision(
        manuscript_id=ms.manuscript_id,
        title="BDNF Regulation in Synaptogenesis (Revised)",
        sections=new_sections,
        claims=new_claims,
        references=v1_rev.references,
        author_notes="Updated discussion and refined wording of BDNF upregulation",
        base_version=1,
        db_path=temp_db,
    )

    assert v2_rev.version == 2
    # Verify that v1 is still intact in storage!
    reloaded_v1 = get_manuscript_revision(ms.manuscript_id, version=1, db_path=temp_db)
    assert reloaded_v1 is not None
    assert reloaded_v1.version == 1
    assert len(reloaded_v1.claims) == 1
    assert "by 40%" in reloaded_v1.claims[0]["claim_text"]

    # Verify diff summary in v2
    diff = v2_rev.diff_summary
    assert diff["base_version"] == 1
    assert diff["new_version"] == 2
    assert "discussion" in diff["modified_sections"]
    assert "clm_bdnf_1" in diff["wording_changed_claims"]
    assert diff["added_claims_count"] == 1


def test_propose_claim_qualifications_from_new_evidence(temp_db):
    """Test proposing claim status updates and qualifications when new counter-evidence emerges."""
    proj = create_project(title="Nutritional Science", db_path=temp_db)
    ms, rev = create_manuscript(
        project_id=proj.project_id,
        title="Intermittent Fasting and Metabolic Health",
        initial_claims=[
            {
                "claim_id": "clm_fasting_1",
                "section": "Results",
                "claim_text": "Time-restricted eating significantly improves insulin sensitivity in non-diabetic cohorts.",
                "evidence_status": "SUPPORTED",
                "supporting_sources": [{"study_id": "study-sutton-2018"}],
            }
        ],
        db_path=temp_db,
    )

    new_evidence = [
        {
            "study_id": "study-lowe-2020",
            "finding": "Randomized trial shows no significant difference in insulin sensitivity during time-restricted eating when caloric intake is isocaloric.",
            "opposing_finding": "Isocaloric feeding nullifies observed glycemic benefits.",
        }
    ]

    proposals = propose_claim_qualifications_from_evidence(
        manuscript_id=ms.manuscript_id,
        new_evidence_items=new_evidence,
        db_path=temp_db,
    )

    assert len(proposals) == 1
    p = proposals[0]
    assert p["claim_id"] == "clm_fasting_1"
    assert p["current_status"] == "SUPPORTED"
    assert p["proposed_status"] == "QUALIFIED"
    assert "time-restricted eating" in p["suggested_qualification_text"].lower()


# ============================================================================
# 3. Deliverable C: Multi-Format Export Engine Tests
# ============================================================================

def test_export_engine_academic_markdown(temp_db):
    """Verify academic Markdown output format, headers, tables, and citation keys."""
    proj = create_project(title="Epigenetics", db_path=temp_db)
    ms, rev = create_manuscript(
        project_id=proj.project_id,
        title="DNA Methylation Aging Clock",
        initial_references=[
            {"citation_key": "horvath_2013", "title": "DNA methylation age of human tissues and cell types", "authors": ["Steve Horvath"], "year": 2013, "doi": "10.1186/gb-2013-14-10-r115", "verified": True}
        ],
        initial_claims=[
            {"claim_id": "clm_clock_1", "claim_text": "Epigenetic clock correlates with chronological age with r=0.96.", "evidence_status": "SUPPORTED", "supporting_sources": [{"citation_key": "horvath_2013"}]}
        ],
        db_path=temp_db,
    )

    res = export_manuscript(ms.manuscript_id, format_type="markdown", db_path=temp_db)
    assert res.format == "markdown"
    assert "# DNA Methylation Aging Clock" in res.content
    assert "## Claim-Level Evidential Ledger" in res.content
    assert "[@horvath_2013]" in res.content
    assert "https://doi.org/10.1186/gb-2013-14-10-r115" in res.content


def test_export_engine_latex_and_bibtex_verification(temp_db):
    """Verify compilable LaTeX structure, character escaping, and authentic BibTeX output without fabrication."""
    proj = create_project(title="Physics Workspace", db_path=temp_db)
    ms, rev = create_manuscript(
        project_id=proj.project_id,
        title="Analysis of 50% Speedup & Charge_Density in Quasi-Particles",  # Has %, &, _
        initial_references=[
            {
                "citation_key": "kitaev_2001",
                "title": "Unpaired Majorana fermions in quantum wires",
                "authors": ["A. Yu. Kitaev"],
                "year": 2001,
                "journal": "Physics-Uspekhi",
                "doi": "10.1070/1063-7869/44/10S/S29",
                "verified": True,
            },
            {
                "citation_key": "unverified_preprint",
                "title": "Preliminary observations of Majorana zero modes",
                "authors": ["Anonymous Research Group"],
                "year": 2024,
                "verified": False,  # Missing DOI, unverified!
            },
        ],
        initial_claims=[
            {
                "claim_id": "clm_majorana_1",
                "claim_text": "Non-Abelian statistics emerge in 1D topological superconductors.",
                "evidence_status": "SUPPORTED",
                "supporting_sources": [{"citation_key": "kitaev_2001"}],
            }
        ],
        db_path=temp_db,
    )

    # 1. LaTeX Test
    latex_res = export_manuscript(ms.manuscript_id, format_type="latex", db_path=temp_db)
    assert "\\documentclass[11pt,a4paper]{article}" in latex_res.content
    # Character escaping verified: % -> \%, & -> \&, _ -> \_
    assert "50\\% Speedup \\& Charge\\_Density" in latex_res.content
    assert "\\cite{kitaev_2001}" in latex_res.content
    assert "\\begin{thebibliography}" in latex_res.content
    assert "\\end{document}" in latex_res.content

    # 2. BibTeX Test
    bib_res = export_manuscript(ms.manuscript_id, format_type="bibtex", db_path=temp_db)
    assert "@article{kitaev_2001," in bib_res.content
    assert "doi = {10.1070/1063-7869/44/10S/S29}" in bib_res.content
    assert "Verified: true" in bib_res.content

    # Unverified entry must NOT have fabricated DOI or journal!
    assert "@misc{unverified_preprint," in bib_res.content
    assert "Note: Unverified entry - no persistent DOI confirmed" in bib_res.content
    assert bib_res.metadata["verified_entries"] == 1
    assert bib_res.metadata["unverified_entries"] == 1


def test_export_engine_publication_html_xss_protection_and_links(temp_db):
    """Verify HTML semantic markup, XSS escaping, interactive citation links, and badges."""
    proj = create_project(title="Web Security Workspace", db_path=temp_db)
    ms, rev = create_manuscript(
        project_id=proj.project_id,
        title="Study of <script>alert('xss')</script> Injection & Boundaries",
        initial_references=[
            {"citation_key": "smith_2022", "title": "Web Browser Security", "authors": ["Alice Smith"], "year": 2022, "doi": "10.1145/3372297.3417238", "verified": True}
        ],
        initial_claims=[
            {
                "claim_id": "clm_sec_1",
                "claim_text": "Cross-site scripting vectors bypass raw string concats.",
                "evidence_status": "SUPPORTED",
                "supporting_sources": [{"citation_key": "smith_2022"}],
            }
        ],
        db_path=temp_db,
    )

    html_res = export_manuscript(ms.manuscript_id, format_type="html", db_path=temp_db)
    assert "<!DOCTYPE html>" in html_res.content
    # XSS script tags must be escaped!
    assert "<script>" not in html_res.content
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_res.content
    # Internal jump link to reference
    assert "<a class=\"citation-link\" href=\"#ref-smith_2022\">[@smith_2022]</a>" in html_res.content
    assert "<li id=\"ref-smith_2022\">" in html_res.content
    # Evidence status badge
    assert "<span class=\"badge badge-supported\">SUPPORTED</span>" in html_res.content


# ============================================================================
# 4. Deliverable D: Interactive Traceability Tests
# ============================================================================

def test_drill_down_study_record_and_screening_decisions(temp_db):
    """Test drilling down into a study row to view screening decisions, appraisal, and linked claims."""
    proj = create_project(title="Cardiovascular Research", db_path=temp_db)

    # Save review
    save_prisma_review_db({
        "review_id": "rev-cardio-01",
        "brief_id": "brief-cardio-01",
        "topic": "SGLT2 Inhibitors",
        "evidence_matrix": {
            "included_studies": [
                {
                    "study_id": "study-empa-reg-2015",
                    "title": "Empagliflozin, Cardiovascular Outcomes, and Mortality",
                    "synthesized_findings": "Significant reduction in cardiovascular death (HR 0.62)",
                    "appraisal_notes": "Double-blind RCT; low risk of bias; sample N=7020",
                    "doi": "10.1056/NEJMoa1504720",
                    "source_url": "https://nejm.org/doi/10.1056/NEJMoa1504720",
                }
            ],
            "dialectical_contradictions": [],
        },
    }, db_path=temp_db)

    # Save screening decisions for multiple reports belonging to the study
    save_screening_decision_db({
        "decision_id": "dec-001",
        "review_id": "rev-cardio-01",
        "brief_id": "brief-cardio-01",
        "source_id": "pmid-26378978",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/26378978/",
        "title": "Empagliflozin in Type 2 Diabetes",
        "stage": "FULL_TEXT_ELIGIBILITY",
        "disposition": "INCLUDED",
        "study_id": "study-empa-reg-2015",
        "supporting_passages": ["Cardiovascular death occurred in 3.7% vs 5.9%."],
        "rationale": "Meets primary outcome criteria.",
    }, db_path=temp_db)

    save_screening_decision_db({
        "decision_id": "dec-002",
        "review_id": "rev-cardio-01",
        "brief_id": "brief-cardio-01",
        "source_id": "pmid-27088923",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/27088923/",
        "title": "Empagliflozin and Heart Failure Subanalysis",
        "stage": "FULL_TEXT_ELIGIBILITY",
        "disposition": "INCLUDED",
        "study_id": "study-empa-reg-2015",
        "supporting_passages": ["Heart failure hospitalizations reduced by 35%."],
        "rationale": "Secondary outcome report for study-empa-reg-2015.",
    }, db_path=temp_db)

    # Save manuscript referencing this study
    ms, rev = create_manuscript(
        project_id=proj.project_id,
        title="Cardiovascular Pharmacology Review",
        initial_claims=[
            {
                "claim_id": "clm_sglt2_cv",
                "claim_text": "SGLT2 inhibitors reduce cardiovascular death in diabetic patients.",
                "evidence_status": "SUPPORTED",
                "supporting_sources": [{"study_id": "study-empa-reg-2015"}],
            }
        ],
        db_path=temp_db,
    )

    # Drill down into study
    study_detail = drill_down_study_record("study-empa-reg-2015", review_id="rev-cardio-01", db_path=temp_db)
    assert study_detail is not None
    assert study_detail.study_id == "study-empa-reg-2015"
    assert study_detail.reports_count == 2
    assert len(study_detail.associated_reports) == 2
    assert len(study_detail.screening_decisions) == 2
    assert study_detail.appraisal["risk_of_bias"] == "Low"
    assert "Double-blind RCT" in study_detail.appraisal["methodological_appraisal"]

    # Bidirectional link to manuscript claim verified!
    assert len(study_detail.referenced_claims) == 1
    assert study_detail.referenced_claims[0]["claim_id"] == "clm_sglt2_cv"


def test_flow_node_records_and_claim_traceability(temp_db):
    """Test resolving PRISMA flow nodes to underlying records and navigating from claim to study."""
    # Seed review first to satisfy FK constraint
    save_prisma_review_db({
        "review_id": "rev-test-1",
        "brief_id": "brief-1",
        "topic": "Test Review",
        "evidence_matrix": {"included_studies": [{"study_id": "study-alpha-1", "synthesized_findings": "Alpha confirmed"}]},
    }, db_path=temp_db)

    # Seed screening decisions for different flow stages
    save_screening_decision_db({
        "decision_id": "dec-sc-1",
        "review_id": "rev-test-1",
        "brief_id": "brief-1",
        "source_id": "src-1",
        "title": "Relevant Study Title",
        "stage": "TITLE_ABSTRACT",
        "disposition": "INCLUDED",
    }, db_path=temp_db)

    save_screening_decision_db({
        "decision_id": "dec-sc-2",
        "review_id": "rev-test-1",
        "brief_id": "brief-1",
        "source_id": "src-2",
        "title": "Irrelevant Animal Model",
        "stage": "TITLE_ABSTRACT",
        "disposition": "EXCLUDED",
        "exclusion_reason": "Non-human population",
    }, db_path=temp_db)

    save_screening_decision_db({
        "decision_id": "dec-el-1",
        "review_id": "rev-test-1",
        "brief_id": "brief-1",
        "source_id": "src-1",
        "title": "Relevant Study Title",
        "stage": "FULL_TEXT_ELIGIBILITY",
        "disposition": "INCLUDED",
        "study_id": "study-alpha-1",
    }, db_path=temp_db)


    # 1. Flow node drill-down: screening exclusions
    screened_excl = get_flow_node_records("screened_excluded", review_id="rev-test-1", db_path=temp_db)
    assert screened_excl.total_count == 1
    assert screened_excl.records[0]["decision_id"] == "dec-sc-2"

    # 2. Flow node drill-down: included studies
    inc_studies = get_flow_node_records("included_studies", review_id="rev-test-1", db_path=temp_db)
    assert inc_studies.total_count == 1
    assert inc_studies.records[0]["study_id"] == "study-alpha-1"

    # 3. Bidirectional claim navigation
    p_alpha = create_project(title="Alpha Mechanism Project", db_path=temp_db)
    ms, rev = create_manuscript(
        project_id=p_alpha.project_id,
        title="Alpha Manuscript",

        initial_claims=[
            {
                "claim_id": "clm_alpha",
                "claim_text": "Alpha mechanism operates under standard physiological temperature.",
                "evidence_status": "SUPPORTED",
                "supporting_sources": [{"study_id": "study-alpha-1"}],
            }
        ],
        db_path=temp_db,
    )

    trace = get_claim_traceability("clm_alpha", db_path=temp_db)
    assert trace["claim"]["claim_id"] == "clm_alpha"
    assert trace["evidence_status"] == "SUPPORTED"
    assert len(trace["resolved_supporting_studies"]) == 1
    assert trace["resolved_supporting_studies"][0]["study_id"] == "study-alpha-1"


# ============================================================================
# 5. REST API Integration Tests
# ============================================================================

def test_workspace_api_endpoints():
    """Verify FastAPI routes for projects, manuscripts, revisions, exports, and traceability."""
    client = TestClient(app)

    # 1. Create Project
    res = client.post("/api/projects", json={
        "title": "API Automated Test Project",
        "description": "Integration testing through TestClient",
        "session_id": "api-sess-1",
        "metadata": {"test": True},
    })
    assert res.status_code == 201
    p_data = res.json()["project"]
    proj_id = p_data["project_id"]

    # 2. List Projects
    res = client.get("/api/projects?session_id=api-sess-1")
    assert res.status_code == 200
    assert len(res.json()["projects"]) >= 1

    # 3. Create Manuscript
    res = client.post("/api/manuscripts", json={
        "project_id": proj_id,
        "title": "API Test Manuscript",
        "claims": [
            {
                "claim_id": "clm_api_1",
                "section": "Results",
                "claim_text": "API response time adheres to Doherty threshold.",
                "evidence_status": "SUPPORTED",
                "supporting_sources": [{"study_id": "benchmark_1", "citation_key": "bench_1"}],
            }
        ],
        "references": [
            {"citation_key": "bench_1", "title": "Doherty Performance", "authors": ["W. Doherty"], "year": 1982}
        ],
    })
    assert res.status_code == 201
    m_data = res.json()["manuscript"]
    ms_id = m_data["manuscript_id"]

    # 4. Get Manuscript & Revisions
    res = client.get(f"/api/manuscripts/{ms_id}")
    assert res.status_code == 200
    assert res.json()["manuscript"]["current_version"] == 1

    res = client.get(f"/api/manuscripts/{ms_id}/revisions")
    assert res.status_code == 200
    assert len(res.json()["revisions"]) == 1

    # 5. Save Revision v2
    curr_rev = client.get(f"/api/manuscripts/{ms_id}/revisions/1").json()["revision"]
    res = client.post(f"/api/manuscripts/{ms_id}/revisions", json={
        "title": "API Test Manuscript v2",
        "sections": curr_rev["sections"],
        "claims": curr_rev["claims"],
        "references": curr_rev["references"],
        "author_notes": "Bump to v2 via API",
        "base_version": 1,
    })
    assert res.status_code == 201
    assert res.json()["revision"]["version"] == 2

    # 6. Export Manuscript to HTML
    res = client.post(f"/api/manuscripts/{ms_id}/export", json={"format": "html"})
    assert res.status_code == 200
    exp_data = res.json()["export"]
    assert exp_data["format"] == "html"
    exp_id = exp_data["export_id"]

    # 7. Get Export Artifact
    res = client.get(f"/api/exports/{exp_id}")
    assert res.status_code == 200
    assert "<!DOCTYPE html>" in res.json()["export"]["content"]

    # 8. Get Claim Traceability
    res = client.get("/api/traceability/claims/clm_api_1")
    assert res.status_code == 200
    assert res.json()["traceability"]["claim"]["claim_id"] == "clm_api_1"

    # 9. Get Project Workspace
    res = client.get(f"/api/projects/{proj_id}")
    assert res.status_code == 200
    ws = res.json()["workspace"]
    assert ws["project"]["project_id"] == proj_id
    assert len(ws["manuscripts"]) == 1
    assert len(ws["exports"]) >= 1

    # 10. Archive and Delete Project
    res = client.post(f"/api/projects/{proj_id}/archive")
    assert res.status_code == 200
    assert res.json()["archived"] is True

    res = client.delete(f"/api/projects/{proj_id}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
