import unittest
from backend.conversation.resolver import (
    ResolvedQuery,
    reformulate_conversational_query,
    is_continuation_directive,
    detect_topic_correction,
    is_ambiguous_referential_query,
)
from backend.conversation.mandate import synthesize_research_mandate
from backend.pipeline import resolve_anaphoric_topic, route_followup_intent

class TestHybridConversationalQueryResolver(unittest.TestCase):
    def test_deterministic_resolution_inherits_canonical_topic(self):
        canonical_topic = "LLM security and guardrails"
        commands = [
            "Go explore",
            "go explore.",
            "Continue",
            "continue with that",
            "Go ahead",
            "proceed",
            "carry on",
        ]
        for cmd in commands:
            self.assertTrue(
                is_continuation_directive(cmd),
                f"Failed to recognize continuation directive: '{cmd}'",
            )
            res = reformulate_conversational_query(
                user_query=cmd,
                canonical_topic=canonical_topic,
                chat_turns=[{"user": canonical_topic, "assistant": "Sure"}],
                use_llm=False,
            )
            self.assertEqual(res.canonical_topic, canonical_topic)
            self.assertIn("LLM security", res.standalone_query)
            self.assertNotIn("reinforcement learning", res.standalone_query.lower())
            self.assertEqual(res.resolution_type, "DETERMINISTIC_CONTINUATION")

    def test_contextual_query_reformulation_preserves_scope(self):
        canonical_topic = "LLM security and guardrails"
        followup = "Explore key breakthroughs in this area."

        self.assertTrue(is_ambiguous_referential_query(followup))

        res = reformulate_conversational_query(
            user_query=followup,
            canonical_topic=canonical_topic,
            chat_turns=[
                {
                    "user": "I want to research LLM security and guardrails.",
                    "assistant": "Let's review prompt injection and jailbreak defenses.",
                }
            ],
            use_llm=False,
        )

        self.assertEqual(res.canonical_topic, canonical_topic)
        self.assertIn("LLM security and guardrails", res.standalone_query)
        self.assertIn("breakthroughs", res.standalone_query.lower())
        self.assertEqual(res.resolution_type, "REFORMULATED")

    def test_explicit_topic_correction_overrides_stale_topic(self):
        correction_query = (
            "You misunderstood me. I mean prompt injection, jailbreak resistance, "
            "adversarial robustness, and defensive evaluations of LLM guardrails. Continue with that."
        )

        correction = detect_topic_correction(correction_query)
        self.assertIsNotNone(correction)
        corrected_topic, _ = correction
        self.assertIn("prompt injection", corrected_topic.lower())

        res = reformulate_conversational_query(
            user_query=correction_query,
            canonical_topic="Scientific forecasting and Go-Explore",
            chat_turns=[
                {"user": "Go explore", "assistant": "Here is Go-Explore RL"}
            ],
            use_llm=False,
        )

        self.assertTrue(res.is_correction)
        self.assertEqual(res.resolution_type, "TOPIC_CORRECTION")
        self.assertIn("prompt injection", res.canonical_topic.lower())
        self.assertNotIn("scientific forecasting", res.canonical_topic.lower())

    def test_clarification_prompted_when_uncertainty_remains(self):
        res = reformulate_conversational_query(
            user_query="Explore key breakthroughs in this area.",
            canonical_topic="",
            chat_turns=[],
            conversation_summary="",
            use_llm=False,
        )

        self.assertTrue(res.needs_clarification)
        self.assertEqual(res.resolution_type, "CLARIFICATION_NEEDED")
        self.assertTrue(len(res.clarification_prompt) > 0)
        self.assertGreaterEqual(len(res.clarification_options), 2)

    def test_strict_separation_of_responsibilities(self):
        canonical_topic = "Quantum error correction surface codes"
        followup = "What are the latest 2026 threshold benchmarks?"

        res = reformulate_conversational_query(
            user_query=followup,
            canonical_topic=canonical_topic,
            chat_turns=[],
            use_llm=False,
        )

        self.assertEqual(res.canonical_topic, canonical_topic)
        self.assertIn(canonical_topic, res.standalone_query)
        self.assertIn("threshold benchmarks", res.standalone_query)
        self.assertFalse(res.is_correction)

    def test_resolve_anaphoric_topic_integration(self):
        resolved = resolve_anaphoric_topic(
            "Go explore.",
            chat_turns=[
                {"user": "Research on LLM security guardrails", "assistant": "Okay."}
            ]
        )
        self.assertEqual(resolved, "Research on LLM security guardrails")

    def test_mandate_synthesis_with_continuation_directive(self):
        mandate = synthesize_research_mandate(
            user_query="Go explore",
            chat_turns=[
                {"user": "We are studying LLM prompt injection defenses.", "assistant": "Understood."}
            ]
        )
        self.assertIn("LLM prompt injection defenses", mandate.topic)
        self.assertNotEqual(mandate.topic, "Go explore")

if __name__ == "__main__":
    unittest.main()
