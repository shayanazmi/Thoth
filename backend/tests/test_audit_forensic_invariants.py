import unittest
from unittest.mock import patch, MagicMock
import tempfile
import shutil
import json
import os
import threading
from fastapi.testclient import TestClient

from backend.main import app
from backend.conversation.brief import (
    ResearchBrief,
    BriefApprovalStatus,
    prepare_research_brief,
    approve_research_brief,
    update_research_brief,
    verify_brief_approval,
    ResearchTaskManager,
    _IN_MEMORY_BRIEFS,
)
from backend.orchestrator import create_initial_state, stream_research_pipeline


class TestAuditForensicInvariants(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_forensic.db")
        _IN_MEMORY_BRIEFS.clear()
        self.client = TestClient(app)

    def tearDown(self):
        _IN_MEMORY_BRIEFS.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("backend.api.routes_research.stream_research_pipeline")
    def test_client_spoofed_approval_payload_rejected_with_zero_research(self, mock_stream):
        """
        Invariant A: A client attempting to start research using approval fields
        supplied only in its request payload MUST be rejected with zero research calls.
        """
        spoofed_payload = {
            "topic": "Zero-Point Energy",
            "brief": {
                "brief_id": "malicious_spoofed_id",
                "topic": "Zero-Point Energy",
                "research_question": "Can we extract vacuum energy?",
                "approval_status": "APPROVED",
                "approved_version": 1,
                "version": 1,
                "approved_at": "2026-10-16T12:00:00Z"
            }
        }

        response = self.client.post("/api/research/stream", json=spoofed_payload)
        self.assertEqual(response.status_code, 200)

        lines = [line.replace("data: ", "") for line in response.text.strip().split("\n") if line.startswith("data: ")]
        events = [json.loads(line) for line in lines if line.strip()]

        barrier_events = [e for e in events if e.get("node") == "approval_barrier"]
        self.assertTrue(
            "does not exist in server storage" in barrier_events[0]["update"]["barrier_reason"] or
            "No research brief found or provided" in barrier_events[0]["update"]["barrier_reason"]
        )

        # Side-effect boundary verification: ZERO calls to pipeline
        mock_stream.assert_not_called()

    @patch("backend.api.routes_research.stream_research_pipeline")
    def test_client_claiming_approval_for_unapproved_server_brief_rejected(self, mock_stream):
        """
        Invariant A: If a brief exists on server as PENDING_APPROVAL,
        a client payload sending approval_status='APPROVED' MUST be rejected because
        authoritative server state takes absolute precedence.
        """
        brief = prepare_research_brief(
            topic="Room Temperature Superconductivity",
            db_path=self.db_path
        )
        self.assertEqual(brief.approval_status, BriefApprovalStatus.PENDING_APPROVAL)

        # Client attempts to spoof approval for the existing brief_id
        spoofed_payload = {
            "topic": "Room Temperature Superconductivity",
            "brief": {
                "brief_id": brief.brief_id,
                "approval_status": "APPROVED",
                "approved_version": 1,
                "version": 1
            }
        }

        response = self.client.post("/api/research/stream", json=spoofed_payload)
        lines = [line.replace("data: ", "") for line in response.text.strip().split("\n") if line.startswith("data: ")]
        events = [json.loads(line) for line in lines if line.strip()]

        barrier_events = [e for e in events if e.get("node") == "approval_barrier"]
        self.assertTrue(len(barrier_events) > 0)
        self.assertIn("Approval Barrier", barrier_events[0]["update"]["barrier_reason"])
        mock_stream.assert_not_called()

    @patch("backend.api.routes_research.stream_research_pipeline")
    def test_stale_expected_version_rejected_with_zero_research(self, mock_stream):
        """
        Invariant B: If a client requests execution of version 1, but the server brief
        has advanced to version 2 (even if version 2 was approved), the request must be
        rejected due to version mismatch.
        """
        brief = prepare_research_brief(topic="Quantum Annealing", db_path=self.db_path)
        approve_research_brief(brief.brief_id, 1, db_path=self.db_path)

        # Substantive edit produces version 2
        update_research_brief(brief.brief_id, {"search_scope": "Updated scope"}, db_path=self.db_path)
        # Approve version 2
        approve_research_brief(brief.brief_id, 2, db_path=self.db_path)

        # Client sends request explicitly asking for version 1
        request_payload = {
            "topic": "Quantum Annealing",
            "brief_id": brief.brief_id,
            "version": 1
        }

        response = self.client.post("/api/research/stream", json=request_payload)
        lines = [line.replace("data: ", "") for line in response.text.strip().split("\n") if line.startswith("data: ")]
        events = [json.loads(line) for line in lines if line.strip()]

        barrier_events = [e for e in events if e.get("node") == "approval_barrier"]
        self.assertTrue(len(barrier_events) > 0)
        self.assertIn("Version Mismatch", barrier_events[0]["update"]["barrier_reason"])
        mock_stream.assert_not_called()

    def test_task_manager_single_process_concurrency_deduplication(self):
        """
        Invariant E: Within a single process, ResearchTaskManager strictly prevents
        duplicate concurrent execution runs for the same brief_id and version.
        """
        from backend.memory.db import init_db
        init_db(self.db_path)
        brief = prepare_research_brief(
            topic="Quantum Computing",
            research_question="What are recent quantum error correction breakthroughs?",
            db_path=self.db_path,
        )
        approve_research_brief(brief.brief_id, version=1, db_path=self.db_path)

        tm = ResearchTaskManager(db_path=self.db_path)
        ok1, cancel1, msg1 = tm.register_task("task_1", brief.brief_id, 1)
        self.assertTrue(ok1)
        self.assertIsNotNone(cancel1)

        # Simultaneous second attempt while task_1 is active
        ok2, cancel2, msg2 = tm.register_task("task_2", brief.brief_id, 1)
        self.assertFalse(ok2)
        self.assertIsNone(cancel2)
        self.assertTrue("already active" in msg2.lower() or "already running" in msg2.lower())

        # When task 1 fails, an intentional retry CAN be registered
        tm.complete_task("task_1", "FAILED", error_code="ERR_TEST", error_summary="Simulated test failure")
        ok3, cancel3, msg3 = tm.register_task("task_3", brief.brief_id, 1)
        self.assertTrue(ok3)

        # After task 3 completes, accidental reruns are blocked by policy
        tm.complete_task("task_3", "COMPLETED")
        ok4, cancel4, msg4 = tm.register_task("task_4", brief.brief_id, 1)
        self.assertFalse(ok4)
        self.assertIn("already completed", msg4.lower())

    def test_cooperative_cancellation_semantics(self):
        """
        Invariant F: Cancellation is cooperative and halts execution before node execution.
        """
        cancel_event = threading.Event()
        cancel_event.set()  # Cancelled before start

        gen = stream_research_pipeline(
            topic="Cancelled Test",
            cancel_event=cancel_event
        )

        events = list(gen)
        self.assertEqual(len(events), 1)
        node_name, update, state = events[0]
        self.assertEqual(node_name, "cancelled")
        self.assertTrue(state.get("cancelled"))

    def test_mandate_propagation_and_unresolved_questions_limitation(self):
        """
        Invariant C & Audit Verification: Verify propagation of thinker context,
        hypotheses, and selection criteria into initial state, and verify current status
        of unresolved_questions.
        """
        brief_data = {
            "brief_id": "test_brief_1",
            "topic": "Epigenetic Clocks",
            "research_question": "How accurate are DNA methylation clocks in non-model organisms?",
            "thinker_context": {
                "thinker_name": "Aristotle",
                "archetype": "First-Principles Empiricist",
                "description": "Examine material and formal causes."
            },
            "hypotheses": ["Horvath clock correlates across mammalia."],
            "selection_criteria": ["Peer-reviewed datasets only."],
            "unresolved_questions": ["Tissue-specific vs whole-blood divergence?"]
        }

        state = create_initial_state(
            topic="Epigenetic Clocks",
            brief=brief_data
        )

        self.assertEqual(state["thinker_context"]["thinker_name"], "Aristotle")
        self.assertEqual(state["hypotheses"], ["Horvath clock correlates across mammalia."])
        self.assertEqual(state["selection_criteria"], ["Peer-reviewed datasets only."])
        # Note limitation: unresolved_questions is stored in state["brief"] but not at top-level state
        self.assertIn("unresolved_questions", state["brief"])
        self.assertEqual(state["brief"]["unresolved_questions"], ["Tissue-specific vs whole-blood divergence?"])


if __name__ == "__main__":
    unittest.main()
