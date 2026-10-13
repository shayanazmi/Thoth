import unittest
import json
import pydantic
from pydantic import ValidationError
from unittest.mock import patch, MagicMock

from backend.agents import (
    VerificationResult,
    FactVerificationReport,
    CriticScore,
    safe_extract_json,
    strip_chain_of_thought,
    router_prompt
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
        with self.assertRaises(ValidationError):
            VerificationResult(is_valid=True)

        with self.assertRaises(ValidationError):
            VerificationResult(claim="Quantum claim")

    def test_verification_result_invalid_types_raise(self):
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

        with self.assertRaises(ValidationError):
            FactVerificationReport()

        with self.assertRaises(ValidationError):
            FactVerificationReport(results=[{"invalid_key": "bad"}])

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

        d = candidate.to_dict()
        self.assertEqual(d["title"], candidate.title)
        self.assertEqual(d["source_api"], "arxiv")

        snippet = candidate.to_formatted_snippet()
        self.assertIn("A Survey of Quantum Error Correction", snippet)
        self.assertIn("10.1000/qec123", snippet)

    def test_source_candidate_missing_required_positional_args_raises(self):
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

        d = note.to_dict()
        self.assertEqual(d["note_id"], "note_topological_qubits")
        self.assertEqual(d["type"], "concept")
        self.assertEqual(d["content"], note.content)

    def test_note_missing_required_positional_args_raises(self):
        with self.assertRaises(TypeError):
            Note()

class TestTypedDictsAndConstructors(unittest.TestCase):
    def test_research_state_created_with_all_required_keys(self):
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

        self.assertIn("nodes", state["mindmap"])
        self.assertIn("edges", state["mindmap"])
        self.assertIsInstance(state["mindmap"]["nodes"], list)
        self.assertIsInstance(state["mindmap"]["edges"], list)

    def test_mindmap_node_construction_and_structure(self):
        sample_state = {
            "topic": "Neutral Atom Qubits",
            "report": "# Neutral Atom Qubits\nRydberg blockade enables two-qubit entangling gates.",
            "cumulative_sources": [{"url": "https://arxiv.org/abs/2401.12345"}]
        }

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

        node = mm["nodes"][0]
        self.assertEqual(node["id"], "root")
        self.assertEqual(node["label"], "Neutral Atoms")
        self.assertEqual(node["type"], "topic")

        edge = mm["edges"][0]
        self.assertEqual(edge["from"], "root")
        self.assertEqual(edge["to"], "sub1")
        self.assertEqual(edge["label"], "enables")

class TestSchemaConsumersMalformedLLMOutputs(unittest.TestCase):
    def test_critic_node_handles_thinking_tokens_and_markdown_fences(self):
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
        mock_critic = MagicMock()
        mock_critic.invoke.return_value = "I cannot format this as JSON at all."

        with patch("backend.pipeline.critic_chain", mock_critic):
            with self.assertRaises(ValueError):
                critic_node({"topic": "Quantum Computing", "report": "Report content..."})

    def test_verifier_node_handles_malformed_and_unsupported_text(self):
        mock_verifier = MagicMock()

        mock_verifier.invoke.return_value = "Error parsing: Claim 1 contradicts the provided arXiv paper."
        with patch("backend.pipeline.verifier_chain", mock_verifier):
            res1 = verifier_node({"cumulative_sources": [], "report": "Report text"})
            self.assertIn("contradicts", res1["verifier_feedback"])

        clean_json = '{"results": [{"claim": "Qubits exist", "is_valid": true, "supporting_source_id": "src-paper", "reason_if_failed": ""}]}'
        mock_verifier.invoke.return_value = clean_json
        with patch("backend.pipeline.verifier_chain", mock_verifier):
            res2 = verifier_node({"cumulative_sources": [], "report": "Report text"})
            self.assertEqual(res2["verifier_feedback"], "")
            self.assertEqual(len(res2["verification_results"]), 1)

    def test_mindmap_node_fallback_on_garbled_json(self):
        mock_mm = MagicMock()
        mock_mm.invoke.return_value = "Invalid JSON non-graph response"

        with patch("backend.pipeline.mindmap_extractor_chain", mock_mm):
            res = mindmap_node({"topic": "Quantum Teleportation", "report": "Content", "cumulative_sources": []})

        self.assertIn("mindmap", res)
        self.assertEqual(len(res["mindmap"]["nodes"]), 4)
        self.assertEqual(res["mindmap"]["nodes"][0]["id"], "root")
        self.assertEqual(res["mindmap"]["nodes"][0]["label"], "Quantum Teleportation")

    def test_follow_up_node_fallback_on_garbled_json(self):
        mock_fu = MagicMock()
        mock_fu.invoke.return_value = "Not a JSON array"

        with patch("backend.pipeline.follow_up_chain", mock_fu):
            res = follow_up_node({"topic": "Quantum Annealing", "report": "Content"})

        self.assertIn("follow_up_questions", res)
        self.assertGreaterEqual(len(res["follow_up_questions"]), 2)
        self.assertTrue(any("Quantum Annealing" in q for q in res["follow_up_questions"]))

    def test_intent_router_fallback_on_garbled_and_truncated_output(self):
        mock_router = MagicMock()

        mock_router.invoke.return_value = "Broken { route: "
        with patch("backend.pipeline.router_chain", mock_router):
            decision1 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision1["route"], "LOCAL_QA")

        mock_router.invoke.return_value = '{"route": "EXECUTE_UNKNOWN_SHELL"}'
        with patch("backend.pipeline.router_chain", mock_router):
            decision2 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision2["route"], "LOCAL_QA")

    def test_intent_router_chitchat_route_classification(self):
        mock_router = MagicMock()
        mock_router.invoke.return_value = '{"route": "CHITCHAT", "reasoning": "Conversational greeting without research inquiry", "search_query": ""}'
        with patch("backend.pipeline.router_chain", mock_router):
            decision = route_followup_intent(
                topic="Fault-Tolerant Quantum Computing",
                mindmap_summary="5 concepts",
                report_summary="Report overview",
                user_query="Hello Thoth, how are you today?"
            )
            self.assertEqual(decision["route"], "CHITCHAT")
            self.assertEqual(decision["reasoning"], "Conversational greeting without research inquiry")
            self.assertEqual(decision["search_query"], "")

    def test_intent_router_all_permitted_routes(self):
        test_routes = [
            ("LOCAL_QA", "Answerable from existing mindmap and report", ""),
            ("WEB_SEARCH", "Requires fresh external literature probe", "Cat qubit hardware overhead 2026"),
            ("REPORT_EXPANSION", "User explicitly requests a new section", ""),
            ("CHITCHAT", "Casual conversational message", "")
        ]
        mock_router = MagicMock()
        with patch("backend.pipeline.router_chain", mock_router):
            for r_name, r_reason, r_query in test_routes:
                mock_router.invoke.return_value = json.dumps({
                    "route": r_name,
                    "reasoning": r_reason,
                    "search_query": r_query
                })
                decision = route_followup_intent("Topic", "Mindmap", "Report", "Query")
                self.assertEqual(decision["route"], r_name)
                self.assertEqual(decision["reasoning"], r_reason)
                self.assertEqual(decision["search_query"], r_query)

    def test_intent_router_deep_research_branch_preserved(self):
        mock_router = MagicMock()
        mock_router.invoke.return_value = '{"route": "DEEP_RESEARCH_BRANCH", "reasoning": "Deep multi-stage probe", "search_query": "Surface codes deep dive"}'
        with patch("backend.pipeline.router_chain", mock_router):
            decision = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision["route"], "DEEP_RESEARCH_BRANCH")
            self.assertEqual(decision["search_query"], "Surface codes deep dive")

    def test_intent_router_missing_and_unsupported_route_fallback(self):
        mock_router = MagicMock()
        with patch("backend.pipeline.router_chain", mock_router):
            mock_router.invoke.return_value = '{"reasoning": "Missing route field", "search_query": ""}'
            decision1 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision1["route"], "LOCAL_QA")

            mock_router.invoke.return_value = '{"route": null, "reasoning": "Null route", "search_query": ""}'
            decision2 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision2["route"], "LOCAL_QA")

            mock_router.invoke.return_value = '{"route": "ARBITRARY_NONEXISTENT_ROUTE"}'
            decision3 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision3["route"], "LOCAL_QA")

    def test_intent_router_malformed_json_resilience(self):
        mock_router = MagicMock()
        malformed_outputs = [
            "",
            "   ",
            "Not JSON at all",
            "{\"route\": \"CHITCHAT\", unclosed...",
            "<think>Thinking process with broken JSON</think> route: CHITCHAT",
            "{bad_json: 123}"
        ]
        with patch("backend.pipeline.router_chain", mock_router):
            for bad_output in malformed_outputs:
                mock_router.invoke.return_value = bad_output
                try:
                    decision = route_followup_intent("Topic", "Mindmap", "Report", "Query")
                    self.assertEqual(decision["route"], "LOCAL_QA")
                    self.assertIsInstance(decision["reasoning"], str)
                    self.assertIsInstance(decision["search_query"], str)
                except Exception as e:
                    self.fail(f"route_followup_intent raised an uncaught exception on malformed output: {e}")

    def test_intent_router_invocation_exception_handling_and_logging(self):
        mock_router = MagicMock()
        mock_router.invoke.side_effect = RuntimeError("Simulated API connection failure")
        with patch("backend.pipeline.router_chain", mock_router):
            with self.assertLogs("ThothPipeline", level="ERROR") as cm:
                decision = route_followup_intent("Topic", "Mindmap", "Report", "Query")
                self.assertEqual(decision["route"], "LOCAL_QA")
                self.assertIn("RuntimeError", decision["reasoning"])
                self.assertTrue(any("Router invocation failed" in log for log in cm.output))

    def test_intent_router_json_array_resilience_and_logging(self):
        mock_router = MagicMock()
        mock_router.invoke.return_value = '["unexpected", "json", "array"]'
        with patch("backend.pipeline.router_chain", mock_router):
            with self.assertLogs("ThothPipeline", level="WARNING") as cm:
                decision = route_followup_intent("Topic", "Mindmap", "Report", "Query")
                self.assertEqual(decision["route"], "LOCAL_QA")
                self.assertTrue(any("not a dictionary" in log for log in cm.output))

    def test_intent_router_diagnostic_logging_for_failure_categories(self):
        mock_router = MagicMock()
        with patch("backend.pipeline.router_chain", mock_router):
            mock_router.invoke.return_value = "{completely invalid"
            with self.assertLogs("ThothPipeline", level="WARNING") as cm1:
                dec1 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
                self.assertEqual(dec1["route"], "LOCAL_QA")
                self.assertTrue(any("could not be parsed into a supported JSON value" in log for log in cm1.output))

            mock_router.invoke.return_value = '{"reasoning": "Missing route"}'
            with self.assertLogs("ThothPipeline", level="WARNING") as cm2:
                dec2 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
                self.assertEqual(dec2["route"], "LOCAL_QA")
                self.assertTrue(any("missing a usable route" in log for log in cm2.output))

            mock_router.invoke.return_value = '{"route": "INVALID_ACTION_123"}'
            with self.assertLogs("ThothPipeline", level="WARNING") as cm3:
                dec3 = route_followup_intent("Topic", "Mindmap", "Report", "Query")
                self.assertEqual(dec3["route"], "LOCAL_QA")
                self.assertTrue(any("unsupported route" in log for log in cm3.output))

    def test_intent_router_valid_route_info_logging(self):
        mock_router = MagicMock()
        mock_router.invoke.return_value = '{"route": "CHITCHAT", "reasoning": "Conversational greeting", "search_query": ""}'
        with patch("backend.pipeline.router_chain", mock_router):
            with self.assertLogs("ThothPipeline", level="INFO") as cm:
                decision = route_followup_intent("Topic", "Mindmap", "Report", "Hello Thoth")
                self.assertEqual(decision["route"], "CHITCHAT")
                self.assertTrue(any("Router returned a valid route: 'CHITCHAT'" in log for log in cm.output))

    def test_intent_router_unclosed_reasoning_fails_safely_to_fallback(self):
        mock_router = MagicMock()
        mock_router.invoke.return_value = "<think>Let us pick {\"route\": \"WEB_SEARCH\", \"search_query\": \"misleading\"}\nUnfinished..."
        with patch("backend.pipeline.router_chain", mock_router):
            decision = route_followup_intent("Topic", "Mindmap", "Report", "Query")
            self.assertEqual(decision["route"], "LOCAL_QA")
            self.assertNotEqual(decision["route"], "WEB_SEARCH")

    def test_router_prompt_distinguishes_greeting_with_substantive_question(self):
        system_msg = router_prompt.messages[0].prompt.template
        self.assertIn("CHITCHAT", system_msg)
        self.assertIn("Critical Instruction", system_msg)
        self.assertIn("must NOT be classified as CHITCHAT", system_msg)
        self.assertIn("Hi Thoth, explain fault tolerance in surface codes", system_msg)

        formatted = router_prompt.format_messages(
            topic="Quantum Computing",
            mindmap_summary="5 nodes",
            report_summary="Report content",
            user_query="Hi Thoth, what is the threshold?"
        )
        self.assertEqual(len(formatted), 2)
        self.assertIn("Hi Thoth, what is the threshold?", formatted[1].content)

if __name__ == "__main__":
    unittest.main()
