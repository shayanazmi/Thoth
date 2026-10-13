import sys
import os
import unittest
import re
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.orchestrator import create_initial_state
from backend.pipeline import (
    search_node,
    resolve_anaphoric_topic,
    stream_followup_turn
)
from backend.memory.session import SessionMemory, count_tokens

class TestEndToEndUserJourney(unittest.TestCase):
    def test_anaphora_and_reference_resolution(self):
        turns = [
            {
                "turn": 1,
                "user_query": "What are the primary challenges for superconducting quantum computing?",
                "assistant_response": "1. High cryogenic cooling overhead at millikelvin temperatures.\n2. Planar nearest-neighbor connectivity constraints.\n3. Two-qubit gate cross-talk."
            }
        ]
        summary = "Discussion on superconducting quantum computer hardware bottlenecks."

        resolved_1 = resolve_anaphoric_topic("Research this deeply", chat_turns=turns, conv_summary=summary)
        self.assertEqual(resolved_1, "What are the primary challenges for superconducting quantum computing?")

        resolved_2 = resolve_anaphoric_topic("Go deeper on the second point", chat_turns=turns, conv_summary=summary)
        self.assertIn("nearest-neighbor connectivity", resolved_2.lower())

        resolved_3 = resolve_anaphoric_topic("Look into that", chat_turns=turns, conv_summary=summary)
        self.assertEqual(resolved_3, "What are the primary challenges for superconducting quantum computing?")

        resolved_4 = resolve_anaphoric_topic("Neutral atom Rydberg gate fidelity in 2026", chat_turns=turns, conv_summary=summary)
        self.assertEqual(resolved_4, "Neutral atom Rydberg gate fidelity in 2026")

        print("  ✓ All anaphora and reference resolution patterns verified.")

    def test_research_directive_classification_logic(self):
        def is_research_directive(text: str) -> bool:
            clean = text.strip().lower().rstrip("?!.,;:")

            if re.match(r'^(what|why|how|who|when|where|is|are|was|were)\s+(is\s+|are\s+)?(research|investigation)\b', clean):
                return False
            patterns = [
                r'^(do\s+|conduct\s+|run\s+|start\s+)?deep\s+research(\s+on|\s+into|\s+about)?',
                r'^(can\s+you\s+|please\s+|go\s+)?(research|investigate|dig\s+into|look\s+into|examine|explore)(\s+this|\s+that|\s+it|\s+the\s+above|\s+further|\s+properly|\s+deeply)?(\s+on|\s+into|\s+about)?',
                r'^(go\s+deeper|explore\s+deeply|explore\s+in\s+depth|dig\s+deeper)(\s+on|\s+into|\s+about|\s+this|\s+that|\s+it)?',
                r'^(find|gather)\s+(evidence|literature|papers|sources|data)\s+(for|on|about|regarding)',
                r'^(what\s+does\s+the\s+(research|literature|evidence)\s+say(\s+about)?)',
                r'^research:'
            ]
            return any(re.search(p, clean) for p in patterns)

        true_directives = [
            "Research this deeply",
            "Can you dig into this?",
            "Look into this",
            "Investigate this",
            "Go research this",
            "Find evidence for this",
            "Explore this properly",
            "What does the research say about quantum error correction?",
            "Go deeper on the cryogenic cooling bottleneck",
            "Deep research: semiconductor manufacturing in India"
        ]
        for td in true_directives:
            self.assertTrue(is_research_directive(td), f"Failed to detect valid directive: '{td}'")

        conversational_queries = [
            "Hi",
            "Hello there",
            "Why is research important in modern science?",
            "What is research methodology?",
            "How is research funded in universities?",
            "Explain semiconductors.",
            "Tell me something interesting about astronomy.",
            "Can you summarize what we just discussed?"
        ]
        for cq in conversational_queries:
            self.assertFalse(is_research_directive(cq), f"False positive triggered for conversational query: '{cq}'")

        print("  ✓ Research directive classification & false-positive guards verified.")

    def test_post_research_report_expansion_continuity(self):
        initial_state = {
            "topic": "Semiconductor UPW Requirements",
            "report": "# Initial Synthesis\nUltrapure water requirements are critical for 28nm lithography.",
            "mindmap": {"nodes": [{"id": "root", "label": "Semiconductor UPW"}], "edges": []},
            "cumulative_sources": [{"url": "https://example.com/upw", "title": "UPW Guide"}],
            "chat_turns": [],
            "conversation_summary": ""
        }

        with patch("backend.pipeline.router_chain") as mock_router, \
             patch("backend.pipeline.report_expander_chain") as mock_expander, \
             patch("backend.pipeline.follow_up_chain") as mock_fu:
            mock_router.invoke.return_value = '{"route": "REPORT_EXPANSION", "search_query": ""}'
            mock_expander.invoke.return_value = "## Expansion: Closed-Loop Water Recycling\nClosed-loop recycling recovers up to 85% of fab rinse water."
            mock_fu.invoke.return_value = '["Explore ultrafiltration membranes", "Compare capital cost per cubic meter"]'

            events = list(stream_followup_turn(
                current_state=initial_state,
                user_query="Add a section on closed-loop water recycling methods"
            ))

            complete_event = next((payload for ev, payload in events if ev == "followup_complete"), None)
            self.assertIsNotNone(complete_event)
            self.assertIn("Closed-Loop Water Recycling", complete_event["report"])
            self.assertIn("Initial Synthesis", complete_event["report"])
            self.assertEqual(len(complete_event["chat_turns"]), 1)

        print("  ✓ Post-research report expansion continuity verified.")

    def test_long_conversation_token_budget_stability(self):
        mem = SessionMemory(session_id="test_long_conv", initial_summary="Initial research on fusion reactors.")
        for i in range(1, 21):
            mem.add_turn(
                user_query=f"Turn {i} question on magnetic confinement field strength at step {i}?",
                assistant_response=f"Turn {i} response explaining toroidal field coils and plasma stability in detail for step {i}." * 5
            )

        context = mem.get_context()
        recent_turns_str = context["recent_turns"]
        summary_str = context["summary"]

        self.assertLessEqual(count_tokens(recent_turns_str), 4000)
        self.assertLessEqual(count_tokens(summary_str), 2500)
        self.assertGreater(len(mem.turns), 15)

        print(f"  ✓ 20-turn conversation successfully bounded: recent_turns={count_tokens(recent_turns_str)} tokens, total_turns={len(mem.turns)}.")

if __name__ == "__main__":
    unittest.main()
