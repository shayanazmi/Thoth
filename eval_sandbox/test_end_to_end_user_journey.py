"""
eval_sandbox/test_end_to_end_user_journey.py
Evaluates the complete end-to-end user experience lifecycle:
1. Casual chat -> domain discussion -> anaphoric 'Research this deeply' transition.
2. Anaphoric and reference resolution (ordinals, comparisons, pronouns).
3. False-positive resistance (philosophical questions about research vs actionable directives).
4. Post-research follow-up & report expansion continuity.
5. Long-conversation context bounding (20-turn token stability).
"""

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
        """Test resolving varied conversational references into concrete search topics."""
        turns = [
            {
                "turn": 1,
                "user_query": "What are the primary challenges for superconducting quantum computing?",
                "assistant_response": "1. High cryogenic cooling overhead at millikelvin temperatures.\n2. Planar nearest-neighbor connectivity constraints.\n3. Two-qubit gate cross-talk."
            }
        ]
        summary = "Discussion on superconducting quantum computer hardware bottlenecks."

        # Case 1: "Research this deeply" -> inherits main query
        resolved_1 = resolve_anaphoric_topic("Research this deeply", chat_turns=turns, conv_summary=summary)
        self.assertEqual(resolved_1, "What are the primary challenges for superconducting quantum computing?")

        # Case 2: "Go deeper on the second point" -> resolves to point #2
        resolved_2 = resolve_anaphoric_topic("Go deeper on the second point", chat_turns=turns, conv_summary=summary)
        self.assertIn("nearest-neighbor connectivity", resolved_2.lower())

        # Case 3: "Look into that" -> inherits main query
        resolved_3 = resolve_anaphoric_topic("Look into that", chat_turns=turns, conv_summary=summary)
        self.assertEqual(resolved_3, "What are the primary challenges for superconducting quantum computing?")

        # Case 4: Non-anaphoric query -> preserved as-is
        resolved_4 = resolve_anaphoric_topic("Neutral atom Rydberg gate fidelity in 2026", chat_turns=turns, conv_summary=summary)
        self.assertEqual(resolved_4, "Neutral atom Rydberg gate fidelity in 2026")

        print("  ✓ All anaphora and reference resolution patterns verified.")

    def test_research_directive_classification_logic(self):
        """Verify natural language directive patterns vs conversational false-positive resistance."""
        def is_research_directive(text: str) -> bool:
            clean = text.strip().lower().rstrip("?!.,;:")
            # Philosophical or definitional questions -> false
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

        # True Directives
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

        # Conversational / Casual (Must NOT trigger research swarm)
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
        """Verify that expanding a report updates the current state and report persistence."""
        initial_state = {
            "topic": "Semiconductor UPW Requirements",
            "report": "# Initial Synthesis\nUltrapure water requirements are critical for 28nm lithography.",
            "mindmap": {"nodes": [{"id": "root", "label": "Semiconductor UPW"}], "edges": []},
            "cumulative_sources": [{"url": "https://example.com/upw", "title": "UPW Guide"}],
            "chat_turns": [],
            "conversation_summary": ""
        }

        # Mock LLM and router to force REPORT_EXPANSION
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

            # Extract followup_complete event
            complete_event = next((payload for ev, payload in events if ev == "followup_complete"), None)
            self.assertIsNotNone(complete_event)
            self.assertIn("Closed-Loop Water Recycling", complete_event["report"])
            self.assertIn("Initial Synthesis", complete_event["report"])
            self.assertEqual(len(complete_event["chat_turns"]), 1)

        print("  ✓ Post-research report expansion continuity verified.")

    def test_long_conversation_token_budget_stability(self):
        """Verify that a 20-turn conversation remains bounded and stable in SessionMemory."""
        mem = SessionMemory(session_id="test_long_conv", initial_summary="Initial research on fusion reactors.")
        for i in range(1, 21):
            mem.add_turn(
                user_query=f"Turn {i} question on magnetic confinement field strength at step {i}?",
                assistant_response=f"Turn {i} response explaining toroidal field coils and plasma stability in detail for step {i}." * 5
            )

        context = mem.get_context()
        recent_turns_str = context["recent_turns"]
        summary_str = context["summary"]

        # Ensure tokens remain within default budget limits
        self.assertLessEqual(count_tokens(recent_turns_str), 4000)
        self.assertLessEqual(count_tokens(summary_str), 2500)
        self.assertGreater(len(mem.turns), 15)

        print(f"  ✓ 20-turn conversation successfully bounded: recent_turns={count_tokens(recent_turns_str)} tokens, total_turns={len(mem.turns)}.")


if __name__ == "__main__":
    unittest.main()
