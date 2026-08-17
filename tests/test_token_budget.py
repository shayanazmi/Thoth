import unittest
from unittest.mock import patch, MagicMock
from backend.pipeline import (
    count_tokens,
    truncate_text_to_tokens,
    fit_context_to_token_budget,
    stream_followup_turn
)
from langchain_core.runnables import RunnableSequence


class TestTokenBudget(unittest.TestCase):

    def test_count_tokens_and_truncate(self):
        sample_text = "The quick brown fox jumps over the lazy dog." * 50
        initial_tokens = count_tokens(sample_text)
        self.assertGreater(initial_tokens, 100)

        # Truncate to 30 tokens
        truncated = truncate_text_to_tokens(sample_text, 30)
        truncated_tokens = count_tokens(truncated)
        self.assertLessEqual(truncated_tokens, 30)

    def test_fit_context_drops_oldest_turns_first(self):
        topic = "Quantum Computing"
        context_block = "MIND MAP: Quantum gates and superposition." * 20
        summary = "Rolling summary of initial discovery." * 10
        user_query = "Explain qubit decoherence."

        # Create 5 historical turns with long responses
        chat_turns = [
            {"turn": 1, "user_query": "Turn 1 Q", "assistant_response": "Turn 1 Answer " * 50},
            {"turn": 2, "user_query": "Turn 2 Q", "assistant_response": "Turn 2 Answer " * 50},
            {"turn": 3, "user_query": "Turn 3 Q", "assistant_response": "Turn 3 Answer " * 50},
            {"turn": 4, "user_query": "Turn 4 Q", "assistant_response": "Turn 4 Answer " * 50},
            {"turn": 5, "user_query": "Turn 5 Q", "assistant_response": "Turn 5 Answer " * 50},
        ]

        # Fit into a strict budget of 500 tokens
        trimmed_ctx, trimmed_sum, recent_turns_text = fit_context_to_token_budget(
            topic=topic,
            context_block=context_block,
            summary=summary,
            chat_turns=chat_turns,
            user_query=user_query,
            max_tokens=500
        )

        # Total tokens of assembled prompt components must not exceed 500
        total_assembled = count_tokens(f"Topic: {topic}\nUser Query: {user_query}") + count_tokens(trimmed_ctx) + count_tokens(trimmed_sum) + count_tokens(recent_turns_text)
        self.assertLessEqual(total_assembled, 500)

        # Oldest turns (Turn 1, Turn 2) should have been dropped first
        self.assertNotIn("Turn 1 Answer", recent_turns_text)
        # Most recent turn (Turn 5) should be retained if it fits
        if recent_turns_text:
            self.assertIn("Turn 5 Answer", recent_turns_text)

    @patch.object(RunnableSequence, "invoke")
    def test_stream_followup_turn_respects_token_budget(self, mock_invoke):
        mock_invoke.return_value = '{"route": "LOCAL_QA", "reasoning": "Local QA"}'

        state = {
            "topic": "AI Agents",
            "mindmap": {"nodes": [{"id": "n1", "label": "Node 1", "type": "topic", "details": "Detail"}], "edges": []},
            "report": "Comprehensive synthesis report on AI agents." * 300,
            "cumulative_sources": [],
            "chat_turns": [
                {"turn": 1, "user_query": "Q1", "assistant_response": "A1 " * 100},
                {"turn": 2, "user_query": "Q2", "assistant_response": "A2 " * 100},
            ],
            "conversation_summary": "Summary of prior turns."
        }

        # Stream followup turn with max_context_tokens=1000
        events = {}
        for ev_name, ev_payload in stream_followup_turn(state, "What are multi-agent bottlenecks?", max_context_tokens=1000):
            events[ev_name] = ev_payload

        self.assertIn("answer", events)
        self.assertEqual(events["answer"]["route"], "LOCAL_QA")

    @patch("backend.pipeline.web_search")
    @patch("backend.pipeline.scrape_url")
    @patch.object(RunnableSequence, "invoke")
    def test_stream_followup_web_search_writes_to_vault(self, mock_invoke, mock_scrape, mock_web_search):
        mock_invoke.side_effect = [
            '{"route": "WEB_SEARCH", "reasoning": "New info needed", "search_query": "agent communication protocols"}',
            '{"nodes": [], "edges": []}',  # mindmap_updater
            'Agent communication protocols rely on standard JSON-RPC specifications.',  # answer
            '["What are multi-agent consensus protocols?", "How does latency affect agent orchestration?"]'  # follow_up_chain
        ]
        mock_web_search.invoke.return_value = "Search result with link https://arxiv.org/abs/2402.12345"
        mock_scrape.invoke.return_value = "Detailed paper content on agent protocols."

        state = {
            "topic": "AI Agents",
            "mindmap": {"nodes": [{"id": "n1", "label": "Node 1", "type": "topic", "details": "Detail"}], "edges": []},
            "report": "Initial synthesis report.",
            "cumulative_sources": [],
            "chat_turns": [],
            "conversation_summary": ""
        }

        events = {}
        for ev_name, ev_payload in stream_followup_turn(state, "What protocols do agents use?"):
            events[ev_name] = ev_payload

        self.assertIn("vault_update", events)
        self.assertTrue(len(events["vault_update"]["vault_notes"]) >= 1)
        self.assertIn("answer", events)
        self.assertEqual(events["answer"]["route"], "WEB_SEARCH")


if __name__ == "__main__":
    unittest.main()
