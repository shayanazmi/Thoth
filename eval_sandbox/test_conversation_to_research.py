"""
eval_sandbox/test_conversation_to_research.py
Evaluates:
1. Multi-turn dialogue flow transitioning into deep research.
2. Context inheritance when research is triggered with an anaphoric query ("Research this deeply").
3. Verification that search_node and initial state preserve previous discussion constraints.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.orchestrator import create_initial_state
from backend.pipeline import search_node


class TestConversationToResearchTransition(unittest.TestCase):

    def test_state_context_inheritance(self):
        """Verify that create_initial_state preserves previous turns and summary."""
        prior_turns = [
            {"turn": 1, "user_query": "Could Bihar attract semiconductor fabs?", "assistant_response": "Bihar faces power and water infrastructure constraints."},
            {"turn": 2, "user_query": "What are the specific water purity requirements for 28nm fabs?", "assistant_response": "Ultrapure water (UPW) requirements exceed 2-4 million gallons daily."}
        ]
        prior_summary = "Discussion on Bihar semiconductor feasibility focusing on UPW ultrapure water infrastructure."

        state = create_initial_state(
            topic="Research this deeply",
            initial_turns=prior_turns,
            initial_summary=prior_summary
        )

        self.assertEqual(len(state["chat_turns"]), 2)
        self.assertEqual(state["conversation_summary"], prior_summary)
        self.assertEqual(state["topic"], "Research this deeply")
        print("  ✓ Initial state successfully inherited prior turns and summary.")

    def test_search_node_anaphoric_resolution(self):
        """Verify that search_node resolves 'Research this deeply' to the active topic from prior turns."""
        prior_turns = [
            {"turn": 1, "user_query": "Could Bihar attract semiconductor fabs?", "assistant_response": "Bihar faces power and water infrastructure constraints."},
            {"turn": 2, "user_query": "What are the specific water purity requirements for 28nm fabs?", "assistant_response": "Ultrapure water (UPW) requirements exceed 2-4 million gallons daily."}
        ]
        prior_summary = "Discussion on Bihar semiconductor feasibility focusing on UPW ultrapure water infrastructure."

        state = create_initial_state(
            topic="Research this deeply",
            scrape_top_n=2,
            initial_turns=prior_turns,
            initial_summary=prior_summary
        )

        # Mock scholarly search to verify query resolution without network flakiness
        from unittest.mock import patch
        with patch("backend.pipeline.search_scholarly_sources") as mock_scholarly:
            mock_scholarly.return_value = []
            with patch("backend.pipeline.build_search_agent") as mock_agent:
                mock_runner = mock_agent.return_value
                mock_msg = type("MockMsg", (), {"content": "Found sources on UPW water requirements", "type": "ai"})()
                mock_runner.invoke.return_value = {"messages": [mock_msg]}

                update = search_node(state)
                # Verify that search_scholarly_sources was invoked with the resolved topic rather than bare 'Research this deeply'
                mock_scholarly.assert_called_once()
                called_query = mock_scholarly.call_args[0][0]
                self.assertIn("water purity requirements", called_query.lower())
                print(f"  ✓ search_node resolved anaphoric query to: '{called_query}'")


if __name__ == "__main__":
    unittest.main()
