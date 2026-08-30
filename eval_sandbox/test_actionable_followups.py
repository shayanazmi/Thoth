"""
eval_sandbox/test_actionable_followups.py
Evaluates:
1. Generation of forward-thinking, actionable follow-up suggestions from synthesized reports.
2. Verification that suggestions are non-generic and actionable.
"""

import sys
import os
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agents import follow_up_chain, strip_chain_of_thought, safe_extract_json


class TestActionableFollowups(unittest.TestCase):

    def test_forward_thinking_followups(self):
        topic = "Superconducting Transmon Qubits vs Neutral Atom Tweezer Arrays"
        report = """# Comparative Quantum Architecture Analysis
Superconducting transmon circuits demonstrate high gate fidelity (>99.9% 1-qubit) but suffer from heavy cryogenic overhead and planar nearest-neighbor connectivity limits.
Neutral atom tweezer arrays offer dynamic connectivity and long coherence times (T2 > 1s) but face lower 2-qubit Rydberg gate speeds (100kHz-1MHz)."""
        recent_context = "User asked about scalability trade-offs for 10,000 logical qubits."

        raw_output = follow_up_chain.invoke({
            "topic": topic,
            "report": report,
            "recent_context": recent_context
        })
        cleaned = strip_chain_of_thought(raw_output)
        pills = safe_extract_json(cleaned, default=[])

        self.assertIsInstance(pills, list)
        self.assertGreaterEqual(len(pills), 1)

        # Check for non-generic questions
        for pill in pills:
            self.assertNotIn("would you like to know more", pill.lower())
            self.assertNotIn("can you tell me", pill.lower())
            self.assertGreater(len(pill.strip()), 15)

        print(f"  ✓ Successfully generated {len(pills)} actionable follow-up pills:")
        for idx, p in enumerate(pills, 1):
            print(f"    [{idx}] {p}")


if __name__ == "__main__":
    unittest.main()
