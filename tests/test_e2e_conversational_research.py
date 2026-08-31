"""
End-to-End Integration Test Suite for Conversational Brainstorming
to Deep Research Orchestration, Living Report Updates, and Memory.
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from web_server import app
from backend.conversation import (
    EscalationState,
    detect_escalation_intent,
    synthesize_research_mandate,
    evaluate_clarification_need,
)
from backend.reports import patch_report_section


class TestE2EConversationalResearchFlow(unittest.TestCase):
    """Tests the full user journey from brainstorming to deep research."""

    def setUp(self):
        self.client = TestClient(app)

    def test_api_detect_escalation_endpoint(self):
        # 1. Normal casual question
        resp = self.client.post(
            "/api/conversation/escalate",
            json={"query": "Hello Thoth, what can you do?"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["state"], "CHAT")
        self.assertFalse(data["prompt_user"])

        # 2. Explicit research command
        resp_exp = self.client.post(
            "/api/conversation/escalate",
            json={"query": "Research this deeply with recent papers"},
        )
        self.assertEqual(resp_exp.status_code, 200)
        data_exp = resp_exp.json()
        self.assertEqual(data_exp["state"], "RESEARCH_READY")

    def test_api_check_clarification_endpoint(self):
        # Broad keyword query
        resp = self.client.post(
            "/api/research/clarify",
            json={"topic": "Batteries"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["clarification"]["needs_clarification"])
        self.assertGreaterEqual(len(data["clarification"]["options"]), 2)

        # Specific query
        resp_spec = self.client.post(
            "/api/research/clarify",
            json={
                "topic": (
                    "2026 CRISPR Prime Editing Off-Target Fidelity in Human "
                    "T-Cells"
                )
            },
        )
        self.assertEqual(resp_spec.status_code, 200)
        data_spec = resp_spec.json()
        self.assertFalse(data_spec["clarification"]["needs_clarification"])

    def test_chat_to_mandate_to_research_pipeline_integration(self):
        # Simulate multi-turn brainstorming session
        chat_turns = [
            {
                "user": "We are exploring LLZO solid-state electrolyte interfaces.",
                "assistant": "Interfacial resistance and lithium dendrites are main bottlenecks.",
            },
            {
                "user": "Focus only on ALD alumina coating studies from 2024 to 2026.",
                "assistant": "Restricting focus to recent ALD Al2O3 coatings.",
            },
        ]
        summary = "ALD alumina coating improves wetting and blocks dendrites."

        # User triggers research
        trigger_query = "Please do a deep dive and check the literature."
        escalation = detect_escalation_intent(
            user_query=trigger_query,
            chat_turns=chat_turns,
            conversation_summary=summary,
        )
        self.assertEqual(escalation["state"], EscalationState.RESEARCH_READY)

        # Synthesize research mandate
        mandate = synthesize_research_mandate(
            user_query=trigger_query,
            chat_turns=chat_turns,
            conversation_summary=summary,
        )
        self.assertIsInstance(mandate.objective, str)
        self.assertTrue(len(mandate.constraints) >= 1)
        self.assertTrue(len(mandate.known_facts) >= 1)

        # Check clarification gate (should bypass because chat provided constraints)
        clarification = evaluate_clarification_need(mandate)
        self.assertFalse(clarification.needs_clarification)

    def test_living_report_patch_preserves_unrelated_sections(self):
        initial_report = """# Research Synthesis

## Section 1: Introduction
Foundational context.

## Section 2: Key Findings
Old findings.

## Section 3: Open Challenges
Unresolved questions.
"""
        new_section_2 = """## Section 2: Key Findings
Updated 2026 findings with primary source evidence [[src-paper_1]]."""

        updated_report, was_replaced = patch_report_section(
            original_markdown=initial_report,
            section_title="Section 2: Key Findings",
            new_content=new_section_2,
        )

        self.assertTrue(was_replaced)
        self.assertIn("Updated 2026 findings", updated_report)
        self.assertIn("## Section 1: Introduction", updated_report)
        self.assertIn("## Section 3: Open Challenges", updated_report)


if __name__ == "__main__":
    unittest.main()
