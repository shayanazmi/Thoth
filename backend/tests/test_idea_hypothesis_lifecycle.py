import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.memory.db import init_db, get_connection
from backend.conversation.idea import (
    create_tentative_idea,
    promote_idea_to_artifact,
    revise_idea,
    abandon_idea,
    get_idea,
    list_ideas,
    get_idea_history,
    attach_idea_to_brief,
    IdeaStatus,
    ResearchIdea,
)
from backend.conversation.brief import (
    prepare_research_brief,
    get_research_brief,
    update_research_brief,
    approve_research_brief,
    BriefApprovalStatus,
)
from backend.main import app


@pytest.fixture
def isolated_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_ideas.db")
    init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_tentative_idea_creation_starts_in_tentative_state(isolated_db):
    """
    Mandate invariant: Exploratory conversation must not automatically create
    promoted persistent research artifacts without user consent.
    """
    idea = create_tentative_idea(
        title="Synaptic Pruning in Graph Neural Networks",
        hypothesis="Dynamic threshold pruning mimics biological synaptic plasticity in GNNs.",
        description="Exploring bio-plausible architectures for graph representation learning.",
        session_id="session-spar-001",
        thinker_id="darwin",
        thinker_critique="Ensure fitness selection criteria are clearly operationalized.",
        unresolved_objections=["What prevents premature convergence in dense clusters?"],
        db_path=isolated_db,
    )

    assert idea.idea_id.startswith("idea-")
    assert idea.status == IdeaStatus.TENTATIVE
    assert idea.revision_version == 1
    assert idea.parent_idea_id is None
    assert idea.brief_id is None
    assert idea.thinker_id == "darwin"
    assert len(idea.unresolved_objections) == 1

    # Verify persistent retrieval
    fetched = get_idea(idea.idea_id, db_path=isolated_db)
    assert fetched is not None
    assert fetched.title == idea.title
    assert fetched.hypothesis == idea.hypothesis
    assert fetched.status == IdeaStatus.TENTATIVE


def test_promotion_barrier_blocks_unapproved_promotion(isolated_db):
    """
    Mandate invariant: Explicit user approval is required before promoting a
    tentative idea into persistent project storage.
    """
    idea = create_tentative_idea(
        title="Zero-Shot Epistemic Grounding",
        hypothesis="Synthesizing multi-framework critiques eliminates ungrounded hallucination.",
        db_path=isolated_db,
    )

    # Attempt promotion without user approval
    success, res, msg = promote_idea_to_artifact(idea.idea_id, user_approved=False, db_path=isolated_db)
    assert success is False
    assert "Promotion Barrier" in msg
    assert res.status == IdeaStatus.TENTATIVE

    # Verify DB status was NOT altered
    fetched = get_idea(idea.idea_id, db_path=isolated_db)
    assert fetched.status == IdeaStatus.TENTATIVE


def test_promotion_succeeds_with_explicit_user_approval(isolated_db):
    """
    Mandate invariant: Once the user explicitly approves promotion, the idea
    transitions to PROMOTED status.
    """
    idea = create_tentative_idea(
        title="Zero-Shot Epistemic Grounding",
        hypothesis="Synthesizing multi-framework critiques eliminates ungrounded hallucination.",
        db_path=isolated_db,
    )

    # Explicit user approval
    success, promoted, msg = promote_idea_to_artifact(idea.idea_id, user_approved=True, db_path=isolated_db)
    assert success is True
    assert promoted.status == IdeaStatus.PROMOTED
    assert "successfully promoted" in msg

    # Verify DB status was updated
    fetched = get_idea(idea.idea_id, db_path=isolated_db)
    assert fetched.status == IdeaStatus.PROMOTED

    # Idempotent re-promotion
    success2, promoted2, msg2 = promote_idea_to_artifact(idea.idea_id, user_approved=True, db_path=isolated_db)
    assert success2 is True
    assert "already promoted" in msg2


def test_revision_immutability_and_lineage_traceability(isolated_db):
    """
    Mandate invariant: Hypotheses and ideas must NEVER be silently overwritten.
    Revisions must create child records while preserving parent records as REVISED.
    """
    # 1. Create parent tentative idea and promote it
    parent = create_tentative_idea(
        title="Spike-Timing Plasticity in RNNs",
        hypothesis="STDP increases sample efficiency in recurrent sequence models by 30%.",
        session_id="session-lineage-01",
        thinker_id="turing",
        db_path=isolated_db,
    )
    promote_idea_to_artifact(parent.idea_id, user_approved=True, db_path=isolated_db)

    # 2. Revise hypothesis based on Popperian falsification critique
    v1_hypothesis = parent.hypothesis
    rev_notes = "Refining hypothesis to specify continuous-time spiking networks and control for parameter budget."
    v2_hypothesis = "STDP constrained to equal parameter budgets improves sample efficiency only in continuous-time dynamics."

    success, child_v2, msg = revise_idea(
        idea_id=parent.idea_id,
        new_hypothesis=v2_hypothesis,
        revision_notes=rev_notes,
        thinker_id="popper",
        thinker_critique="Ensure control groups share identical active synapse counts.",
        db_path=isolated_db,
    )

    assert success is True
    assert child_v2.revision_version == 2
    assert child_v2.parent_idea_id == parent.idea_id
    assert child_v2.hypothesis == v2_hypothesis
    assert child_v2.status == IdeaStatus.PROMOTED

    # Parent must remain in DB with status=REVISED and original hypothesis intact
    parent_in_db = get_idea(parent.idea_id, db_path=isolated_db)
    assert parent_in_db.status == IdeaStatus.REVISED
    assert parent_in_db.hypothesis == v1_hypothesis

    # 3. Formulate third revision (v3)
    v3_hypothesis = "STDP in continuous-time recurrent networks reduces gradient variance across long temporal horizons."
    success, child_v3, _ = revise_idea(
        idea_id=child_v2.idea_id,
        new_hypothesis=v3_hypothesis,
        revision_notes="Shifting primary metric from sample efficiency to gradient variance stability.",
        db_path=isolated_db,
    )
    assert child_v3.revision_version == 3
    assert child_v3.parent_idea_id == child_v2.idea_id

    # 4. Verify complete lineage history
    history = get_idea_history(child_v3.idea_id, db_path=isolated_db)
    assert len(history) == 3
    assert history[0].revision_version == 1
    assert history[0].idea_id == parent.idea_id
    assert history[0].status == IdeaStatus.REVISED

    assert history[1].revision_version == 2
    assert history[1].idea_id == child_v2.idea_id
    assert history[1].status == IdeaStatus.REVISED

    assert history[2].revision_version == 3
    assert history[2].idea_id == child_v3.idea_id
    assert history[2].status == IdeaStatus.PROMOTED

    # History requested from root parent returns the exact same complete family
    parent_history = get_idea_history(parent.idea_id, db_path=isolated_db)
    assert len(parent_history) == 3
    assert [h.idea_id for h in parent_history] == [h.idea_id for h in history]


def test_brief_integration_blocks_tentative_idea(isolated_db):
    """
    Mandate invariant: Tentative ideas cannot bypass the promotion barrier to
    construct research briefs.
    """
    tentative = create_tentative_idea(
        title="Quantum Dot Sensitization",
        hypothesis="Colloidal quantum dots double photocurrent in perovskite cells.",
        db_path=isolated_db,
    )

    with pytest.raises(ValueError) as excinfo:
        prepare_research_brief(
            topic="Quantum Dot Sensitization",
            idea_id=tentative.idea_id,
            db_path=isolated_db,
        )
    assert "Promotion Barrier" in str(excinfo.value)
    assert "must explicitly promote" in str(excinfo.value)


def test_brief_integration_succeeds_for_promoted_idea(isolated_db):
    """
    Mandate invariant: Promoted ideas bind cleanly to ResearchBriefs, inheriting
    their refined hypothesis, thinker context, and updating mutual references.
    """
    idea = create_tentative_idea(
        title="Epistemic Dialectic Convergence",
        hypothesis="Multi-thinker dialectic decreases cognitive bias in automated literature review.",
        thinker_id="aristotle",
        unresolved_objections=["Does telos introduce teleological bias in mechanistic studies?"],
        session_id="session-brief-01",
        db_path=isolated_db,
    )
    promote_idea_to_artifact(idea.idea_id, user_approved=True, db_path=isolated_db)

    brief = prepare_research_brief(
        topic="Epistemic Dialectic Convergence",
        idea_id=idea.idea_id,
        session_id="session-brief-01",
        db_path=isolated_db,
    )

    assert brief.idea_id == idea.idea_id
    assert idea.hypothesis in brief.hypotheses
    assert brief.thinker_context is not None
    assert brief.thinker_context["thinker_id"] == "aristotle"
    assert any("teleological bias" in q for q in brief.unresolved_questions)

    # Check that idea in DB now records brief_id
    updated_idea = get_idea(idea.idea_id, db_path=isolated_db)
    assert updated_idea.brief_id == brief.brief_id

    # Check persistence in research_briefs table
    db_brief = get_research_brief(brief.brief_id, db_path=isolated_db)
    assert db_brief is not None
    assert db_brief.idea_id == idea.idea_id


def test_abandon_idea_prevents_revision_and_promotion(isolated_db):
    """
    Mandate invariant: Shelved/abandoned ideas cannot be revised or promoted.
    """
    idea = create_tentative_idea(
        title="Cold Fusion in Ambient Palladium",
        hypothesis="Electrolytic loading yields sustained excess heat.",
        db_path=isolated_db,
    )

    success, abandoned, msg = abandon_idea(
        idea.idea_id,
        reason="Initial exploratory replication showed no thermal anomaly.",
        db_path=isolated_db,
    )
    assert success is True
    assert abandoned.status == IdeaStatus.ABANDONED

    # Cannot promote
    p_success, _, p_msg = promote_idea_to_artifact(idea.idea_id, user_approved=True, db_path=isolated_db)
    assert p_success is False
    assert "abandoned" in p_msg

    # Cannot revise
    r_success, _, r_msg = revise_idea(
        idea.idea_id,
        new_hypothesis="New speculative hypothesis",
        db_path=isolated_db,
    )
    assert r_success is False
    assert "abandoned" in r_msg


def test_rest_api_idea_endpoints_end_to_end(isolated_db, monkeypatch):
    """
    Test REST endpoints in routes_ideas.py through FastAPI TestClient.
    """
    # Monkeypatch DEFAULT_DB_PATH to isolated_db
    import backend.memory.db as db_module
    import backend.conversation.idea as idea_module
    monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", isolated_db)
    monkeypatch.setattr(idea_module, "DEFAULT_DB_PATH", isolated_db)

    client = TestClient(app)

    # 1. Formulate tentative idea
    create_resp = client.post(
        "/api/ideas/tentative",
        json={
            "title": "Neuromorphic Memristor Crossbars",
            "hypothesis": "Memristive crossbars reduce energy consumption of matrix-vector multiplication by 100x.",
            "description": "Analog computing hardware for edge inference.",
            "session_id": "session-api-test",
            "thinker_id": "simon",
            "unresolved_objections": ["How does device-to-device variance affect drift?"],
        },
    )
    assert create_resp.status_code == 201
    c_data = create_resp.json()
    assert c_data["success"] is True
    idea_id = c_data["idea"]["idea_id"]
    assert c_data["idea"]["status"] == "TENTATIVE"

    # 2. Attempt promotion with approved=false
    p_fail_resp = client.post(f"/api/ideas/{idea_id}/promote", json={"approved": False})
    assert p_fail_resp.status_code == 400
    assert "Promotion Barrier" in p_fail_resp.json()["detail"]

    # 3. Successful promotion with approved=true
    p_ok_resp = client.post(f"/api/ideas/{idea_id}/promote", json={"approved": True})
    assert p_ok_resp.status_code == 200
    assert p_ok_resp.json()["idea"]["status"] == "PROMOTED"

    # 4. Revise idea
    rev_resp = client.post(
        f"/api/ideas/{idea_id}/revise",
        json={
            "new_hypothesis": "1T1R memristive crossbars with closed-loop programming compensate for device variance while retaining 80x energy savings.",
            "revision_notes": "Added 1T1R architecture and closed-loop compensation.",
            "thinker_id": "box",
        },
    )
    assert rev_resp.status_code == 201
    r_data = rev_resp.json()
    child_id = r_data["idea"]["idea_id"]
    assert r_data["idea"]["revision_version"] == 2
    assert r_data["idea"]["parent_idea_id"] == idea_id

    # 5. Fetch history
    hist_resp = client.get(f"/api/ideas/{child_id}/history")
    assert hist_resp.status_code == 200
    history = hist_resp.json()["history"]
    assert len(history) == 2
    assert history[0]["idea_id"] == idea_id
    assert history[0]["status"] == "REVISED"
    assert history[1]["idea_id"] == child_id
    assert history[1]["status"] == "PROMOTED"

    # 6. List ideas
    list_resp = client.get("/api/ideas?session_id=session-api-test")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["ideas"]) >= 2
