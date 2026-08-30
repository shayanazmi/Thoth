"""
eval_sandbox/test_adversarial_continuity.py
Adversarial Validation Suite for Thoth:
1. Multi-Turn Sequential Report Expansion: Verifies cumulative preservation across multiple expansion and QA turns.
2. Topic Switching & Negative Context Isolation: Verifies that switching topics isolates new research from prior topic contamination.
3. Conversational Transition Sanitization: Verifies that transition prefaces and conversational fillers are cleanly stripped for academic APIs.
"""

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.pipeline import (
    stream_followup_turn,
    resolve_anaphoric_topic
)
from backend.scholarly import _sanitize_academic_query


class TestAdversarialContinuity(unittest.TestCase):

    def test_multi_turn_sequential_report_expansions(self):
        """Test adding 3 sequential expansions interspersed with Q&A turns."""
        state = {
            "topic": "Quantum Computing Scaling Architectures",
            "report": "# Initial Synthesis\nQuantum computing faces physical error scaling limits.",
            "mindmap": {"nodes": [{"id": "root", "label": "QC Scaling"}], "edges": []},
            "cumulative_sources": [],
            "chat_turns": [],
            "conversation_summary": ""
        }

        # Sequence of turns
        turns = [
            ("REPORT_EXPANSION", "Add Section A: Cryogenic Cooling Systems", "## Section A: Cryogenic Cooling\nDilution refrigerators maintain 10mK operating temperatures."),
            ("LOCAL_QA", "What is the operating temperature in Section A?", "The operating temperature is 10mK as noted in Section A."),
            ("REPORT_EXPANSION", "Add Section B: Neutral Atom Optical Tweezers", "## Section B: Neutral Atoms\nOptical tweezer arrays scale to 1,000+ physical qubits."),
            ("REPORT_EXPANSION", "Add Section C: 2026 Threshold Benchmarks", "## Section C: 2026 Benchmarks\nSurface code error thresholds achieved 0.5% physical error rates.")
        ]

        for route, user_q, canned_resp in turns:
            with patch("backend.pipeline.router_chain") as mock_router, \
                 patch("backend.pipeline.report_expander_chain") as mock_expander, \
                 patch("backend.pipeline.mindmap_qa_chain") as mock_qa, \
                 patch("backend.pipeline.follow_up_chain") as mock_fu:
                mock_router.invoke.return_value = f'{{"route": "{route}", "search_query": ""}}'
                mock_expander.invoke.return_value = canned_resp
                mock_qa.invoke.return_value = canned_resp
                mock_fu.invoke.return_value = '["Question 1", "Question 2"]'

                events = list(stream_followup_turn(current_state=state, user_query=user_q))
                comp = next((p for ev, p in events if ev == "followup_complete"), None)
                self.assertIsNotNone(comp)
                state["report"] = comp["report"]
                state["chat_turns"] = comp["chat_turns"]

        # Assert all three sections survive cumulatively in state["report"]
        self.assertIn("Section A: Cryogenic Cooling", state["report"])
        self.assertIn("Section B: Neutral Atoms", state["report"])
        self.assertIn("Section C: 2026 Benchmarks", state["report"])
        self.assertIn("Initial Synthesis", state["report"])
        self.assertEqual(len(state["chat_turns"]), 4)
        print("  ✓ Multi-turn sequential report expansion continuity verified (3 sections + QA turn preserved).")

    def test_topic_switching_isolation(self):
        """Verify that switching topics isolates the new research query from prior topic contamination."""
        turns = [
            {"turn": 1, "user_query": "Could Bihar attract semiconductor fabs?", "assistant_response": "Bihar has power and water constraints."},
            {"turn": 2, "user_query": "What about ultrapure water in India?", "assistant_response": "UPW requirements in India face logistical hurdles."},
            {"turn": 3, "user_query": "Now let's switch topics completely. How do European photonics foundries handle extreme ultraviolet lithography?", "assistant_response": "European photonics centers like IMEC utilize high-NA EUV."}
        ]
        summary = "Discussion on Bihar and Indian semiconductor infrastructure."

        resolved = resolve_anaphoric_topic("Research this deeply", chat_turns=turns, conv_summary=summary)
        # Should pick the latest turn (European photonics), NOT Bihar or India
        self.assertIn("European photonics foundries", resolved)
        self.assertNotIn("Bihar", resolved)
        print(f"  ✓ Topic switching correctly resolved latest focus: '{resolved}'")

    def test_conversational_preface_sanitization(self):
        """Verify that conversational transitions and fillers are cleanly removed for academic search APIs."""
        raw_queries = [
            ("Now let's switch gears completely. What are the latest 2026 benchmarks for LLM sparse autoencoders?", "What are the latest 2026 benchmarks for LLM sparse autoencoders"),
            ("Can you please research the dielectric breakdown voltages of hexagonal boron nitride?", "the dielectric breakdown voltages of hexagonal boron nitride"),
            ("On another note, how does quantum repeater fidelity scale with distance?", "how does quantum repeater fidelity scale with distance"),
            ("By the way, explain perovskite solar cell stability metrics.", "perovskite solar cell stability metrics")
        ]

        for raw, expected_substr in raw_queries:
            sanitized = _sanitize_academic_query(raw)
            self.assertIn(expected_substr.lower(), sanitized.lower())
            self.assertNotIn("switch gears", sanitized.lower())
            self.assertNotIn("can you please research", sanitized.lower())
            self.assertNotIn("on another note", sanitized.lower())
            self.assertNotIn("by the way", sanitized.lower())

        print("  ✓ Conversational prefaces and transition fillers successfully sanitized.")


if __name__ == "__main__":
    unittest.main()
