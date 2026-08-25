import unittest
import pydantic
from pydantic import ValidationError
from unittest.mock import patch, MagicMock

from backend.agents import (
    VerificationResult,
    FactVerificationReport,
    CriticScore,
    safe_extract_json,
    strip_chain_of_thought
)
from backend.scholarly import SourceCandidate
from backend.memory.vault import Note
from backend.pipeline import (
    ResearchState,
    ResearchMindMap,
    MindMapNode,
    MindMapEdge,
    critic_node,
    verifier_node,
    mindmap_node,
    follow_up_node,
    route_followup_intent
)
from backend.orchestrator import create_initial_state


class TestPydanticSchemas(unittest.TestCase):
    """Validation tests for all Pydantic models in backend/agents.py."""

    # -------------------------------------------------------------------------
    # 1. VerificationResult & FactVerificationReport
    # -------------------------------------------------------------------------

    def test_verification_result_valid_construction(self):
        res = VerificationResult(
            claim="Superconducting qubits require dilution refrigerators.",
            is_valid=True,
            reason_if_failed="",
            supporting_source_id="src-superconducting_qubits"
        )
        self.assertEqual(res.claim, "Superconducting qubits require dilution refrigerators.")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.supporting_source_id, "src-superconducting_qubits")
        self.assertEqual(res.reason_if_failed, "")

    def test_verification_result_missing_required_field_raises(self):
        # Missing 'claim'
        with self.assertRaises(ValidationError):
            VerificationResult(is_valid=True)

        # Missing 'is_valid'
        with self.assertRaises(ValidationError):
            VerificationResult(claim="Quantum claim")

    def test_verification_result_invalid_types_raise(self):
        # Unsupported complex type for boolean is_valid
        with self.assertRaises(ValidationError):
            VerificationResult(claim="Claim", is_valid=[1, 2, 3])

    def test_fact_verification_report_valid_and_invalid(self):
        valid_res = VerificationResult(
            claim="Cat qubits have biased noise.",
            is_valid=True,
            supporting_source_id="src-cat_qubits"
        )
        report = FactVerificationReport(results=[valid_res])
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].claim, "Cat qubits have biased noise.")

        # Missing results field
        with self.assertRaises(ValidationError):
            FactVerificationReport()

        # Invalid item inside results list
        with self.assertRaises(ValidationError):
            FactVerificationReport(results=[{"invalid_key": "bad"}])

    # -------------------------------------------------------------------------
    # 2. CriticScore (including 0.0 - 10.0 range constraints)
    # -------------------------------------------------------------------------

    def test_critic_score_valid_construction(self):
        score = CriticScore(
            faithfulness=8.5,
            relevance=9.0,
            completeness=8.0,
            evidence_quality=8.5,
            clarity_and_coherence=9.0,
            overall_score=8.6,
            strengths=["Clear methodology", "Strong citations"],
            areas_to_improve=["Add real-world benchmarks"],
            verdict="Comprehensive and rigorous research report.",
            reasoning="All claims are backed by peer-reviewed sources."
        )
        self.assertEqual(score.overall_score, 8.6)
        self.assertEqual(len(score.strengths), 2)
        self.assertEqual(len(score.areas_to_improve), 1)

    def test_critic_score_missing_required_fields_raises(self):
        # Missing reasoning and verdict
        with self.assertRaises(ValidationError):
            CriticScore(
                faithfulness=8.0,
                relevance=8.0,
                completeness=8.0,
                evidence_quality=8.0,
                clarity_and_coherence=8.0,
                overall_score=8.0,
                strengths=["Good"],
                areas_to_improve=[]
            )

    def test_critic_score_out_of_bounds_raises_validation_error(self):
        """Confirms Field(ge=0.0, le=10.0) constraint prevents out-of-range scores."""
        valid_kwargs = {
            "faithfulness": 8.0,
            "relevance": 8.0,
            "completeness": 8.0,
            "evidence_quality": 8.0,
            "clarity_and_coherence": 8.0,
            "overall_score": 8.0,
            "strengths": ["Clear"],
            "areas_to_improve": [],
            "verdict": "Good",
            "reasoning": "Solid"
        }

        # Test upper bound violation (> 10.0) for each dimensional field and overall_score
        score_fields = [
            "faithfulness",
            "relevance",
            "completeness",
            "evidence_quality",
            "clarity_and_coherence",
            "overall_score"
        ]

        for field_name in score_fields:
            bad_high = dict(valid_kwargs)
            bad_high[field_name] = 10.1
            with self.assertRaises(ValidationError, msg=f"Score > 10.0 for {field_name} did not raise ValidationError"):
                CriticScore(**bad_high)

            bad_low = dict(valid_kwargs)
            bad_low[field_name] = -0.5
            with self.assertRaises(ValidationError, msg=f"Score < 0.0 for {field_name} did not raise ValidationError"):
                CriticScore(**bad_low)


class TestDataclassSchemas(unittest.TestCase):
    """Validation tests for dataclasses in backend/scholarly.py and backend/memory/vault.py."""

    def test_source_candidate_valid_construction(self):
        candidate = SourceCandidate(
            title="A Survey of Quantum Error Correction",
            authors=["Dr. Alice", "Dr. Bob"],
            abstract="Quantum error correction protects quantum information from noise.",
            url="https://arxiv.org/abs/2401.99999",
            doi="10.1000/qec123",
            citation_count=42,
            published_date="2024-01-15",
            source_api="arxiv",
            arxiv_id="2401.99999"
        )
        self.assertEqual(candidate.title, "A Survey of Quantum Error Correction")
        self.assertEqual(candidate.citation_count, 42)

        # Verify to_dict serialization
        d = candidate.to_dict()
        self.assertEqual(d["title"], candidate.title)
        self.assertEqual(d["source_api"], "arxiv")

        # Verify snippet generation
        snippet = candidate.to_formatted_snippet()
        self.assertIn("A Survey of Quantum Error Correction", snippet)
        self.assertIn("10.1000/qec123", snippet)

    def test_source_candidate_missing_required_positional_args_raises(self):
        # Missing all required positional fields
        with self.assertRaises(TypeError):
            SourceCandidate()

    def test_note_valid_construction(self):
        note = Note(
            note_id="note_topological_qubits",
            note_type="concept",
            content="Topological qubits utilize Majorana zero modes for hardware-level fault tolerance.",
            frontmatter={"title": "Topological Qubits", "tags": ["quantum", "hardware"]},
            file_path="/path/to/note.md"
        )
        self.assertEqual(note.note_id, "note_topological_qubits")
        self.assertEqual(note.note_type, "concept")
        self.assertEqual(note.frontmatter["title"], "Topological Qubits")

        # Verify to_dict output
        d = note.to_dict()
        self.assertEqual(d["note_id"], "note_topological_qubits")
        self.assertEqual(d["type"], "concept")
        self.assertEqual(d["content"], note.content)

    def test_note_missing_required_positional_args_raises(self):
        # Missing required positional fields (note_id, note_type, content)
        with self.assertRaises(TypeError):
            Note()


class TestTypedDictsAndConstructors(unittest.TestCase):
    """Validation tests for TypedDict shapes and their producing factory functions."""

    def test_research_state_created_with_all_required_keys(self):
        """
        Confirms create_initial_state populates every key declared in ResearchState TypedDict.
        """
        state = create_initial_state(
            topic="Fault-Tolerant Quantum Computing",
            role="senior scientist",
            tone="academic",
            language="English",
            scrape_top_n=3,
            min_score=7.0,
            max_retries=2
        )

        required_keys = [
            "topic",
            "role",
            "tone",
            "language",
            "scrape_top_n",
            "min_score",
            "max_retries",
            "attempt",
            "search_results",
            "scraped_content",
            "report",
            "feedback",
            "verifier_feedback",
            "score",
            "follow_up_questions",
            "mindmap",
            "cumulative_sources",
            "conversation_summary",
            "chat_turns"
        ]

        for key in required_keys:
            self.assertIn(key, state, f"Key '{key}' was missing from constructed ResearchState dictionary")
            self.assertIsNotNone(state[key], f"Key '{key}' was None in constructed ResearchState dictionary")

        # Confirm nested mindmap TypedDict structure in state
        self.assertIn("nodes", state["mindmap"])
        self.assertIn("edges", state["mindmap"])
        self.assertIsInstance(state["mindmap"]["nodes"], list)
        self.assertIsInstance(state["mindmap"]["edges"], list)

    def test_mindmap_node_construction_and_structure(self):
        """
        Tests that mindmap_node produces valid MindMapNode and MindMapEdge structures.
        """
        sample_state = {
            "topic": "Neutral Atom Qubits",
            "report": "# Neutral Atom Qubits\nRydberg blockade enables two-qubit entangling gates.",
            "cumulative_sources": [{"url": "https://arxiv.org/abs/2401.12345"}]
        }

        # Mock mindmap extractor chain
        mock_mm_chain = MagicMock()
        mock_mm_chain.invoke.return_value = '{"nodes": [{"id": "root", "label": "Neutral Atoms", "type": "topic", "details": "Core topic", "group": "topic"}, {"id": "sub1", "label": "Rydberg States", "type": "subtopic", "details": "Interactions", "group": "subtopic"}], "edges": [{"from": "root", "to": "sub1", "label": "enables"}]}'

        with patch("backend.pipeline.mindmap_extractor_chain", mock_mm_chain):
            res = mindmap_node(sample_state)

        self.assertIn("mindmap", res)
        mm = res["mindmap"]
        self.assertIn("nodes", mm)
        self.assertIn("edges", mm)
        self.assertEqual(len(mm["nodes"]), 2)
        self.assertEqual(len(mm["edges"]), 1)

        # Validate node fields
        node = mm["nodes"][0]
        self.assertEqual(node["id"], "root")
        self.assertEqual(node["label"], "Neutral Atoms")
        self.assertEqual(node["type"], "topic")

        # Validate edge fields
        edge = mm["edges"][0]
        self.assertEqual(edge["from"], "root")
        self.assertEqual(edge["to"], "sub1")
        self.assertEqual(edge["label"], "enables")


class TestSchemaConsumersMalformedLLMOutputs(unittest.TestCase):
    """
    Tests error handling when raw LLM output is malformed, truncated, has thinking tokens,
    or contains extra prose across all schema consumer nodes.
    """

    def test_critic_node_handles_thinking_tokens_and_markdown_fences(self):
        """
        Confirms critic_node extracts CriticScore cleanly from <think>...</think> and markdown fences.
        """
        llm_output_with_thinking = """
        <think>
        I will evaluate this report against the 5 criteria:
        Faithfulness is high because sources are cited.
        Overall score should be 8.8.
        </think>
        ```json
        {
          "faithfulness": 9.0,
          "relevance": 9.0,
          "completeness": 8.5,
          "evidence_quality": 8.5,
          "clarity_and_coherence": 9.0,
          "overall_score": 8.8,
          "strengths": ["Strong evidence base", "Clear section layout"],
          "areas_to_improve": ["Discuss decoherence rates"],
          "verdict": "High quality research report.",
          "reasoning": "Grounded synthesis across all major subfields."
        }
        ```
        """
        mock_critic = MagicMock()
        mock_critic.invoke.return_value = llm_output_with_thinking

        with patch("backend.pipeline.critic_chain", mock_critic):
            update = critic_node({"topic": "Quantum Computing", "report": "Report content..."})

        self.assertEqual(update["score"], 8.8)
        self.assertIn("Faithfulness", update["feedback"])

    def test_critic_node_raises_informative_error_on_unparseable_output(self):
        """Confirms critic_node raises ValueError when output cannot be salvaged."""
        mock_critic = MagicMock()
        mock_critic.invoke.return_value = "I cannot format this as JSON at all."

        with patch("backend.pipeline.critic_chain", mock_critic):
            with self.assertRaises(ValueError):
                critic_node({"topic": "Quantum Computing", "report": "Report content..."})

    def test_verifier_node_handles_malformed_and_unsupported_text(self):
        """
        Confirms verifier_node handles unparseable JSON by checking textual contradiction signals.
        """
        mock_verifier = MagicMock()

        # Test Case 1: Garbled JSON with contradiction keyword in text
        mock_verifier.invoke.return_value = "Error parsing: Claim 1 contradicts the provided arXiv paper."
        with patch("backend.pipeline.verifier_chain", mock_verifier):
            res1 = verifier_node({"cumulative_sources": [], "report": "Report text"})
            self.assertIn("contradicts", res1["verifier_feedback"])

        # Test Case 2: Clean structured JSON
        clean_json = '{"results": [{"claim": "Qubits exist", "is_valid": true, "supporting_source_id": "src-paper", "reason_if_failed": ""}]}'
        mock_verifier.invoke.return_value = clean_json
        with patch("backend.pipeline.verifier_chain", mock_verifier):
            res2 = verifier_node({"cumulative_sources": [], "report": "Report text"})
            self.assertEqual(res2["verifier_feedback"], "")
            self.assertEqual(len(res2["verification_results"]), 1)

    def test_mindmap_node_fallback_on_garbled_json(self):
        """
        Confirms mindmap_node gracefully falls back to default graph topology on malformed output.
        """
        mock_mm = MagicMock()
        mock_mm.invoke.return_value = "Invalid JSON non-graph response"

        with patch("backend.pipeline.mindmap_extractor_chain", mock_mm):
            res = mindmap_node({"topic": "Quantum Teleportation", "report": "Content", "cumulative_sources": []})

        self.assertIn("mindmap", res)
        self.assertEqual(len(res["mindmap"]["nodes"]), 4)
        self.assertEqual(res["mindmap"]["nodes"][0]["id"], "root")
        self.assertEqual(res["mindmap"]["nodes"][0]["label"], "Quantum Teleportation")

    def test_follow_up_node_fallback_on_garbled_json(self):
        """
        Confirms follow_up_node produces default suggested questions when JSON parse fails.
        """
        mock_fu = MagicMock()
        mock_fu.invoke.return_value = "Not a JSON array"

        with patch("backend.pipeline.follow_up_chain", mock_fu):
            res = follow_up_node({"topic": "Quantum Annealing", "report": "Content"})

        self.assertIn("follow_up_questions", res)
        self.assertGreaterEqual(len(res["follow_up_questions"]), 2)
        self.assertTrue(any("Quantum Annealing" in q for q in res["follow_up_questions"]))

    def test_intent_router_fallback_on_garbled_and_truncated_output(self):
        """
        Confirms route_followup_intent schema confinement falls back to LOCAL_QA on malformed output.
        """
        mock_router = MagicMock()

        # Garbled JSON
        mock_router.invoke.return_value = "Broken { route: "
        with patch("backend.pipeline.router_chain", mock_router):
            decision1 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision1["route"], "LOCAL_QA")

        # Valid JSON but unrecognized route value
        mock_router.invoke.return_value = '{"route": "EXECUTE_UNKNOWN_SHELL"}'
        with patch("backend.pipeline.router_chain", mock_router):
            decision2 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision2["route"], "LOCAL_QA")


if __name__ == "__main__":
    unittest.main()
