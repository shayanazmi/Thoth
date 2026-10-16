"""
THOTH Phase 6 Verification Test Suite
Advanced Research Execution, PDF Publishing & Production Collaboration.

Comprehensive tests covering:
1. Deliverable A: Server-side binary PDF generation (LaTeX & ReportLab), magic byte & page validation, export download.
2. Deliverable B: Recursive citation snowballing, forward/backward discovery, cycle prevention, marginal yield decay, PRISMA accounting.
3. Deliverable C: Multi-tenant RBAC permissions, member management, outbox queueing, collision detection, cloud sync replay.
4. End-to-end integration: Brief -> Review -> Snowballing -> Manuscript -> Binary PDF.
"""

import os
import tempfile
import pytest
import pypdf
from fastapi.testclient import TestClient

from backend.main import app
from backend.memory.db import (
    init_db,
    save_brief_db,
    save_prisma_review_db,
    get_prisma_review_db,
    list_screening_decisions_db,
    get_manuscript_export_db,
)
from backend.workspace.project import create_project, get_project
from backend.workspace.manuscript import create_manuscript, save_manuscript_revision
from backend.workspace.exporter import export_manuscript, ExportFormat
from backend.workspace.pdf_compiler import (
    compile_latex_to_pdf,
    compile_reportlab_to_pdf,
    compile_manuscript_to_pdf,
    find_latex_executable,
    validate_pdf_bytes,
    PDFCompilerError,
)
from backend.scholarly import SourceCandidate
from backend.intellectual_rigour.snowball import (
    SnowballConfig,
    SnowballDirection,
    StoppingReason,
    run_recursive_snowball,
)
from backend.collaboration.membership import (
    ProjectRole,
    ProjectPermission,
    can_user_perform,
    add_project_member,
    list_project_members,
    remove_project_member,
    verify_project_access,
)
from backend.collaboration.sync import (
    SyncOperation,
    SyncStatus,
    queue_sync_event,
    replay_sync_outbox,
    get_project_sync_status,
)


@pytest.fixture
def isolated_db():
    """Provides a sterile, isolated SQLite database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    init_db(temp_path)
    yield temp_path
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def test_client():
    return TestClient(app)


# ==============================================================================
# Deliverable A: PDF Compilation & Publication Pipeline Tests
# ==============================================================================

class TestPDFCompilation:
    def test_reportlab_pdf_compilation(self):
        """Verify pure-Python ReportLab compilation generates valid binary PDF with expected structure."""
        revision = {
            "title": "Empirical Analysis of Attention Mechanisms",
            "version": 1,
            "author_notes": "First drafted revision",
            "sections": {
                "abstract": "This study analyzes scaling laws of multi-head self-attention mechanisms.",
                "introduction": "Transformer models rely heavily on dot-product attention.\n\nHere we evaluate scaling efficiency.",
                "methods": "We conducted controlled benchmarking on standard GLUE tasks.",
                "results": "Sparse attention reduces quadratic computational complexity to O(N log N).",
                "discussion": "The findings substantiate hypothesis H1 under constrained compute.",
            },
            "evidence_matrix": {
                "studies": [
                    {
                        "study_id": "study_vaswani_2017",
                        "title": "Attention Is All You Need",
                        "authors": ["Vaswani, A.", "Shazeer, N."],
                        "study_design": "Benchmark Evaluation",
                        "sample_or_dataset": "WMT 2014 En-De",
                        "hypothesis_relation": "SUPPORTS",
                        "key_findings": ["Transformer establishes new state-of-the-art BLEU score."],
                    }
                ]
            },
            "claims": [
                {
                    "claim_text": "Sparse attention preserves 98% of dense attention task performance.",
                    "evidence_status": "SUPPORTED",
                    "confidence": 0.92,
                }
            ],
            "references": [
                {
                    "title": "Attention Is All You Need",
                    "authors": ["Vaswani, A.", "et al."],
                    "year": "2017",
                    "doi": "10.5555/3295222.3295349",
                }
            ],
        }

        pdf_bytes, meta = compile_reportlab_to_pdf(revision)

        assert pdf_bytes is not None
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF-")
        assert meta["engine"] == "reportlab"
        assert meta["page_count"] >= 1
        assert "sha256" in meta

        # Deep verification with pypdf
        is_valid, pages, val_meta = validate_pdf_bytes(pdf_bytes)
        assert is_valid is True
        assert pages >= 1

    def test_pdflatex_compilation_if_available(self):
        """Verify pdflatex compiles LaTeX document to valid binary PDF when binary exists on system."""
        exe = find_latex_executable("pdflatex")
        if not exe:
            pytest.skip("pdflatex binary not found on test environment.")

        latex_doc = r"""
        \documentclass{article}
        \title{THOTH Test Manuscript}
        \author{THOTH Intelligence System}
        \date{\today}
        \begin{document}
        \maketitle
        \begin{abstract}
        Testing server-side LaTeX compilation in THOTH.
        \end{abstract}
        \section{Introduction}
        This is an automated regression test verifying real binary PDF output.
        \end{document}
        """

        pdf_bytes, meta = compile_latex_to_pdf(latex_doc)
        assert pdf_bytes.startswith(b"%PDF-")
        assert meta["engine"] == "pdflatex"
        assert meta["page_count"] >= 1

    def test_latex_compilation_error_handling(self):
        """Verify invalid LaTeX input raises PDFCompilerError with inspectable error diagnostics."""
        exe = find_latex_executable("pdflatex")
        if not exe:
            pytest.skip("pdflatex binary not found on test environment.")

        broken_latex = r"""
        \documentclass{article}
        \begin{document}
        \invalidlatexcommandwithoutdefinition{%$#
        """
        with pytest.raises(PDFCompilerError) as exc_info:
            compile_latex_to_pdf(broken_latex, timeout_seconds=10.0)

        err = exc_info.value
        assert err.stage == "latex_compilation"
        assert "exit_code" in err.details

    def test_export_manuscript_pdf_integration(self, isolated_db):
        """Verify export_manuscript with format_type='pdf' persists binary artifact in database."""
        proj = create_project(title="PDF Project", db_path=isolated_db)
        ms, rev = create_manuscript(
            project_id=proj.project_id,
            title="Publication Manuscript",
            initial_sections={"abstract": "Export abstract", "introduction": "Export intro"},
            db_path=isolated_db,
        )

        export_res = export_manuscript(
            manuscript_id=ms.manuscript_id,
            format_type="pdf",
            version=1,
            pdf_engine="reportlab",
            db_path=isolated_db,
        )

        assert export_res.format == "pdf"
        assert export_res.metadata["content_type"] == "application/pdf"
        assert export_res.metadata["encoding"] == "base64"
        assert export_res.metadata["page_count"] >= 1

        db_rec = get_manuscript_export_db(export_res.export_id, db_path=isolated_db)
        assert db_rec is not None
        assert db_rec["format"] == "pdf"

    def test_api_download_export_pdf(self, test_client, isolated_db, monkeypatch):
        """Verify GET /api/exports/{id}/download serves application/pdf binary response."""
        monkeypatch.setattr("backend.memory.db.DEFAULT_DB_PATH", isolated_db)

        proj = create_project(title="Download Project", db_path=isolated_db)
        ms, _ = create_manuscript(
            project_id=proj.project_id,
            title="Downloadable Article",
            initial_sections={"abstract": "Testing binary download"},
            db_path=isolated_db,
        )
        export_res = export_manuscript(
            manuscript_id=ms.manuscript_id,
            format_type="pdf",
            version=1,
            pdf_engine="reportlab",
            db_path=isolated_db,
        )

        resp = test_client.get(f"/api/exports/{export_res.export_id}/download?db_path={isolated_db}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF-")


# ==============================================================================
# Deliverable B: Recursive Citation Snowballing Tests
# ==============================================================================

class TestCitationSnowballing:
    @pytest.mark.asyncio
    async def test_backward_and_forward_discovery(self, isolated_db):
        """Verify backward (cited references) and forward (citing papers) discover candidates with provenance."""
        seed = SourceCandidate(
            title="Seed Paper on Deep Learning",
            paper_id="seed_101",
            doi="10.1000/seed101",
        )

        async def mock_references(paper_id, limit=5):
            return [
                SourceCandidate(
                    title=f"Ref cited by {paper_id}",
                    paper_id=f"ref_{paper_id}",
                    doi=f"10.1000/ref_{paper_id}",
                    source_api="semantic_scholar_references",
                )
            ]

        async def mock_citations(paper_id, limit=5):
            return [
                SourceCandidate(
                    title=f"Paper citing {paper_id}",
                    paper_id=f"cite_{paper_id}",
                    doi=f"10.1000/cite_{paper_id}",
                    source_api="semantic_scholar_citations",
                )
            ]

        # Create a PRISMA review to bind
        brief = save_brief_db({
            "brief_id": "brief_snb_1",
            "topic": "Deep Learning Foundations",
            "research_question": "What are the core foundations?",
        }, db_path=isolated_db)
        save_prisma_review_db(
            review_data={
                "review_id": "rev_snb_1",
                "brief_id": brief["brief_id"],
                "topic": "Deep Learning",
                "protocol": {"search_queries": ["deep learning"]},
                "flow_counts": {"total_identified": 1, "records_screened": 1},
            },
            db_path=isolated_db,
        )

        config = SnowballConfig(max_depth=1, limit_per_paper=2)
        res = await run_recursive_snowball(
            seeds=[seed],
            review_id="rev_snb_1",
            brief_id=brief["brief_id"],
            config=config,
            references_fn=mock_references,
            citations_fn=mock_citations,
            db_path=isolated_db,
        )

        assert res.total_rounds == 1
        assert res.unique_candidates == 2  # 1 backward + 1 forward
        directions = {c.direction for c in res.candidates}
        assert SnowballDirection.BACKWARD in directions
        assert SnowballDirection.FORWARD in directions

        # Verify provenance
        for c in res.candidates:
            assert c.parent_paper_id == "seed_101"
            assert c.round_number == 1
            assert c.is_duplicate is False

    @pytest.mark.asyncio
    async def test_cycle_prevention_terminates_safely(self, isolated_db):
        """Verify circular citations (Paper A cites B, B cites A) do not cause infinite loops."""
        paper_a = SourceCandidate(title="Paper A", paper_id="p_A", doi="10.1/a")
        paper_b = SourceCandidate(title="Paper B", paper_id="p_B", doi="10.1/b")

        async def mock_circular_refs(paper_id, limit=5):
            if paper_id in ("p_A", "10.1/a", "Paper A"):
                return [paper_b]
            elif paper_id in ("p_B", "10.1/b", "Paper B"):
                return [paper_a]
            return []

        config = SnowballConfig(max_depth=5, enable_forward=False)
        res = await run_recursive_snowball(
            seeds=[paper_a],
            review_id="rev_dummy",
            brief_id="brief_dummy",
            config=config,
            references_fn=mock_circular_refs,
            citations_fn=lambda p, limit=5: [],
            db_path=isolated_db,
        )

        # Should discover Paper B in round 1, then in round 2 Paper A is detected as duplicate, stopping safely
        assert res.total_rounds >= 1
        assert res.unique_candidates == 1  # Only B is newly discovered
        assert res.duplicates_count >= 1

    @pytest.mark.asyncio
    async def test_marginal_yield_decay_stopping(self, isolated_db):
        """Verify traversal stops early when marginal yield falls below threshold."""
        seed = SourceCandidate(title="Root Study", paper_id="root_1")

        call_count = 0
        async def mock_decaying_refs(paper_id, limit=5):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    SourceCandidate(title="Child 1", paper_id="c1"),
                    SourceCandidate(title="Child 2", paper_id="c2"),
                ]
            # Subsequent rounds yield nothing new
            return []

        config = SnowballConfig(max_depth=5, marginal_yield_threshold=0.25, enable_forward=False)
        res = await run_recursive_snowball(
            seeds=[seed],
            review_id="rev_dummy",
            brief_id="brief_dummy",
            config=config,
            references_fn=mock_decaying_refs,
            citations_fn=lambda p, limit=5: [],
            db_path=isolated_db,
        )

        assert res.stopping_reason in (StoppingReason.MARGINAL_YIELD_DECAY, StoppingReason.CONSECUTIVE_ZERO_YIELD, StoppingReason.NO_FURTHER_SEEDS)
        assert res.total_rounds < 5

    @pytest.mark.asyncio
    async def test_prisma_flow_accounting_integration(self, isolated_db):
        """Verify newly discovered candidates update PRISMA review flow counts without violating mathematical invariants."""
        brief = save_brief_db({
            "brief_id": "brief_snb_flow",
            "topic": "Topic",
            "research_question": "Question",
        }, db_path=isolated_db)
        save_prisma_review_db(
            review_data={
                "review_id": "rev_snb_flow",
                "brief_id": brief["brief_id"],
                "topic": "Topic",
                "protocol": {},
                "flow_counts": {
                    "identified_databases": 10,
                    "identified_registries_web": 2,
                    "identified_snowball": 0,
                    "total_identified": 12,
                    "duplicates_removed": 2,
                    "records_screened": 10,
                },
            },
            db_path=isolated_db,
        )

        seed = SourceCandidate(title="Seed Study", paper_id="seed_p1")
        async def mock_refs(paper_id, limit=5):
            return [
                SourceCandidate(title="Discovered 1", paper_id="d1", abstract="Abstract 1"),
                SourceCandidate(title="Discovered 2", paper_id="d2", abstract="Abstract 2"),
            ]

        config = SnowballConfig(max_depth=1, enable_forward=False)
        await run_recursive_snowball(
            seeds=[seed],
            review_id="rev_snb_flow",
            brief_id=brief["brief_id"],
            config=config,
            references_fn=mock_refs,
            citations_fn=lambda p, limit=5: [],
            db_path=isolated_db,
        )

        updated_rev = get_prisma_review_db("rev_snb_flow", db_path=isolated_db)
        flow = updated_rev["flow_counts"]

        assert flow["identified_snowball"] == 2
        assert flow["total_identified"] == 14  # 10 + 2 + 2
        assert flow["records_screened"] == 12  # 14 - 2 duplicates

        # Check screening decisions
        decisions = list_screening_decisions_db("rev_snb_flow", db_path=isolated_db)
        assert len(decisions) == 2
        for d in decisions:
            assert d["stage"] == "TITLE_ABSTRACT"
            assert d["disposition"] == "UNRESOLVED"
            assert "snowball" in d["rationale"]


# ==============================================================================
# Deliverable C: Production Collaboration & Cloud Synchronization Tests
# ==============================================================================

class TestCollaborationAndSync:
    def test_project_role_permissions(self):
        """Verify OWNER, EDITOR, and VIEWER RBAC permissions."""
        assert can_user_perform(ProjectRole.OWNER, ProjectPermission.DELETE_PROJECT) is True
        assert can_user_perform(ProjectRole.OWNER, ProjectPermission.MANAGE_MEMBERS) is True

        assert can_user_perform(ProjectRole.EDITOR, ProjectPermission.EDIT_MANUSCRIPT) is True
        assert can_user_perform(ProjectRole.EDITOR, ProjectPermission.CREATE_MANUSCRIPT) is True
        assert can_user_perform(ProjectRole.EDITOR, ProjectPermission.DELETE_PROJECT) is False
        assert can_user_perform(ProjectRole.EDITOR, ProjectPermission.MANAGE_MEMBERS) is False

        assert can_user_perform(ProjectRole.VIEWER, ProjectPermission.READ_PROJECT) is True
        assert can_user_perform(ProjectRole.VIEWER, ProjectPermission.EXPORT_MANUSCRIPT) is True
        assert can_user_perform(ProjectRole.VIEWER, ProjectPermission.EDIT_MANUSCRIPT) is False

    def test_add_and_list_project_members(self, isolated_db):
        """Verify project member invitation, listing, and access verification."""
        proj = create_project(title="Collaborative Lab", session_id="owner_alice", db_path=isolated_db)

        # Owner Alice has full access
        has_acc, role = verify_project_access(proj.project_id, "owner_alice", ProjectPermission.DELETE_PROJECT, db_path=isolated_db)
        assert has_acc is True
        assert role == ProjectRole.OWNER

        # Add Bob as EDITOR
        member_bob = add_project_member(
            project_id=proj.project_id,
            user_id="bob_editor",
            role="EDITOR",
            inviter_id="owner_alice",
            db_path=isolated_db,
        )
        assert member_bob.role == ProjectRole.EDITOR

        # Verify Bob has EDIT_MANUSCRIPT but not DELETE_PROJECT
        has_edit, _ = verify_project_access(proj.project_id, "bob_editor", ProjectPermission.EDIT_MANUSCRIPT, db_path=isolated_db)
        assert has_edit is True
        has_del, _ = verify_project_access(proj.project_id, "bob_editor", ProjectPermission.DELETE_PROJECT, db_path=isolated_db)
        assert has_del is False

        # List members
        members = list_project_members(proj.project_id, db_path=isolated_db)
        assert len(members) == 1
        assert members[0].user_id == "bob_editor"

    def test_remove_project_member_guard(self, isolated_db):
        """Verify non-owner cannot remove members and project owner cannot be removed."""
        proj = create_project(title="Secure Lab", session_id="owner_alice", db_path=isolated_db)
        add_project_member(proj.project_id, "charlie_editor", role="EDITOR", db_path=isolated_db)
        add_project_member(proj.project_id, "dave_viewer", role="VIEWER", db_path=isolated_db)

        # Viewer Dave tries to remove Charlie -> fails
        with pytest.raises(PermissionError):
            remove_project_member(proj.project_id, "charlie_editor", remover_id="dave_viewer", db_path=isolated_db)

        # Try to remove project owner -> fails
        with pytest.raises(ValueError):
            remove_project_member(proj.project_id, "owner_alice", remover_id="owner_alice", db_path=isolated_db)

        # Owner Alice removes Dave -> succeeds
        ok = remove_project_member(proj.project_id, "dave_viewer", remover_id="owner_alice", db_path=isolated_db)
        assert ok is True

    def test_outbox_queueing_offline_resilience(self, isolated_db):
        """Verify local mutations are queued in sync_outbox with PENDING status for offline preservation."""
        proj = create_project(title="Offline Project", db_path=isolated_db)
        evt = queue_sync_event(
            entity_type="manuscripts",
            entity_id="ms_test_123",
            operation=SyncOperation.INSERT,
            payload={"title": "Draft in offline mode"},
            project_id=proj.project_id,
            db_path=isolated_db,
        )

        assert evt.status == SyncStatus.PENDING
        status_info = get_project_sync_status(proj.project_id, db_path=isolated_db)
        assert status_info["pending_count"] == 1
        assert status_info["synced_count"] == 0

        # Replaying without Supabase client preserves events safely
        replay_res = replay_sync_outbox(supabase_client=None, project_id=proj.project_id, db_path=isolated_db)
        assert replay_res.get("offline_mode") is True
        assert replay_res["processed"] == 1
        assert replay_res["synced"] == 0

    def test_outbox_replay_and_conflict_detection(self, isolated_db):
        """Verify revision conflict detection flags CONFLICT when remote version diverges from local base_version."""
        proj = create_project(title="Sync Project", db_path=isolated_db)

        # Queue a revision with base_version 1
        queue_sync_event(
            entity_type="manuscript_revisions",
            entity_id="rev_conflict_1",
            operation=SyncOperation.INSERT,
            payload={"manuscript_id": "ms_target", "version": 2, "base_version": 1},
            project_id=proj.project_id,
            db_path=isolated_db,
        )

        # Mock Supabase client where remote manuscript version has already advanced to v3
        class MockRemoteTable:
            def select(self, *args):
                return self
            def eq(self, *args):
                return self
            def order(self, *args, **kwargs):
                return self
            def limit(self, *args):
                return self
            def execute(self):
                class MockResponse:
                    data = [{"version": 3}]
                return MockResponse()

        class MockSupabaseClient:
            def table(self, name):
                return MockRemoteTable()

        res = replay_sync_outbox(
            supabase_client=MockSupabaseClient(),
            project_id=proj.project_id,
            db_path=isolated_db,
        )

        assert res["conflicts"] == 1
        assert res["results"][0]["status"] == "CONFLICT"

        # Check status in DB
        status_info = get_project_sync_status(proj.project_id, db_path=isolated_db)
        assert status_info["conflict_count"] == 1


# ==============================================================================
# End-to-End Workflow Integration Test
# ==============================================================================

class TestEndToEndPhase6Workflow:
    @pytest.mark.asyncio
    async def test_complete_research_to_pdf_pipeline(self, isolated_db):
        """
        Tests complete integrated research lifecycle:
        1. Research Brief definition.
        2. PRISMA review initialization.
        3. Citation Snowballing discovers new candidate studies.
        4. Screening decision incorporates discovered study.
        5. Manuscript revision tracks claims with evidence matrix.
        6. Binary PDF compilation produces validated publication artifact.
        """
        # 1. Research Brief
        brief = save_brief_db({
            "brief_id": "brief_e2e_6",
            "topic": "Transformer Reasoning Latency",
            "research_question": "Does speculative decoding reduce latency without degradation?",
        }, db_path=isolated_db)

        # 2. PRISMA Review
        save_prisma_review_db(
            review_data={
                "review_id": "rev_e2e_6",
                "brief_id": brief["brief_id"],
                "topic": brief["topic"],
                "protocol": {"search_queries": ["speculative decoding"]},
                "flow_counts": {"total_identified": 1, "records_screened": 1},
            },
            db_path=isolated_db,
        )

        # 3. Citation Snowballing
        seed = SourceCandidate(title="Fast Inference via Speculative Decoding", paper_id="seed_spec_1")
        async def mock_lookups(paper_id, limit=5):
            return [
                SourceCandidate(
                    title="Blockwise Parallel Decoding for Deep Autoregressive Models",
                    paper_id="spec_ref_1",
                    abstract="Introduces multi-token prediction heads achieving 2.5x speedup.",
                    doi="10.1000/blockwise2018",
                )
            ]

        snowball_res = await run_recursive_snowball(
            seeds=[seed],
            review_id="rev_e2e_6",
            brief_id=brief["brief_id"],
            config=SnowballConfig(max_depth=1),
            references_fn=mock_lookups,
            citations_fn=lambda p, limit=5: [],
            db_path=isolated_db,
        )
        assert snowball_res.unique_candidates == 1

        # 4. Project Workspace & Manuscript
        proj = create_project(title="Speculative Inference Project", db_path=isolated_db)
        ms, rev = create_manuscript(
            project_id=proj.project_id,
            title="Comprehensive Study on Speculative Decoding",
            brief_id=brief["brief_id"],
            review_id="rev_e2e_6",
            initial_sections={
                "abstract": "Speculative decoding accelerates generative language model inference.",
                "introduction": "Autoregressive generation suffers from memory bandwidth memory stalls.",
                "evidence_synthesis": "Empirical studies verify speculative draft models achieve 2.0-3.0x speedups.",
            },
            initial_claims=[
                {
                    "claim_text": "Speculative decoding produces identical output distribution to target model.",
                    "evidence_status": "SUPPORTED",
                    "confidence": 0.99,
                }
            ],
            initial_references=[
                {
                    "title": "Blockwise Parallel Decoding for Deep Autoregressive Models",
                    "authors": ["Stern, M.", "et al."],
                    "year": "2018",
                    "doi": "10.1000/blockwise2018",
                }
            ],
            db_path=isolated_db,
        )

        # 5. Compile Binary PDF
        export_res = export_manuscript(
            manuscript_id=ms.manuscript_id,
            format_type="pdf",
            version=rev.version,
            pdf_engine="reportlab",
            db_path=isolated_db,
        )

        assert export_res.format == "pdf"
        assert export_res.metadata["page_count"] >= 1
        assert export_res.metadata["content_type"] == "application/pdf"
        assert export_res.content is not None  # base64 representation present
