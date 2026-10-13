import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.main import app
from backend.intellectual_rigour.matcher import match_ideation_archetype, ARCHETYPE_DEFINITIONS
from backend.intellectual_rigour.sparring import spar_with_thinker, evaluate_ideation_convergence, EscalationProposal
from backend.conversation.escalation import evaluate_brainstorm_escalation, EscalationState

@pytest.fixture
def client():
    return TestClient(app)

class TestEpistemicMatcher:
    def test_all_10_thinkers_defined(self):
        expected_thinkers = [
            "aristotle", "descartes", "bacon", "hume", "darwin",
            "popper", "kuhn", "box", "turing", "simon"
        ]
        for tid in expected_thinkers:
            assert tid in ARCHETYPE_DEFINITIONS
            data = ARCHETYPE_DEFINITIONS[tid]
            assert "name" in data
            assert "tradition" in data
            assert "archetype" in data
            assert "description" in data
            assert "default_opening" in data

    def test_heuristic_pattern_matching_aristotle(self):
        res = match_ideation_archetype("How do we define the category boundary of this concept?")
        assert res.thinker_id == "aristotle"
        assert res.archetype == "Categorical Architect"

    def test_heuristic_pattern_matching_descartes(self):
        res = match_ideation_archetype("Let us break this down to its first principles and core assumptions.")
        assert res.thinker_id == "descartes"
        assert res.archetype == "Foundational Reductionist"

    def test_heuristic_pattern_matching_bacon(self):
        res = match_ideation_archetype("We must avoid confirmation bias by examining negative instances and empirical evidence.")
        assert res.thinker_id == "bacon"
        assert res.archetype == "Eliminative Empiricist"

    def test_heuristic_pattern_matching_hume(self):
        res = match_ideation_archetype("Can this observed correlation be explained by an unmeasured confounder?")
        assert res.thinker_id == "hume"
        assert res.archetype == "Causal Skeptic"

    def test_heuristic_pattern_matching_darwin(self):
        res = match_ideation_archetype("A multi-agent swarm navigating a dynamic fitness landscape.")
        assert res.thinker_id == "darwin"
        assert res.archetype == "Evolutionary Selectionist"

    def test_heuristic_pattern_matching_popper(self):
        res = match_ideation_archetype("How can we design a severe test to falsify this hypothesis?")
        assert res.thinker_id == "popper"
        assert res.archetype == "Falsificationist Warrior"

    def test_heuristic_pattern_matching_kuhn(self):
        res = match_ideation_archetype("A paradigm shift prompted by accumulating anomalies in normal science.")
        assert res.thinker_id == "kuhn"
        assert res.archetype == "Paradigmatic Strategist"

    def test_heuristic_pattern_matching_box(self):
        res = match_ideation_archetype("A parsimonious model balancing complexity with residual diagnostics.")
        assert res.thinker_id == "box"
        assert res.archetype == "Pragmatic Modeling Iterativist"

    def test_heuristic_pattern_matching_turing(self):
        res = match_ideation_archetype("A discrete state machine with formal halting guarantees.")
        assert res.thinker_id == "turing"
        assert res.archetype == "Computational Operationalist"

    def test_heuristic_pattern_matching_simon(self):
        res = match_ideation_archetype("Bounded rationality with heuristic search and satisficing stopping criteria.")
        assert res.thinker_id == "simon"
        assert res.archetype == "Bounded Rationalist"

class TestSparringAndEscalation:
    def test_spar_with_thinker_mock(self):
        mock_response = MagicMock()
        mock_response.content = "What conceivable empirical observation would destroy your premise?"
        with patch("backend.intellectual_rigour.sparring.llm.invoke", return_value=mock_response):
            res = spar_with_thinker(
                thinker_id="popper",
                user_message="My system is 100% correct.",
                chat_turns=[]
            )
            assert res.thinker_id == "popper"
            assert res.thinker_name == "Karl Popper"
            assert "empirical observation" in res.reply
            assert res.turn_count == 1

    def test_evaluate_ideation_convergence_ready(self):
        mock_json_response = MagicMock()
        mock_json_response.content = '''{
            "is_ready_for_research": true,
            "readiness_score": 0.88,
            "crystallized_topic": "Attention Map Correlation Anomalies in Transformers",
            "testable_hypothesis": "Cross-layer attention patterns produce spurious causal artifacts under OOD shifts",
            "identified_constraints": ["Zero-shot classification", "Vision transformers"],
            "falsification_or_test_criteria": "Attention intervention ablation benchmarks",
            "action_pill_label": "🚀 Launch Deep Research with Karl Popper",
            "escalation_reason": "Specific testable hypothesis with concrete ablation falsification criteria."
        }'''
        turns = [
            {"user": "Attention might have bugs.", "assistant": "Define the bug."},
            {"user": "Under OOD shift, cross-layer correlations are spurious.", "assistant": "How will you test this?"}
        ]
        with patch("backend.intellectual_rigour.sparring.llm.invoke", return_value=mock_json_response):
            proposal = evaluate_ideation_convergence("popper", turns)
            assert proposal is not None
            assert proposal.is_ready_for_research is True
            assert proposal.readiness_score == 0.88
            assert proposal.crystallized_topic == "Attention Map Correlation Anomalies in Transformers"

    def test_evaluate_brainstorm_escalation_bridge(self):
        mock_json_response = MagicMock()
        mock_json_response.content = '''{
            "is_ready_for_research": true,
            "readiness_score": 0.92,
            "crystallized_topic": "Quantum Surface Code Decoder Latency Bounds",
            "testable_hypothesis": "Lookup table decoders scale exponentially past distance 7",
            "identified_constraints": ["Surface code distance <= 7", "Real-time FPGA decoding"],
            "falsification_or_test_criteria": "Microsecond FPGA simulation benchmarks",
            "action_pill_label": "🚀 Launch Deep Research with Alan Turing",
            "escalation_reason": "Formal operational bounds articulated."
        }'''
        turns = [
            {"user": "Quantum decoding speed.", "assistant": "Specify state machine."},
            {"user": "FPGA lookup tables scale exponentially.", "assistant": "What is the halting proof?"}
        ]
        with patch("backend.intellectual_rigour.sparring.llm.invoke", return_value=mock_json_response):
            res = evaluate_brainstorm_escalation(
                query="Look into this deeply",
                chat_turns=turns,
                thinker_id="turing"
            )
            assert res["state"] == EscalationState.RESEARCH_READY
            assert res["confidence"] == 0.92
            assert res["prompt_user"] is True
            assert "🚀 Launch Deep Research with Alan Turing" in res["action_pill_label"]

class TestWebEndpoints:
    def test_list_thinkers_endpoint(self, client):
        resp = client.get("/api/brainstorm/thinkers")
        assert resp.status_code == 200
        data = resp.json()
        assert "thinkers" in data
        assert len(data["thinkers"]) == 10
        ids = [t["id"] for t in data["thinkers"]]
        assert "popper" in ids
        assert "aristotle" in ids

    def test_match_thinker_endpoint(self, client):
        resp = client.post("/api/brainstorm/match", json={
            "query": "Is there an unmeasured confounder causing this correlation?",
            "chat_turns": []
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["thinker_id"] == "hume"
        assert data["archetype"] == "Causal Skeptic"

    def test_brainstorm_chat_endpoint(self, client):
        mock_reply = MagicMock()
        mock_reply.content = "What is the counter-instance that refutes this?"
        with patch("backend.intellectual_rigour.sparring.llm.invoke", return_value=mock_reply):
            resp = client.post("/api/brainstorm/chat", json={
                "thinker_id": "popper",
                "message": "I believe all swans are white.",
                "chat_turns": []
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["thinker_id"] == "popper"
            assert data["thinker_name"] == "Karl Popper"
            assert "counter-instance" in data["reply"]
