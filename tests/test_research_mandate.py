"""
Comprehensive unit test suite for Research Mandate synthesis,
pronoun/reference resolution, and context constraint inheritance.
"""

import unittest
from backend.conversation.mandate import (
    ResearchMandate,
    synthesize_research_mandate,
    _extract_constraints_and_hypotheses,
)


class TestResearchMandateFidelity(unittest.TestCase):
    """Tests accuracy and information fidelity of ResearchMandate."""

    def test_pronoun_reference_resolution_from_prior_turn(self):
        # When user says "Can you research this?", topic must resolve to the
        # actual problem discussed rather than the literal pronoun string.
        chat_turns = [
            {
                "user": (
                    "We are seeing unsupported claims despite relevant "
                    "retrieval."
                ),
                "assistant": (
                    "That could indicate grounding failure rather than "
                    "recall issues."
                ),
            },
            {
                "user": "I also noticed the issue is worse with longer contexts.",
                "assistant": (
                    "That points toward evidence dilution and lost in the "
                    "middle attention effects."
                ),
            },
        ]
        summary = "Grounding errors worsen with long context length."

        mandate = synthesize_research_mandate(
            user_query="Can you research this?",
            chat_turns=chat_turns,
            conversation_summary=summary,
        )

        self.assertIsInstance(mandate, ResearchMandate)
        # Topic should resolve to the substantive problem from the dialogue
        self.assertNotEqual(mandate.topic, "Can you research this?")
        self.assertIn("longer contexts", mandate.topic.lower())
        self.assertTrue(len(mandate.known_facts) >= 1)
        self.assertIn("Grounding errors", mandate.known_facts[0])

    def test_constraint_inheritance_and_retention(self):
        chat_turns = [
            {
                "user": (
                    "Only focus on peer-reviewed papers published between "
                    "2024 and 2026."
                ),
                "assistant": "Understood, filtering for 2024-2026.",
            },
            {
                "user": "Limit research specifically to human clinical trials.",
                "assistant": "Restricting domain to clinical human studies.",
            },
        ]

        mandate = synthesize_research_mandate(
            user_query="Research solid state electrolyte degradation",
            chat_turns=chat_turns,
        )

        self.assertTrue(len(mandate.constraints) >= 1)
        constraint_text = " ".join(mandate.constraints).lower()
        self.assertTrue(
            "2024" in constraint_text or "human clinical" in constraint_text
        )

    def test_hypothesis_extraction_without_hallucination(self):
        chat_turns = [
            {
                "user": (
                    "What if LLZO garnet electrolytes are coated with ALD "
                    "alumina?"
                ),
                "assistant": (
                    "Atomic layer deposition of Al2O3 can suppress lithium "
                    "dendrites."
                ),
            }
        ]

        mandate = synthesize_research_mandate(
            user_query="Investigate this hypothesis",
            chat_turns=chat_turns,
        )

        self.assertTrue(len(mandate.hypotheses) >= 1)
        self.assertIn("llzo garnet", mandate.hypotheses[0].lower())
        self.assertIn("ald alumina", mandate.objective.lower())

    def test_five_turn_conversation_referential_resolution(self):
        # 5-turn conversation testing subject evolution
        chat_turns = [
            {
                "user": "We are investigating why answer quality dropped.",
                "assistant": "Could be retrieval failure or model generation.",
            },
            {
                "user": "Retrieval recall appears normal across test sets.",
                "assistant": "Then the bottleneck is downstream in generation.",
            },
            {
                "user": "The problem happens more often with longer contexts.",
                "assistant": "Longer contexts can cause attention dilution.",
            },
            {
                "user": "I suspect that evidence selection is degrading.",
                "assistant": "That is a specific testable hypothesis.",
            },
        ]
        summary = "Grounding degrades in large contexts despite high recall."

        # User gives meta-research command
        query = "Can we investigate this properly using the literature?"
        mandate = synthesize_research_mandate(
            user_query=query,
            chat_turns=chat_turns,
            conversation_summary=summary,
        )

        # Topic must not be the meta command
        self.assertNotEqual(mandate.topic, query)
        self.assertIn("evidence selection", mandate.topic.lower())
        self.assertEqual(mandate.scope, "peer-reviewed academic literature")
        self.assertTrue(len(mandate.hypotheses) >= 1)
        self.assertIn("evidence selection", mandate.hypotheses[0].lower())

    def test_cold_start_referential_query_marked_unresolved(self):
        # When a user gives a pronoun command with 0 context, mark as unresolved
        mandate = synthesize_research_mandate("Research this deeply")
        self.assertIn("unresolved", mandate.topic.lower())


if __name__ == "__main__":
    unittest.main()

