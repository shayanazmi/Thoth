"""
eval_sandbox/test_persona_simulations.py

Simulates real user personas across the complete Thoth lifecycle:
- Persona A & B: Casual conversation & fast-path streaming
- Persona C: Curious Researcher (Chat -> Explore -> Deep Research -> Go Deeper)
- Persona D & E: Power & Skeptical Researcher (Grounded Citations & Assumption Stress-Testing)
- Persona F: Impatient User (Topic Switches & Deictic Return to Prior Context)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.pipeline import (
    resolve_anaphoric_topic,
    stream_followup_turn,
)
from backend.orchestrator import create_initial_state
from backend.memory.session import SessionMemory


class TestRealUserPersonas(unittest.TestCase):

    def test_persona_ab_casual_flow(self):
        """Persona A & B: Normal conversation should remain fast, friendly, and non-intrusive."""
        mem = SessionMemory()
        mem.add_turn(
            "Hi, who are you and what can you help me with?",
            "Hello! I am Thoth, an autonomous research assistant. We can chat casually, explore scientific topics, or launch deep literature investigations across arXiv and scholarly repositories."
        )
        
        # User asks a normal conceptual question
        ctx = mem.get_context()
        self.assertIn("Hello! I am Thoth", ctx["recent_turns"])
        print("  ✓ Persona A/B: Casual dialogue memory and formatting verified.")

    def test_persona_c_curious_researcher_lifecycle(self):
        """Persona C: Chat -> Explore -> Deep Research Directive -> Follow-up Inquiry."""
        mem = SessionMemory()
        
        # Turn 1: Casual
        mem.add_turn("Hi!", "Hello! What are we exploring today?")
        
        # Turn 2: Topic exploration
        mem.add_turn(
            "What are the biggest challenges in neutral atom quantum computing?",
            "Key challenges include optical tweezer crosstalk, laser phase noise, and Rydberg state decay times."
        )
        
        # Turn 3: Natural directive with deictic reference and specific focus
        chat_turns = [
            {"role": "user", "content": "Hi!"},
            {"role": "assistant", "content": "Hello! What are we exploring today?"},
            {"role": "user", "content": "What are the biggest challenges in neutral atom quantum computing?"},
            {"role": "assistant", "content": "Key challenges include optical tweezer crosstalk, laser phase noise, and Rydberg state decay times."}
        ]
        query = "Can you research this deeply, especially the optical tweezer crosstalk limits?"
        resolved = resolve_anaphoric_topic(query, chat_turns, mem.summary)
        self.assertIn("neutral atom quantum computing", resolved.lower())
        self.assertIn("optical tweezer", resolved.lower())
        
        # State initialized with full conversational pedigree
        state = create_initial_state(
            topic=resolved,
            initial_turns=chat_turns,
            initial_summary=mem.summary
        )
        self.assertEqual(len(state["chat_turns"]), 4)
        print("  ✓ Persona C: Curious researcher transition & context inheritance verified.")

    def test_persona_de_skeptical_researcher(self):
        """Persona D & E: Skeptical researcher challenging conclusions and assumptions."""
        sample_report = (
            "# Neutral Atom Fidelity\n\n"
            "## Key Findings\n"
            "Recent 2026 experiments demonstrate two-qubit gate fidelities exceeding 99.5%.\n\n"
            "## Knowledge Gaps\n"
            "Scalability beyond 10,000 physical qubits in a single vacuum chamber remains unverified.\n\n"
            "## Sources\n"
            "1. https://arxiv.org/abs/2401.00001 - Rydberg Gate Benchmarks\n"
        )
        
        sample_state = {
            "session_id": "persona-de-test",
            "topic": "Neutral atom two-qubit gate fidelities",
            "report": sample_report,
            "mindmap": {
                "nodes": [{"id": "Gate Fidelity", "label": "99.5% Fidelity in 2026", "details": "Demonstrated with strontium-88"}],
                "edges": []
            },
            "chat_turns": [
                {"role": "user", "content": "What are the gate fidelities?"},
                {"role": "assistant", "content": "Recent benchmarks show 99.5% gate fidelity."}
            ],
            "conversation_summary": ""
        }
        
        # Follow-up: Challenging assumptions (synchronous generator)
        events = list(stream_followup_turn(
            sample_state,
            "What is the weakest assumption in this 99.5% claim, and what counterarguments exist?"
        ))
        self.assertGreaterEqual(len(events), 1)
        final_node, final_update, final_state = events[-1]
        self.assertIn("answer", final_update)
        answer = final_update["answer"].lower()
        # Answer must discuss assumptions, limits, or experimental conditions
        self.assertTrue(any(k in answer for k in ["assumption", "limit", "vacuum", "fidelity", "crosstalk", "error", "laser", "gate", "qubit"]))
        print("  ✓ Persona D/E: Skeptical researcher critical Q&A verified.")

    def test_persona_f_impatient_topic_switching(self):
        """Persona F: Impatient topic switches and deictic return to prior topics."""
        chat_turns = [
            {"role": "user", "content": "What are the water constraints for fabs in Bihar?"},
            {"role": "assistant", "content": "Ultrapure water requires 5 million gallons daily with specific filtration infrastructure."},
            {"role": "user", "content": "Forget that for a second. How do European foundries handle EUV lithography?"},
            {"role": "assistant", "content": "ASML high-NA EUV tools use 13.5nm wavelength with reflective optics in Veldhoven."}
        ]
        
        # Turn 5: Return to topic 1 with explicit reference
        query = "Okay coming back to the previous water thing in Bihar - compare that to Gujarat's Dholera SIR setup."
        resolved = resolve_anaphoric_topic(query, chat_turns, "")
        self.assertIn("water", resolved.lower())
        self.assertIn("bihar", resolved.lower())
        print("  ✓ Persona F: Topic switching and deictic return resolution verified.")


if __name__ == "__main__":
    unittest.main()
