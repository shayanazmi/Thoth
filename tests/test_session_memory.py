import unittest
from unittest.mock import MagicMock
from backend.memory.session import (
    SessionMemory,
    DEFAULT_TOKEN_BUDGET,
    count_tokens,
    truncate_text_to_tokens,
)


class TestSessionMemory(unittest.TestCase):

    def test_count_and_truncate_tokens(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20
        total_tokens = count_tokens(text)
        self.assertTrue(total_tokens > 20)

        truncated = truncate_text_to_tokens(text, 10)
        truncated_tokens = count_tokens(truncated)
        self.assertLessEqual(truncated_tokens, 10)

    def test_session_add_turns(self):
        session = SessionMemory(session_id="test_s1", system_prompt="You are Thoth.")
        session.add_turn("What is quantum entanglement?", "It is a physical phenomenon where particles remain connected.")
        session.add_turn("Can it be used for FTL communication?", "No, the no-communication theorem prohibits faster-than-light signaling.")

        self.assertEqual(len(session.turns), 2)
        self.assertEqual(session.turns[0]["turn"], 1)
        self.assertEqual(session.turns[1]["turn"], 2)

    def test_get_context_token_budget_slicing(self):
        session = SessionMemory(
            session_id="test_s2",
            system_prompt="System instructions for research assistant.",
            initial_summary="Prior discussion on quantum error mitigation."
        )

        # Add 5 conversational turns
        for i in range(1, 6):
            session.add_turn(f"User Question {i} with some detailed context text.", f"Assistant Answer {i} detailing findings and analysis.")

        custom_budget = {
            "system": 50,
            "retrieved_notes": 100,
            "summary": 50,
            "recent_turns": 40,  # Small budget will force dropping older turns
            "headroom": 50,
        }

        retrieved_notes_raw = "--- Note [topic-quantum]: Quantum bits store superposition states." * 10
        ctx = session.get_context(token_budget=custom_budget, retrieved_notes_text=retrieved_notes_raw)

        self.assertIn("system", ctx)
        self.assertIn("retrieved_notes", ctx)
        self.assertIn("summary", ctx)
        self.assertIn("recent_turns", ctx)
        self.assertIn("formatted_prompt_context", ctx)

        # Confirm recent turns kept the newest turn (Turn 5) and dropped older turns (Turn 1)
        self.assertIn("User Question 5", ctx["recent_turns"])
        self.assertNotIn("User Question 1", ctx["recent_turns"])

        # Confirm slices don't exceed their assigned caps
        self.assertLessEqual(count_tokens(ctx["system"]), 50)
        self.assertLessEqual(count_tokens(ctx["retrieved_notes"]), 100)
        self.assertLessEqual(count_tokens(ctx["summary"]), 50)
        self.assertLessEqual(count_tokens(ctx["recent_turns"]), 40)

    def test_compress_history(self):
        mock_summarizer = MagicMock()
        mock_summarizer.invoke.return_value = "Compressed summary: Explored quantum superposition and teleportation."

        session = SessionMemory(initial_summary="Prior quantum basics.")
        session.add_turn("Q1", "A1")
        session.add_turn("Q2", "A2")

        new_summary = session.compress_history(summarizer_chain=mock_summarizer)
        self.assertEqual(new_summary, "Compressed summary: Explored quantum superposition and teleportation.")
        self.assertEqual(session.summary, "Compressed summary: Explored quantum superposition and teleportation.")
        mock_summarizer.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
