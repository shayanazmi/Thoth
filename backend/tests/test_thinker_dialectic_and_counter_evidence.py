import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from backend.memory.db import init_db, get_connection, save_brief_db, get_brief_db
from backend.conversation.idea import (
    create_tentative_idea,
    promote_idea_to_artifact,
    revise_idea,
    get_idea,
    get_idea_history,
)
from backend.conversation.brief import (
    prepare_research_brief,
    get_research_brief,
    update_research_brief,
    ResearchBrief,
)
from backend.intellectual_rigour.counter_evidence import (
    generate_counter_evidence_plan,
    generate_hypothesis_revision_proposal,
    FRAMEWORK_COUNTER_TEMPLATES,
    CounterEvidencePlan,
    HypothesisRevisionProposal,
)
from backend.scholarly import SourceCandidate
from backend.pipeline import search_node, ResearchState
from backend.orchestrator import create_initial_state
from backend.main import app


@pytest.fixture
def isolated_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_counter_evidence.db")
    init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_framework_specific_counter_evidence_generation():
    """
    Verify each of the 10 thinker frameworks generates distinct, epistemically
    aligned counter-evidence queries and falsification criteria.
    """
    hyp = "Self-attention mechanisms linearly scale cognitive reasoning in large models."
    topic = "Attention Scaling in LLMs"

    # 1. Karl Popper — Falsification & Negative Results
    popper_plan = generate_counter_evidence_plan(hyp, thinker_id="popper", topic=topic)
    assert any("falsification" in q.query.lower() or "negative result" in q.query.lower() for q in popper_plan.queries)
    assert any("null effect" in crit.lower() or "falsif" in crit.lower() for crit in popper_plan.falsification_criteria)
    assert popper_plan.target_bias == "Confirmation bias & verificationism"

    # 2. David Hume — Confounding & Spurious Correlation
    hume_plan = generate_counter_evidence_plan(hyp, thinker_id="hume", topic=topic)
    assert any("confounding" in q.query.lower() or "spurious" in q.query.lower() for q in hume_plan.queries)
    assert any("alternative explanation" in crit.lower() or "confound" in crit.lower() for crit in hume_plan.falsification_criteria)

    # 3. George Box — Model Misspecification & Sensitivity
    box_plan = generate_counter_evidence_plan(hyp, thinker_id="box", topic=topic)
    assert any("misspecification" in q.query.lower() or "sensitivity" in q.query.lower() for q in box_plan.queries)
    assert any("parameter sensitivity" in crit.lower() or "breakdown" in crit.lower() for crit in box_plan.falsification_criteria)

    # 4. Herbert Simon — Computational Intractability & Bounded Rationality
    simon_plan = generate_counter_evidence_plan(hyp, thinker_id="simon", topic=topic)
    assert any("intractability" in q.query.lower() or "search cost" in q.query.lower() for q in simon_plan.queries)
    assert any("polynomial" in crit.lower() or "tractab" in crit.lower() or "budget" in crit.lower() for crit in simon_plan.falsification_criteria)

    # 5. Thomas Kuhn — Anomalies & Paradigm Boundaries
    kuhn_plan = generate_counter_evidence_plan(hyp, thinker_id="kuhn", topic=topic)
    assert any("anomal" in q.query.lower() or "paradigm" in q.query.lower() for q in kuhn_plan.queries)

    # 6. Francis Bacon — Idols & Cognitive Biases
    bacon_plan = generate_counter_evidence_plan(hyp, thinker_id="bacon", topic=topic)
    assert any("sampling bias" in q.query.lower() or "systematic error" in q.query.lower() for q in bacon_plan.queries)

    # 7. Rene Descartes — Foundational Skepticism
    descartes_plan = generate_counter_evidence_plan(hyp, thinker_id="descartes", topic=topic)
    assert any("unstated assumption" in q.query.lower() or "boundary condition" in q.query.lower() for q in descartes_plan.queries)

    # 8. Aristotle — Teleological & Essentialist Limits
    aristotle_plan = generate_counter_evidence_plan(hyp, thinker_id="aristotle", topic=topic)
    assert any("efficient cause" in q.query.lower() or "counter-examples" in q.query.lower() for q in aristotle_plan.queries)

    # 9. Charles Darwin — Selection Pressures & Fitness Tradeoffs
    darwin_plan = generate_counter_evidence_plan(hyp, thinker_id="darwin", topic=topic)
    assert any("maladaptive" in q.query.lower() or "evolutionary bottleneck" in q.query.lower() for q in darwin_plan.queries)

    # 10. Alan Turing — Operational Equivalence & Behavioral Breakdown
    turing_plan = generate_counter_evidence_plan(hyp, thinker_id="turing", topic=topic)
    assert any("adversarial perturbation" in q.query.lower() or "behavioral failure" in q.query.lower() for q in turing_plan.queries)


def test_objection_translation_into_targeted_queries():
    """
    Verify thinker dialectic objections are translated into specific scholarly queries.
    """
    hyp = "Transformer models generalize out-of-distribution without explicit inductive bias."
    objections = [
        "Memory consumption grows quadratically leading to severe latency degradation in production environments.",
        "Synthesized data leads to model collapse due to loss of distribution tails."
    ]

    plan = generate_counter_evidence_plan(
        hypothesis=hyp,
        thinker_id="simon",
        objections=objections,
        topic="Transformer Scalability"
    )

    queries_text = [q.query for q in plan.queries]
    # Check that objection-specific queries were constructed
    assert any("memory consumption" in q.lower() or "latency degradation" in q.lower() for q in queries_text)
    assert any("model collapse" in q.lower() or "distribution tails" in q.lower() for q in queries_text)

    # Check falsification criteria are extracted
    assert any("memory consumption" in c.lower() or "collapse" in c.lower() for c in plan.falsification_criteria)


def test_prepare_brief_auto_generates_counter_evidence_plan(isolated_db):
    """
    Verify prepare_research_brief automatically produces counter-evidence queries
    and falsification criteria when thinker objections exist in mandate.
    """
    mandate = {
        "title": "Biological Metaphors in Artificial Neural Networks",
        "primary_question": "Does dynamic dendritic gating prevent catastrophic forgetting?",
        "topic": "Dendritic Gating in Neural Networks",
        "hypotheses": ["Dendritic branch compartmentation isolates task weights to mitigate interference."],
        "thinker_context": {
            "thinker_id": "popper",
            "critique": "The hypothesis risks being unfalsifiable unless baseline backpropagation models are evaluated.",
            "unresolved_objections": [
                "Replication failure in high-dimensional continuous control benchmarks."
            ]
        }
    }

    brief = prepare_research_brief(mandate, session_id="sess-dialectic-01", db_path=isolated_db)
    assert brief is not None
    assert len(brief.counter_evidence_queries) >= 2
    assert len(brief.falsification_criteria) >= 2

    # Check that the popper framework was applied
    assert any("falsification" in q["query"].lower() or "negative result" in q["query"].lower() for q in brief.counter_evidence_queries)
    assert any("replication failure" in q["query"].lower() for q in brief.counter_evidence_queries)


def test_brief_counter_evidence_sqlite_persistence(isolated_db):
    """
    Verify counter_evidence_queries and falsification_criteria persist across SQLite sessions.
    """
    brief_data = {
        "title": "Quantum Annealing for Combinatorial Optimization",
        "primary_question": "Can D-Wave quantum annealers surpass classical simulated annealing on MAX-CUT?",
        "topic": "Quantum vs Classical Annealing",
        "hypotheses": ["Quantum tunneling provides polynomial speedup on rugged energy landscapes."],
        "counter_evidence_queries": [
            {
                "query": "quantum annealing simulated annealing benchmark comparison MAX-CUT negative result",
                "framework": "popper",
                "purpose": "Identify experimental comparisons showing no speedup",
                "target_bias": "Confirmation bias"
            }
        ],
        "falsification_criteria": [
            "Classical simulated annealing with optimized tensor networks achieves lower ground-state energy.",
            "Tunneling speedup disappears in non-random benchmark graphs."
        ]
    }

    brief = prepare_research_brief(brief_data, session_id="sess-q-01", db_path=isolated_db)
    brief_id = brief.brief_id

    # Reload from database in a fresh read
    loaded = get_research_brief(brief_id, db_path=isolated_db)
    assert loaded is not None
    assert len(loaded.counter_evidence_queries) == 1
    assert "MAX-CUT negative result" in loaded.counter_evidence_queries[0]["query"]
    assert len(loaded.falsification_criteria) == 2
    assert "Classical simulated annealing" in loaded.falsification_criteria[0]


def test_hypothesis_revision_proposal_generation_preserves_agency(isolated_db):
    """
    Crucial product invariant: Counter-evidence challenges the hypothesis and
    synthesizes a revision proposal, but NEVER silently mutates the user's idea in DB.
    """
    # 1. Create and promote an idea
    idea = create_tentative_idea(
        title="Emergent Reasoning in Sub-10B Models",
        hypothesis="Sub-10B language models exhibit genuine step-by-step reasoning on ARC benchmarks.",
        session_id="sess-prop-01",
        thinker_id="hume",
        unresolved_objections=["The apparent reasoning is memorization of training corpus subgraphs."],
        db_path=isolated_db,
    )
    ok, promoted, _ = promote_idea_to_artifact(idea.idea_id, user_approved=True, db_path=isolated_db)
    assert ok is True

    # 2. Simulate counter-evidence findings extracted from literature
    counter_findings = [
        {
            "claim": "85% of ARC benchmark solution paths in 7B models are identical to pretraining data n-grams.",
            "source_id": "src-memorization-study-2025",
            "finding": "Apparent multi-step reasoning is memorized template matching rather than generalized inference."
        }
    ]

    proposal = generate_hypothesis_revision_proposal(
        idea_id=promoted.idea_id,
        current_hypothesis=promoted.hypothesis,
        counter_evidence_findings=counter_findings,
        thinker_id="hume",
        objection="The apparent reasoning is memorization of training corpus subgraphs."
    )

    assert isinstance(proposal, HypothesisRevisionProposal)
    assert proposal.idea_id == promoted.idea_id
    assert len(proposal.candidate_revisions) >= 3
    assert len(proposal.boundary_conditions) >= 1
    assert proposal.counter_evidence_summary != ""

    # 3. Agency invariant: the database record MUST still have the original hypothesis!
    unchanged_idea = get_idea(promoted.idea_id, db_path=isolated_db)
    assert unchanged_idea.hypothesis == "Sub-10B language models exhibit genuine step-by-step reasoning on ARC benchmarks."
    assert unchanged_idea.version == 1

    # 4. Explicit user approval creates child revision with lineage
    selected_revision = proposal.candidate_revisions[0]["revised_hypothesis"]
    rev_ok, child_idea, _ = revise_idea(
        idea_id=promoted.idea_id,
        new_hypothesis=selected_revision,
        revision_notes="Refined hypothesis following Humean critique and memorization counter-evidence.",
        thinker_id="hume",
        db_path=isolated_db,
    )
    assert rev_ok is True
    assert child_idea.version == 2
    assert child_idea.parent_idea_id == promoted.idea_id

    # Verify history maintains immutable chain
    history = get_idea_history(child_idea.idea_id, db_path=isolated_db)
    assert len(history) == 2
    assert history[0].hypothesis == promoted.hypothesis
    assert history[1].hypothesis == selected_revision


@pytest.mark.asyncio
async def test_search_node_queries_counter_evidence_and_tags_sources():
    """
    Verify search_node extracts counter-evidence queries from state/brief,
    queries them, and tags the candidate sources with relation='counter_evidence'.
    """
    main_cand = SourceCandidate(
        title="Proving Scaling Laws in Modern Neural Architectures",
        url="https://arxiv.org/abs/2401.00001",
        authors=["Alice Researcher"],
        abstract="We show robust power-law scaling across diverse tasks.",
        source_api="arxiv"
    )

    ce_cand = SourceCandidate(
        title="Limits of Power-Law Scaling: Failure Modes and Saturation",
        url="https://arxiv.org/abs/2401.00002",
        authors=["Bob Skeptic"],
        abstract="We demonstrate that scaling laws fail under distribution shift.",
        source_api="arxiv"
    )

    state: ResearchState = {
        "topic": "Scaling Laws in Deep Learning",
        "role": "academic researcher",
        "tone": "objective",
        "language": "English",
        "scrape_top_n": 5,
        "min_score": 6.5,
        "max_retries": 2,
        "attempt": 0,
        "search_results": "",
        "scraped_content": "",
        "report": "",
        "feedback": "",
        "verifier_feedback": "",
        "score": 0.0,
        "follow_up_questions": [],
        "mindmap": {"nodes": [], "edges": []},
        "cumulative_sources": [],
        "conversation_summary": "",
        "chat_turns": [],
        "integrity_status": "PENDING",
        "integrity_result": {},
        "is_verified": False,
        "brief": {},
        "counter_evidence_queries": [
            {
                "query": "scaling laws saturation failure modes distribution shift",
                "framework": "popper",
                "purpose": "Find empirical counter-examples"
            }
        ],
        "falsification_criteria": []
    }

    # Mock search_scholarly_sources to return main_cand for main topic, ce_cand for counter query
    async def mock_search(query, max_results=15, min_scholarly_results=5, **kwargs):
        if "saturation" in query or "failure" in query:
            return [ce_cand]
        return [main_cand]

    with patch("backend.pipeline.search_scholarly_sources", side_effect=mock_search):
        result = search_node(state)

    cum_sources = result["cumulative_sources"]
    assert len(cum_sources) == 2

    # Verify main source relation is None/standard, but counter source has relation='counter_evidence'
    main_src = next(s for s in cum_sources if s["url"] == "https://arxiv.org/abs/2401.00001")
    ce_src = next(s for s in cum_sources if s["url"] == "https://arxiv.org/abs/2401.00002")

    assert ce_src["relation"] == "counter_evidence"
    assert main_src["relation"] != "counter_evidence"


def test_rest_api_counter_evidence_plan_and_proposal(isolated_db):
    """
    Test the FastAPI REST endpoints for counter-evidence planning and revision proposals.
    """
    client = TestClient(app)

    with patch("backend.api.routes_ideas.get_idea") as mock_get_idea:
        # 1. Test 404 on unknown idea
        mock_get_idea.return_value = None
        resp = client.post("/api/ideas/unknown-idea-id/counter-evidence-plan", json={})
        assert resp.status_code == 404

        # 2. Test successful counter-evidence plan endpoint
        from backend.conversation.idea import ResearchIdea, IdeaStatus
        mock_idea = ResearchIdea(
            idea_id="idea-test-123",
            title="Reinforcement Learning with Verifiable Rewards",
            hypothesis="RL with programmatic verifiers eliminates specification gaming in mathematical theorem proving.",
            status=IdeaStatus.PROMOTED,
            thinker_id="box",
            unresolved_objections=["Verifiers themselves have boundary vulnerabilities and false positives."]
        )
        mock_get_idea.return_value = mock_idea

        resp = client.post(
            "/api/ideas/idea-test-123/counter-evidence-plan",
            json={"topic": "Verifiable RL"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "plan" in data
        assert len(data["plan"]["queries"]) >= 2
        assert data["plan"]["thinker_id"] == "box"

        # 3. Test successful hypothesis revision proposal endpoint
        resp_prop = client.post(
            "/api/ideas/idea-test-123/propose-revision",
            json={
                "counter_evidence_findings": [
                    {
                        "claim": "Programmatic verifiers can be bypassed by empty proof tautologies.",
                        "source": "arXiv:2402.99999"
                    }
                ],
                "objection": "Verifiers have false positive boundary cases."
            }
        )
        assert resp_prop.status_code == 200
        prop_data = resp_prop.json()
        assert prop_data["success"] is True
        assert "proposal" in prop_data
        assert len(prop_data["proposal"]["candidate_revisions"]) >= 3
        assert "explicit user approval" in prop_data["message"]
