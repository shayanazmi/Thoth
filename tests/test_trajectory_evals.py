import unittest
import asyncio
from unittest.mock import MagicMock, patch

from deepeval.dataset import EvaluationDataset, Golden
from deepeval.test_case import LLMTestCase
from backend.eval import (
    ThothJudgeModel,
    get_task_completion_metric,
    get_step_efficiency_metric,
    get_plan_adherence_metric,
    get_trajectory_goldens
)
from backend.telemetry import enable_local_tracing, clear_local_traces, get_local_traces
from backend.orchestrator import run_research_pipeline, stream_research_pipeline
from backend.scholarly import SourceCandidate
from backend.dispatcher import Dispatcher, CircuitBreakerOpenError


class TestOrchestratorTrajectoryEvaluations(unittest.TestCase):
    """
    Trajectory and multi-agent loop evaluation suite.
    Uses TaskCompletionMetric, StepEfficiencyMetric, and PlanAdherenceMetric
    against ambient @observe traces.
    """

    def setUp(self):
        enable_local_tracing()
        clear_local_traces()
        self.mock_judge_llm = MagicMock()
        self.mock_judge_llm.invoke.return_value = '{"score": 9.0, "reason": "Execution followed planned multi-agent trajectory efficiently."}'
        self.judge = ThothJudgeModel(model_instance=self.mock_judge_llm, model_name="Mock-Trajectory-Judge")

        self.task_completion = get_task_completion_metric(self.judge)
        self.step_efficiency = get_step_efficiency_metric(self.judge)
        self.plan_adherence = get_plan_adherence_metric(self.judge)

    def test_trajectory_evals_iterator_clean_path(self):
        """
        Scenario 1: Clean Path (no replans needed).
        Confirms TaskCompletionMetric and StepEfficiencyMetric score the trajectory well.
        """
        clean_goldens = [g for g in get_trajectory_goldens() if g.name == "TRAJECTORY_CLEAN_PATH"]
        self.assertEqual(len(clean_goldens), 1)
        dataset = EvaluationDataset(goldens=clean_goldens)

        mock_sources = [
            SourceCandidate(
                title="Topological Quantum Computing",
                authors=["Dr. Majorana"],
                abstract="Majorana modes provide topological protection.",
                url="https://arxiv.org/abs/2401.55555",
                source_api="arxiv"
            )
        ]
        mock_writer = MagicMock()
        mock_writer.invoke.return_value = "# Topological Quantum Computing\n\n## Overview\nMajorana zero modes provide topological protection [src-topological_quantum_computing]."
        mock_verifier = MagicMock()
        mock_verifier.invoke.return_value = '{"results": [{"claim": "Majorana zero modes provide topological protection", "is_valid": true, "supporting_source_id": "src-topological_quantum_computing", "reason_if_failed": ""}]}'
        mock_critic = MagicMock()
        mock_critic.invoke.return_value = '{"faithfulness": 9.0, "relevance": 9.5, "completeness": 9.0, "evidence_quality": 9.0, "clarity_and_coherence": 9.0, "overall_score": 9.1, "strengths": ["Clear"], "areas_to_improve": [], "verdict": "Ready", "reasoning": "Strong"}'
        mock_mm = MagicMock()
        mock_mm.invoke.return_value = '{"nodes": [{"id": "node_0", "label": "Topological QC", "type": "topic", "details": "Core", "group": "topic"}], "edges": []}'
        mock_fu = MagicMock()
        mock_fu.invoke.return_value = '["What are the non-abelian braiding rules?"]'

        mock_scrape = MagicMock()
        mock_scrape.invoke.return_value = "Scraped Majorana text"

        with patch("backend.pipeline.search_scholarly_sources", return_value=mock_sources), \
             patch("backend.pipeline.writer_chain", mock_writer), \
             patch("backend.pipeline.verifier_chain", mock_verifier), \
             patch("backend.pipeline.critic_chain", mock_critic), \
             patch("backend.pipeline.mindmap_extractor_chain", mock_mm), \
             patch("backend.pipeline.follow_up_chain", mock_fu), \
             patch("backend.orchestrator.scrape_url", mock_scrape):

            for golden in dataset.evals_iterator(metrics=[self.task_completion, self.step_efficiency, self.plan_adherence]):
                result_state = run_research_pipeline(golden.input)
                self.assertIn("report", result_state)
                self.assertEqual(result_state["attempt"], 1)

    def test_trajectory_replan_branch_1_verifier_contradiction(self):
        """
        Scenario 2: Replan Branch 1 (Verifier flags contradiction on attempt 1 -> loops back to Writer).
        Confirms PlanAdherenceMetric reflects loopback and attempt 2 addresses feedback.
        """
        goldens = [g for g in get_trajectory_goldens() if g.name == "TRAJECTORY_REPLAN_BRANCH_1_VERIFIER"]
        self.assertEqual(len(goldens), 1)
        dataset = EvaluationDataset(goldens=goldens)

        mock_sources = [
            SourceCandidate(
                title="JWST Optics Overview",
                authors=["NASA"],
                abstract="JWST features beryllium mirrors.",
                url="https://arxiv.org/abs/2401.77777",
                source_api="arxiv"
            )
        ]

        # Writer generates flawed draft on attempt 1, corrected draft on attempt 2
        writer_calls = [
            "# JWST Optics\nJWST primary mirror is made of solid gold.",
            "# JWST Optics\nJWST primary mirror is made of gold-coated beryllium segments [src-jwst_optics_overview]."
        ]
        mock_writer = MagicMock()
        mock_writer.invoke.side_effect = writer_calls

        # Verifier flags contradiction on attempt 1, passes on attempt 2
        verifier_calls = [
            '{"results": [{"claim": "JWST primary mirror is made of solid gold", "is_valid": false, "supporting_source_id": "", "reason_if_failed": "Mirror is beryllium, not solid gold."}]}',
            '{"results": [{"claim": "JWST primary mirror is made of gold-coated beryllium segments", "is_valid": true, "supporting_source_id": "src-jwst_optics_overview", "reason_if_failed": ""}]}'
        ]
        mock_verifier = MagicMock()
        mock_verifier.invoke.side_effect = verifier_calls

        mock_critic = MagicMock()
        mock_critic.invoke.return_value = '{"faithfulness": 9.0, "relevance": 9.0, "completeness": 9.0, "evidence_quality": 9.0, "clarity_and_coherence": 9.0, "overall_score": 9.0, "strengths": ["Accurate"], "areas_to_improve": [], "verdict": "Passed", "reasoning": "Fixed"}'
        mock_mm = MagicMock()
        mock_mm.invoke.return_value = '{"nodes": [{"id": "node_0", "label": "JWST", "type": "topic", "details": "Optics", "group": "topic"}], "edges": []}'
        mock_fu = MagicMock()
        mock_fu.invoke.return_value = '["What is the mirror alignment procedure?"]'

        mock_scrape = MagicMock()
        mock_scrape.invoke.return_value = "JWST beryllium mirror data"

        with patch("backend.pipeline.search_scholarly_sources", return_value=mock_sources), \
             patch("backend.pipeline.writer_chain", mock_writer), \
             patch("backend.pipeline.verifier_chain", mock_verifier), \
             patch("backend.pipeline.critic_chain", mock_critic), \
             patch("backend.pipeline.mindmap_extractor_chain", mock_mm), \
             patch("backend.pipeline.follow_up_chain", mock_fu), \
             patch("backend.orchestrator.scrape_url", mock_scrape):

            for golden in dataset.evals_iterator(metrics=[self.plan_adherence, self.task_completion]):
                result_state = run_research_pipeline(golden.input, max_retries=2)
                # Confirm orchestrator completed attempt 2
                self.assertEqual(result_state["attempt"], 2)
                self.assertIn("beryllium", result_state["report"])
                self.assertEqual(result_state["verifier_feedback"], "")

    def test_trajectory_replan_branch_2_critic_quality_deficit(self):
        """
        Scenario 3: Replan Branch 2 (Verifier passes with no contradictions, but Critic score < min_score).
        Confirms Branch 2 is distinguished in trace from Branch 1.
        """
        goldens = [g for g in get_trajectory_goldens() if g.name == "TRAJECTORY_REPLAN_BRANCH_2_CRITIC"]
        self.assertEqual(len(goldens), 1)
        dataset = EvaluationDataset(goldens=goldens)

        mock_sources = [
            SourceCandidate(
                title="Perovskite Solar Stability",
                authors=["Dr. Solar"],
                abstract="2D/3D perovskite heterostructures enhance stability.",
                url="https://arxiv.org/abs/2401.88888",
                source_api="arxiv"
            )
        ]

        mock_writer = MagicMock()
        mock_writer.invoke.side_effect = [
            "# Perovskite Solar Cells\nBrief overview.",
            "# Perovskite Solar Cells\nComprehensive breakdown with deep stability metrics [src-perovskite_solar_stability]."
        ]

        # Verifier passes both attempts (verifier_feedback is empty)
        mock_verifier = MagicMock()
        mock_verifier.invoke.return_value = '{"results": [{"claim": "2D/3D perovskite enhances stability", "is_valid": true, "supporting_source_id": "src-perovskite_solar_stability", "reason_if_failed": ""}]}'

        # Critic returns 5.0 (below min_score 7.0) on attempt 1, 8.5 on attempt 2
        mock_critic = MagicMock()
        mock_critic.invoke.side_effect = [
            '{"faithfulness": 8.0, "relevance": 6.0, "completeness": 4.0, "evidence_quality": 5.0, "clarity_and_coherence": 5.0, "overall_score": 5.0, "strengths": [], "areas_to_improve": ["Add depth"], "verdict": "Too shallow", "reasoning": "Need more sections"}',
            '{"faithfulness": 9.0, "relevance": 9.0, "completeness": 8.5, "evidence_quality": 8.5, "clarity_and_coherence": 8.5, "overall_score": 8.7, "strengths": ["Deep analysis"], "areas_to_improve": [], "verdict": "High quality", "reasoning": "Comprehensive"}'
        ]

        mock_mm = MagicMock()
        mock_mm.invoke.return_value = '{"nodes": [{"id": "node_0", "label": "Perovskites", "type": "topic", "details": "Solar", "group": "topic"}], "edges": []}'
        mock_fu = MagicMock()
        mock_fu.invoke.return_value = '["What are the degradation mechanisms under UV light?"]'

        mock_scrape = MagicMock()
        mock_scrape.invoke.return_value = "Perovskite efficiency data"

        with patch("backend.pipeline.search_scholarly_sources", return_value=mock_sources), \
             patch("backend.pipeline.writer_chain", mock_writer), \
             patch("backend.pipeline.verifier_chain", mock_verifier), \
             patch("backend.pipeline.critic_chain", mock_critic), \
             patch("backend.pipeline.mindmap_extractor_chain", mock_mm), \
             patch("backend.pipeline.follow_up_chain", mock_fu), \
             patch("backend.orchestrator.scrape_url", mock_scrape):

            for golden in dataset.evals_iterator(metrics=[self.plan_adherence, self.task_completion]):
                result_state = run_research_pipeline(golden.input, min_score=7.0, max_retries=2)
                # Confirm orchestrator looped to attempt 2 because of Critic score < min_score
                self.assertEqual(result_state["attempt"], 2)
                self.assertGreaterEqual(result_state["score"], 7.0)

    def test_trajectory_circuit_breaker_open_graceful_handling(self):
        """
        Scenario 5: Dispatcher Circuit Breaker OPEN mid-run.
        Confirms orchestrator surfaces partial-result/safe state without hanging or crashing.
        """
        # Create a custom dispatcher whose circuit breaker is in OPEN state
        failing_dispatcher = Dispatcher(max_consecutive_failures=1, cooloff_seconds=600.0)
        # Force breaker into OPEN state
        asyncio.run(failing_dispatcher._record_failure())
        self.assertEqual(failing_dispatcher.state, "OPEN")

        mock_sources = [
            SourceCandidate(
                title="Quantum Error Correction",
                authors=["Alice"],
                abstract="Overview of QEC.",
                url="https://arxiv.org/abs/2401.00001",
                source_api="arxiv"
            )
        ]
        mock_writer = MagicMock()
        mock_writer.invoke.return_value = "# Quantum Error Correction\nInitial synthesis draft."
        mock_mm = MagicMock()
        mock_mm.invoke.return_value = '{"nodes": [{"id": "node_0", "label": "QEC", "type": "topic", "details": "Fault tolerance", "group": "topic"}], "edges": []}'
        mock_fu = MagicMock()
        mock_fu.invoke.return_value = '["What is the physical error threshold?"]'

        with patch("backend.pipeline.search_scholarly_sources", return_value=mock_sources), \
             patch("backend.pipeline.writer_chain", mock_writer), \
             patch("backend.pipeline.mindmap_extractor_chain", mock_mm), \
             patch("backend.pipeline.follow_up_chain", mock_fu):

            # Run research pipeline with the OPEN circuit breaker dispatcher
            result_state = run_research_pipeline(
                topic="Quantum Error Correction",
                scrape_top_n=1,
                dispatcher=failing_dispatcher
            )

            # Confirm pipeline completed gracefully, surfaced partial report and verification status
            self.assertIn("report", result_state)
            self.assertIn("verification_status", result_state)
            self.assertIn("UNAVAILABLE", result_state["verification_status"])


if __name__ == "__main__":
    unittest.main()
