"""
Comprehensive unit test suite for Pre-Flight Clarification Gating.
"""

import unittest
from backend.conversation.mandate import ResearchMandate
from backend.conversation.clarification import (
    ClarificationResult,
    evaluate_clarification_need,
    BROAD_TOPIC_KEYWORDS,
)


class TestPreFlightClarificationGate(unittest.TestCase):
    """Tests scoping evaluation and option generation for ambiguous queries."""

    def test_broad_single_word_topics_require_clarification(self):
        for kw in ["ai", "cancer", "battery", "quantum", "robotics"]:
            mandate = ResearchMandate(
                objective="Conduct research",
                primary_question=kw.title(),
                topic=kw.title(),
            )
            res = evaluate_clarification_need(mandate)
            self.assertTrue(
                res.needs_clarification,
                f"Failed to flag broad keyword: {kw}",
            )
            self.assertGreaterEqual(len(res.options), 2)
            self.assertTrue(len(res.clarification_prompt) > 10)

    def test_multi_word_specific_queries_bypass_clarification(self):
        specific_topics = [
            "2026 CRISPR Prime Editing Off-Target Fidelity in Human T-Cells",
            "Superconducting Surface Code Quantum Error Correction Thresholds",
            "Sparse Autoencoders for LLM Mechanistic Interpretability",
            "Garnet LLZO Solid State Electrolyte ALD Alumina Interlayers",
        ]
        for topic in specific_topics:
            mandate = ResearchMandate(
                objective=f"Research {topic}",
                primary_question=topic,
                topic=topic,
            )
            res = evaluate_clarification_need(mandate)
            self.assertFalse(
                res.needs_clarification,
                f"Incorrectly flagged specific topic: {topic}",
            )
            self.assertEqual(len(res.options), 0)

    def test_inherited_constraints_bypass_clarification(self):
        # Even if the topic string is broad ("AI"), having constraints from
        # previous dialogue eliminates the need for redundant clarification
        mandate = ResearchMandate(
            objective="Research AI",
            primary_question="AI",
            topic="AI",
            constraints=["focus on mechanistic interpretability"],
            known_facts=["Residual stream acts as a communication channel."],
        )
        res = evaluate_clarification_need(mandate)
        self.assertFalse(res.needs_clarification)
        self.assertIn("inherited", res.reason.lower())

    def test_clarification_result_serialization(self):
        res = ClarificationResult(
            needs_clarification=True,
            clarification_prompt="Please select a research scope:",
            options=["Option 1", "Option 2"],
            reason="Ambiguous query",
        )
        d = res.to_dict()
        self.assertTrue(d["needs_clarification"])
        self.assertEqual(len(d["options"]), 2)
        self.assertEqual(d["reason"], "Ambiguous query")


if __name__ == "__main__":
    unittest.main()
