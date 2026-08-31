"""
Unit tests for Conversational Research Escalation, Mandate Synthesis,
and Pre-Flight Clarification Gate.
"""

import unittest
from backend.conversation.escalation import (
    EscalationState,
    detect_escalation_intent,
)
from backend.conversation.mandate import (
    ResearchMandate,
    synthesize_research_mandate,
)
from backend.conversation.clarification import (
    evaluate_clarification_need,
    ClarificationResult,
)


class TestConversationEscalation(unittest.TestCase):
    """Tests 3-state escalation model and intent detection."""

    def test_casual_chat_stays_in_chat_state(self):
        res = detect_escalation_intent("Hi there, how are you doing today?")
        self.assertEqual(res["state"], EscalationState.CHAT)
        self.assertFalse(res["prompt_user"])

    def test_explicit_research_commands_trigger_research_ready(self):
        queries = [
            "Research this deeply",
            "Can you do a deep dive into solid state electrolyte degradation?",
            "Find papers on CRISPR prime editing off-target fidelity",
            "Please check the literature on LLM mechanistic interpretability",
            "ispar research karo",
            "papers dhundho on perovskite solar cells",
        ]
        for q in queries:
            res = detect_escalation_intent(q)
            self.assertEqual(
                res["state"],
                EscalationState.RESEARCH_READY,
                f"Failed on query: {q}",
            )
            self.assertGreaterEqual(res["confidence"], 0.85)

    def test_technical_conversation_without_evidence_need_stays_chat(self):
        # A technical question explaining a known concept should not trigger deep research
        res = detect_escalation_intent(
            "What is the difference between a mutex and a semaphore?"
        )
        self.assertEqual(res["state"], EscalationState.CHAT)

    def test_multi_turn_implicit_research_candidate(self):
        # Multi-turn conversation where user asks for empirical literature proof
        chat_turns = [
            {"user": "Solid state batteries have dendrite issues.", "assistant": "Yes, lithium dendrites short-circuit the cell."},
            {"user": "What if we use a polymer interlayer with LLZO?", "assistant": "That can reduce interfacial resistance."},
        ]
        res = detect_escalation_intent(
            user_query="Is there any empirical proof or benchmark in recent papers?",
            chat_turns=chat_turns,
        )
        self.assertEqual(res["state"], EscalationState.RESEARCH_CANDIDATE)
        self.assertTrue(res["prompt_user"])
        self.assertIn("suggestion", res)


class TestResearchMandateSynthesis(unittest.TestCase):
    """Tests synthesis of conversation history into structured ResearchMandate."""

    def test_mandate_inherits_constraints_and_hypotheses(self):
        chat_turns = [
            {"user": "Focus on solid-state batteries published since 2024.", "assistant": "Understood."},
            {"user": "What if LLZO garnet electrolytes are coated with ALD alumina?", "assistant": "ALD alumina protects against lithium reduction."},
        ]
        summary = "Established that ALD alumina prevents reduction of LLZO."

        mandate = synthesize_research_mandate(
            user_query="Research this deeply",
            chat_turns=chat_turns,
            conversation_summary=summary,
        )

        self.assertIsInstance(mandate, ResearchMandate)
        self.assertTrue(len(mandate.constraints) > 0 or len(mandate.hypotheses) > 0)
        self.assertTrue(any("2024" in c for c in mandate.constraints))
        self.assertIn("ALD alumina", mandate.known_facts[0] if mandate.known_facts else "")

    def test_mandate_to_dict_serialization(self):
        mandate = ResearchMandate(
            objective="Investigate quantum error correction",
            primary_question="What are the surface code thresholds?",
            sub_questions=["What physical error rates are needed?"],
            constraints=["focus on superconducting qubits"],
            topic="Quantum Error Correction",
        )
        d = mandate.to_dict()
        self.assertEqual(d["topic"], "Quantum Error Correction")
        self.assertEqual(d["objective"], "Investigate quantum error correction")
        self.assertEqual(len(d["constraints"]), 1)


class TestPreFlightClarification(unittest.TestCase):
    """Tests pre-flight clarification gating."""

    def test_broad_keyword_triggers_clarification(self):
        mandate = ResearchMandate(
            objective="Conduct research",
            primary_question="Cancer research",
            topic="Cancer",
        )
        res = evaluate_clarification_need(mandate)
        self.assertTrue(res.needs_clarification)
        self.assertGreaterEqual(len(res.options), 2)
        self.assertIn("Cancer", res.clarification_prompt)

    def test_specific_prompt_bypasses_clarification(self):
        mandate = ResearchMandate(
            objective="Conduct research",
            primary_question="2026 CRISPR Prime Editing Off-Target Fidelity in Human T-Cells",
            topic="2026 CRISPR Prime Editing Off-Target Fidelity in Human T-Cells",
        )
        res = evaluate_clarification_need(mandate)
        self.assertFalse(res.needs_clarification)

    def test_mandate_with_chat_constraints_bypasses_clarification(self):
        mandate = ResearchMandate(
            objective="Conduct research",
            primary_question="AI",
            topic="AI",
            constraints=["focus on mechanistic interpretability sparse autoencoders"],
        )
        res = evaluate_clarification_need(mandate)
        self.assertFalse(res.needs_clarification)


if __name__ == "__main__":
    unittest.main()
