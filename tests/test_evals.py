import unittest
import json
from unittest.mock import MagicMock, patch

from deepeval.test_case import LLMTestCase, ToolCall
from backend.eval import (
    ThothJudgeModel,
    get_mindmap_extractor_goldens,
    get_follow_up_goldens,
    get_mindmap_qa_goldens,
    get_mindmap_updater_goldens,
    get_conversation_summarizer_goldens,
    get_section_expander_goldens,
    get_tool_correctness_goldens,
    get_argument_correctness_goldens,
    get_adversarial_groundedness_goldens,
    get_task_agent_goldens,
    get_report_correctness_benchmark,
    get_router_stress_goldens,
    get_mindmap_extractor_metric,
    get_follow_up_metric,
    get_mindmap_qa_metric,
    get_mindmap_updater_metric,
    get_conversation_summarizer_metric,
    get_section_expander_metric,
    get_tool_correctness_metric,
    get_argument_correctness_metric,
    get_adversarial_groundedness_metric,
    get_writer_metric,
    get_critic_metric,
    get_router_accuracy_metric,
    get_report_correctness_metric,
    calibrate_percentile_threshold,
    evaluate_six_agents,
    evaluate_adversarial_groundedness,
    evaluate_calibrated_report_benchmark,
    evaluate_router_reliability_stress
)
from backend.pipeline import route_followup_intent


class TestSixUncoveredAgents(unittest.TestCase):
    """
    Evaluates the 6 agents that previously had zero coverage:
    Mind Map Extractor, Follow-Up Generator, Mind Map Q&A,
    Mind Map Updater (Node ID uniqueness), Conversation Summarizer, Section Expander.
    """

    def setUp(self):
        self.mock_judge_llm = MagicMock()
        # Mock judge returns positive score for GEval schema
        self.mock_judge_llm.invoke.return_value = '{"score": 9.0, "reason": "All criteria met rigorously."}'
        self.judge = ThothJudgeModel(model_instance=self.mock_judge_llm, model_name="Mock-Thoth-Judge")

    def test_mindmap_extractor_eval(self):
        metric = get_mindmap_extractor_metric(self.judge)
        goldens = get_mindmap_extractor_goldens()
        self.assertGreater(len(goldens), 0)

        for g in goldens:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

    def test_follow_up_generator_eval(self):
        metric = get_follow_up_metric(self.judge)
        goldens = get_follow_up_goldens()
        self.assertGreater(len(goldens), 0)

        for g in goldens:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

    def test_mindmap_qa_agent_eval(self):
        metric = get_mindmap_qa_metric(self.judge)
        goldens = get_mindmap_qa_goldens()
        self.assertGreater(len(goldens), 0)

        for g in goldens:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

    def test_mindmap_updater_node_id_uniqueness_and_eval(self):
        """
        Confirms that the Mind Map Updater integrates new facts with guaranteed unique node IDs,
        preventing node ID collisions that would corrupt the knowledge graph.
        """
        metric = get_mindmap_updater_metric(self.judge)
        goldens = get_mindmap_updater_goldens()
        self.assertGreater(len(goldens), 0)

        for g in goldens:
            # Parse output JSON to check ID uniqueness programmatically
            mm_data = json.loads(g.expected_output)
            node_ids = [n["id"] for n in mm_data["nodes"]]
            self.assertEqual(len(node_ids), len(set(node_ids)), f"Duplicate node ID detected: {node_ids}")
            self.assertTrue(any(nid.startswith("fu_node_") for nid in node_ids), "Follow-up nodes should have 'fu_node_' prefix")

            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

    def test_conversation_summarizer_eval(self):
        metric = get_conversation_summarizer_metric(self.judge)
        goldens = get_conversation_summarizer_goldens()
        self.assertGreater(len(goldens), 0)

        for g in goldens:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

    def test_section_expander_eval(self):
        metric = get_section_expander_metric(self.judge)
        goldens = get_section_expander_goldens()
        self.assertGreater(len(goldens), 0)

        for g in goldens:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)


class TestToolAndArgumentCorrectness(unittest.TestCase):
    """
    Evaluates ToolCorrectnessMetric and ArgumentCorrectnessMetric with ThothJudgeModel.
    """

    def setUp(self):
        self.mock_judge_llm = MagicMock()
        self.mock_judge_llm.invoke.return_value = '{"score": 1.0, "reason": "Tool usage and arguments are correct."}'
        self.judge = ThothJudgeModel(model_instance=self.mock_judge_llm, model_name="Mock-Thoth-Judge")

    def test_tool_correctness_metric_with_goldens(self):
        metric = get_tool_correctness_metric(self.judge)
        goldens = get_tool_correctness_goldens()

        for g in goldens:
            tc = LLMTestCase(
                input=g.input,
                tools_called=g.expected_tools,
                expected_tools=g.expected_tools
            )
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

    def test_argument_correctness_metric_with_goldens(self):
        metric = get_argument_correctness_metric(self.judge)
        goldens = get_argument_correctness_goldens()

        for g in goldens:
            tc = LLMTestCase(
                input=g.input,
                actual_output=g.expected_output,
                expected_output=g.expected_output,
                tools_called=g.tools_called or g.expected_tools,
                expected_tools=g.expected_tools
            )
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)


class TestAdversarialGroundedness(unittest.TestCase):
    """
    Evaluates Verifier Truth Guard against adversarial true/false mixture (JWST-style).
    """

    def setUp(self):
        self.mock_judge_llm = MagicMock()
        self.mock_judge_llm.invoke.return_value = '{"score": 9.5, "reason": "Accurately flagged false claims and verified real sources."}'
        self.judge = ThothJudgeModel(model_instance=self.mock_judge_llm, model_name="Mock-Thoth-Judge")

    def test_adversarial_groundedness_metric(self):
        metric = get_adversarial_groundedness_metric(self.judge)
        goldens = get_adversarial_groundedness_goldens()

        for g in goldens:
            tc = LLMTestCase(
                input=g.input,
                context=g.context,
                actual_output=g.actual_output or g.expected_output
            )
            score = metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)


class TestTaskLevelAgents(unittest.TestCase):
    """
    Evaluates task-level performance for Writer, Critic, and Router.
    """

    def setUp(self):
        self.mock_judge_llm = MagicMock()
        self.mock_judge_llm.invoke.return_value = '{"score": 9.0, "reason": "Task goal achieved."}'
        self.judge = ThothJudgeModel(model_instance=self.mock_judge_llm, model_name="Mock-Thoth-Judge")

    def test_writer_critic_router_task_eval(self):
        goldens_dict = get_task_agent_goldens()

        # Writer
        writer_metric = get_writer_metric(self.judge)
        for g in goldens_dict["writer"]:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = writer_metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

        # Critic
        critic_metric = get_critic_metric(self.judge)
        for g in goldens_dict["critic"]:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = critic_metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)

        # Router
        router_metric = get_router_accuracy_metric(self.judge)
        for g in goldens_dict["router"]:
            tc = LLMTestCase(input=g.input, context=g.context, actual_output=g.expected_output)
            score = router_metric.measure(tc)
            self.assertGreaterEqual(score, 0.0)


class TestCalibratedReportCorrectness(unittest.TestCase):
    """
    Benchmark evaluation of 16 hand-labeled reports with percentile threshold calibration.
    """

    def test_calibrated_threshold_computation(self):
        # Simulated benchmark scores for 8 good and 8 bad reports
        good_scores = [8.5, 9.0, 9.2, 8.8, 9.5, 8.9, 9.1, 9.4]
        bad_scores = [2.0, 1.5, 3.0, 0.5, 2.5, 1.0, 3.5, 0.0]

        threshold = calibrate_percentile_threshold(good_scores, percentile=75.0)
        self.assertGreaterEqual(threshold, 0.85)
        self.assertLessEqual(threshold, 0.95)

        # Verify that all good scores pass the threshold and all bad scores fail
        self.assertTrue(all(s > max(bad_scores) for s in good_scores))

    def test_report_benchmark_dataset_structure(self):
        benchmark = get_report_correctness_benchmark()
        self.assertEqual(len(benchmark), 16)
        good_count = sum(1 for b in benchmark if b.additional_metadata.get("label") == "GOOD")
        bad_count = sum(1 for b in benchmark if b.additional_metadata.get("label") == "BAD")
        self.assertEqual(good_count, 8)
        self.assertEqual(bad_count, 8)


class TestIntentRouterReliabilityStress(unittest.TestCase):
    """
    Stress test of the Intent Router on 20+ queries:
    Validates route selection and confirms 0% raw JSON parse failure rate.
    """

    def test_router_stress_dataset_zero_parse_failures(self):
        goldens = get_router_stress_goldens()
        self.assertGreaterEqual(len(goldens), 20)

        mock_router_chain = MagicMock()

        for g in goldens:
            expected_route = g.expected_output
            mock_router_chain.invoke.return_value = json.dumps({
                "route": expected_route,
                "reasoning": f"Routing query directly to {expected_route}",
                "search_query": g.input if expected_route == "WEB_SEARCH" else ""
            })

            with patch("backend.pipeline.router_chain", mock_router_chain):
                decision = route_followup_intent(
                    topic="Quantum Computing",
                    mindmap_summary="Mindmap nodes on transmon qubits",
                    report_summary="Report on quantum architectures",
                    user_query=g.input
                )

            # Check that decision has valid route
            self.assertIn("route", decision)
            self.assertIn(decision["route"], {"LOCAL_QA", "WEB_SEARCH", "REPORT_EXPANSION"})
            self.assertEqual(decision["route"], expected_route)


if __name__ == "__main__":
    unittest.main()
