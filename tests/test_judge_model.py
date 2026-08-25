import unittest
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field
from unittest.mock import MagicMock, AsyncMock

from backend.eval.judge_model import ThothJudgeModel, _construct_default_schema_instance, _repair_dict_for_schema
from backend.agents import CriticScore, VerificationResult


class SampleEvaluationSchema(BaseModel):
    verdict: str
    score: float = Field(ge=0.0, le=10.0)
    reasons: List[str] = []
    is_grounded: bool = True


class TestThothJudgeModel(unittest.TestCase):
    """Tests for ThothJudgeModel in isolation before wiring into DeepEval metrics."""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_llm.ainvoke = AsyncMock()
        self.judge = ThothJudgeModel(model_instance=self.mock_llm, model_name="Thoth-Test-Judge")

    def test_model_name_and_load_model(self):
        self.assertEqual(self.judge.get_model_name(), "Thoth-Test-Judge")
        self.assertEqual(self.judge.load_model(), self.mock_llm)

    # -------------------------------------------------------------------------
    # 1. Unstructured String Generation
    # -------------------------------------------------------------------------

    def test_generate_unstructured_string(self):
        self.mock_llm.invoke.return_value = "<think>Analyzing...</think>The report is factually accurate."
        res = self.judge.generate("Evaluate this research summary.")
        self.assertEqual(res, "The report is factually accurate.")

    def test_a_generate_unstructured_string(self):
        self.mock_llm.ainvoke.return_value = "<think>Async reasoning...</think>Solid methodology."
        res = asyncio.run(self.judge.a_generate("Evaluate async."))
        self.assertEqual(res, "Solid methodology.")

    # -------------------------------------------------------------------------
    # 2. Schema-Aware Structured Generation (Clean JSON)
    # -------------------------------------------------------------------------

    def test_generate_with_schema_clean_json(self):
        clean_json = """
        {
            "verdict": "Well supported by arXiv citations.",
            "score": 9.2,
            "reasons": ["Direct citation matches", "Clear derivations"],
            "is_grounded": true
        }
        """
        self.mock_llm.invoke.return_value = clean_json
        res = self.judge.generate("Evaluate claims", schema=SampleEvaluationSchema)

        self.assertIsInstance(res, SampleEvaluationSchema)
        self.assertEqual(res.verdict, "Well supported by arXiv citations.")
        self.assertEqual(res.score, 9.2)
        self.assertEqual(len(res.reasons), 2)
        self.assertTrue(res.is_grounded)

    def test_a_generate_with_schema_clean_json(self):
        clean_json = """
        {
            "verdict": "Async verified.",
            "score": 8.5,
            "reasons": ["Passed"],
            "is_grounded": true
        }
        """
        self.mock_llm.ainvoke.return_value = clean_json
        res = asyncio.run(self.judge.a_generate("Evaluate async claims", schema=SampleEvaluationSchema))

        self.assertIsInstance(res, SampleEvaluationSchema)
        self.assertEqual(res.verdict, "Async verified.")
        self.assertEqual(res.score, 8.5)

    # -------------------------------------------------------------------------
    # 3. Schema-Aware with Thinking Tokens & Markdown Fences
    # -------------------------------------------------------------------------

    def test_generate_with_schema_thinking_tokens_and_markdown(self):
        llm_raw = """
        <think>
        I need to score this based on the provided evidence.
        Score is 8.0, verdict is Positive.
        </think>
        ```json
        {
            "verdict": "Positive evidence alignment.",
            "score": 8.0,
            "reasons": ["Good citations"],
            "is_grounded": true
        }
        ```
        """
        self.mock_llm.invoke.return_value = llm_raw
        res = self.judge.generate("Evaluate with thinking tokens", schema=SampleEvaluationSchema)

        self.assertIsInstance(res, SampleEvaluationSchema)
        self.assertEqual(res.score, 8.0)
        self.assertEqual(res.verdict, "Positive evidence alignment.")

    # -------------------------------------------------------------------------
    # 4. Partial Output & Field Repair
    # -------------------------------------------------------------------------

    def test_generate_with_schema_partial_json_repairs_fields(self):
        # LLM only provided 'verdict' and 'score', missing 'reasons' and 'is_grounded'
        partial_json = '{"verdict": "Partial response", "score": 7.5}'
        self.mock_llm.invoke.return_value = partial_json

        res = self.judge.generate("Evaluate partial", schema=SampleEvaluationSchema)
        self.assertIsInstance(res, SampleEvaluationSchema)
        self.assertEqual(res.verdict, "Partial response")
        self.assertEqual(res.score, 7.5)
        # Repaired defaults
        self.assertEqual(res.reasons, [])
        self.assertTrue(res.is_grounded)

    # -------------------------------------------------------------------------
    # 5. Malformed, Corrupted, or Garbled Output Never Raises or Returns None
    # -------------------------------------------------------------------------

    def test_generate_with_schema_garbled_output_returns_valid_default(self):
        # Completely unparseable prose output
        self.mock_llm.invoke.return_value = "Sorry, I cannot produce JSON output for this request."

        res = self.judge.generate("Evaluate bad text", schema=SampleEvaluationSchema)
        self.assertIsNotNone(res)
        self.assertIsInstance(res, SampleEvaluationSchema)
        self.assertIsInstance(res.verdict, str)
        self.assertIsInstance(res.score, float)
        self.assertGreaterEqual(res.score, 0.0)
        self.assertLessEqual(res.score, 10.0)

    def test_generate_with_schema_llm_exception_returns_valid_default(self):
        # LLM raises an unexpected exception
        self.mock_llm.invoke.side_effect = RuntimeError("Rate limit or connection reset")

        res = self.judge.generate("Prompt causing error", schema=SampleEvaluationSchema)
        self.assertIsNotNone(res)
        self.assertIsInstance(res, SampleEvaluationSchema)

    def test_a_generate_with_schema_garbled_output_returns_valid_default(self):
        self.mock_llm.ainvoke.return_value = "Non-json corrupted stream..."

        res = asyncio.run(self.judge.a_generate("Async bad text", schema=SampleEvaluationSchema))
        self.assertIsNotNone(res)
        self.assertIsInstance(res, SampleEvaluationSchema)

    # -------------------------------------------------------------------------
    # 6. Real Thoth Pydantic Schemas (CriticScore & VerificationResult)
    # -------------------------------------------------------------------------

    def test_generate_with_real_critic_score_schema(self):
        mock_critic_json = """
        {
            "faithfulness": 9.0,
            "relevance": 9.5,
            "completeness": 8.5,
            "evidence_quality": 9.0,
            "clarity_and_coherence": 9.0,
            "overall_score": 9.0,
            "strengths": ["Clear methodology"],
            "areas_to_improve": ["Add hardware details"],
            "verdict": "Ready for publication.",
            "reasoning": "Strong evidence base."
        }
        """
        self.mock_llm.invoke.return_value = mock_critic_json
        res = self.judge.generate("Evaluate report with CriticScore", schema=CriticScore)

        self.assertIsInstance(res, CriticScore)
        self.assertEqual(res.overall_score, 9.0)
        self.assertEqual(res.faithfulness, 9.0)

    def test_generate_with_real_verification_result_schema(self):
        mock_vr_json = """
        {
            "claim": "Superconducting qubits operate at millikelvin temperatures.",
            "is_valid": true,
            "supporting_source_id": "src-superconducting_qubits",
            "reason_if_failed": ""
        }
        """
        self.mock_llm.invoke.return_value = mock_vr_json
        res = self.judge.generate("Verify claim", schema=VerificationResult)

        self.assertIsInstance(res, VerificationResult)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.supporting_source_id, "src-superconducting_qubits")


if __name__ == "__main__":
    unittest.main()
