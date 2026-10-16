import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from backend.main import app
from backend.conversation.brief import (
    BriefApprovalStatus,
    ResearchBrief,
    prepare_research_brief,
    update_research_brief,
    approve_research_brief,
    get_research_brief,
    verify_brief_approval,
    task_manager,
    clear_briefs_cache,
)
from backend.conversation.mandate import ResearchMandate
from backend.memory.db import init_db
from backend.orchestrator import create_initial_state, stream_research_pipeline
from backend.pipeline import writer_node


class TestResearchMandateAndGenuineApproval(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="thoth_brief_test_")
        self.db_path = os.path.join(self.test_dir, "test_store.db")
        init_db(self.db_path)

        # Patch DEFAULT_DB_PATH in db and brief modules to isolate storage
        self.db_patcher1 = patch("backend.memory.db.DEFAULT_DB_PATH", self.db_path)
        self.db_patcher2 = patch("backend.conversation.brief.DEFAULT_DB_PATH", self.db_path)
        self.db_patcher1.start()
        self.db_patcher2.start()

        clear_briefs_cache()
        task_manager.clear()
        self.client = TestClient(app)

    def tearDown(self):
        clear_briefs_cache()
        task_manager.clear()
        self.db_patcher2.stop()
        self.db_patcher1.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Ordinary conversation does not launch formal research
    # -------------------------------------------------------------------------
    @patch("backend.api.routes_research.stream_research_pipeline")
    def test_ordinary_conversation_does_not_launch_formal_research(self, mock_stream_pipeline):
        """Conversational greetings and casual queries must route to fast-chat without launching research."""
        # Casual query in stream endpoint
        resp = self.client.post(
            "/api/research/stream",
            json={
                "topic": "Hello Thoth, how are you today?",
                "mode": "fast_chat",
                "chat_turns": [],
            },
        )
        self.assertEqual(resp.status_code, 200)
        lines = resp.text.strip().split("\n")
        events = [json.loads(line.replace("data: ", "")) for line in lines if line.startswith("data: ")]

        nodes = [e.get("node") for e in events]
        self.assertIn("direct_chat", nodes)
        self.assertNotIn("search", nodes)
        self.assertNotIn("writer", nodes)
        # Verify research pipeline worker was never called
        mock_stream_pipeline.assert_not_called()

        # Chat escalation check stays in CHAT state
        esc_resp = self.client.post(
            "/api/conversation/escalate",
            json={"query": "What is the capital of France?"},
        )
        self.assertEqual(esc_resp.status_code, 200)
        self.assertEqual(esc_resp.json()["state"], "CHAT")
        self.assertFalse(esc_resp.json()["prompt_user"])

    # -------------------------------------------------------------------------
    # 2. Preparing a brief does not launch formal research
    # -------------------------------------------------------------------------
    @patch("backend.api.routes_research.stream_research_pipeline")
    def test_preparing_brief_does_not_launch_formal_research(self, mock_stream_pipeline):
        """Preparing or refining a Research Brief creates persisted brief in PENDING_APPROVAL without launching research."""
        payload = {
            "topic": "Fluxonium Qubit Coherence Limits in 3D Cavities",
            "chat_turns": [
                {"user": "Fluxonium qubits offer large anharmonicity.", "assistant": "Yes, especially in high-impedance regimes."},
                {"user": "Focus on dielectric surface loss and 1/f flux noise.", "assistant": "Restricting focus to dielectric losses."},
            ],
            "conversation_summary": "Investigating coherence times of fluxonium qubits.",
            "hypothesis": "Dielectric surface loss dominates over radiative decay at 50 mK.",
            "selection_criteria": ["Experimental papers only", "Published 2023-2026"],
        }

        resp = self.client.post("/api/research/brief/prepare", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        brief = data["brief"]

        self.assertIsNotNone(brief["brief_id"])
        self.assertEqual(brief["version"], 1)
        self.assertEqual(brief["approval_status"], BriefApprovalStatus.PENDING_APPROVAL)
        self.assertFalse(brief.get("is_confirmed_by_user", False))
        self.assertIn("Fluxonium", brief["topic"])
        self.assertTrue(len(brief["objectives"]) >= 1)
        self.assertTrue(len(brief["hypotheses"]) >= 1)
        self.assertEqual(brief["hypotheses"][0], payload["hypothesis"])
        for crit in payload["selection_criteria"]:
            self.assertIn(crit, brief["selection_criteria"])

        # No background pipeline launched
        mock_stream_pipeline.assert_not_called()

        # Verify brief was persisted in database
        get_resp = self.client.get(f"/api/research/brief/{brief['brief_id']}")
        self.assertEqual(get_resp.status_code, 200)
        persisted = get_resp.json()["brief"]
        self.assertEqual(persisted["brief_id"], brief["brief_id"])
        self.assertEqual(persisted["approval_status"], BriefApprovalStatus.PENDING_APPROVAL)

    # -------------------------------------------------------------------------
    # 3. Approval launches research exactly once for the approved brief version
    # -------------------------------------------------------------------------
    @patch("backend.api.routes_research.stream_research_pipeline")
    def test_approval_launches_research_exactly_once(self, mock_stream_pipeline):
        """An unapproved brief is blocked at the barrier; approved brief launches research once; duplicate is rejected."""
        # Step 3a: Create brief
        brief = prepare_research_brief(
            topic="Topological Majorana Zero Modes in Nanowires",
            research_question="What is the evidence for topological superconductivity in InAs nanowires?",
            db_path=self.db_path,
        )
        self.assertEqual(brief.approval_status, BriefApprovalStatus.PENDING_APPROVAL)

        # Unapproved streaming attempt must stop at approval_barrier
        resp_unapproved = self.client.post(
            "/api/research/stream",
            json={"topic": brief.topic, "brief_id": brief.brief_id},
        )
        self.assertEqual(resp_unapproved.status_code, 200)
        lines = [line.replace("data: ", "") for line in resp_unapproved.text.strip().split("\n") if line.startswith("data: ")]
        events = [json.loads(line) for line in lines if line.strip()]
        barrier_events = [e for e in events if e.get("node") == "approval_barrier"]
        self.assertTrue(len(barrier_events) >= 1)
        self.assertTrue(barrier_events[0]["update"]["requires_approval"])
        # Pipeline was NOT called
        mock_stream_pipeline.assert_not_called()

        # Step 3b: User approves brief version 1
        approve_resp = self.client.post(
            "/api/research/brief/approve",
            json={"brief_id": brief.brief_id, "version": 1},
        )
        self.assertEqual(approve_resp.status_code, 200)
        approved_data = approve_resp.json()
        self.assertTrue(approved_data["success"])
        self.assertEqual(approved_data["brief"]["approval_status"], BriefApprovalStatus.APPROVED)
        self.assertEqual(approved_data["brief"]["approved_version"], 1)

        # Configure mock generator for stream_research_pipeline
        def dummy_pipeline(*args, **kwargs):
            yield {"node": "search", "update": {}, "state": {"topic": brief.topic}}
            yield {"node": "writer", "update": {}, "state": {"report": "# Final Report"}}
            yield {"node": "complete", "update": {}, "state": {}}

        mock_stream_pipeline.side_effect = dummy_pipeline

        # Streaming with approved brief launches research
        resp_approved = self.client.post(
            "/api/research/stream",
            json={"topic": brief.topic, "brief_id": brief.brief_id},
        )
        self.assertEqual(resp_approved.status_code, 200)
        self.assertEqual(mock_stream_pipeline.call_count, 1)

        # Step 3c: Duplicate launch while a task is already registered/running
        brief2 = prepare_research_brief(
            topic="Topological Majorana Zero Modes in Nanowires 2",
            research_question="What is the evidence for topological superconductivity in InAs nanowires? 2",
            db_path=self.db_path,
        )
        approve_research_brief(brief2.brief_id, version=1, db_path=self.db_path)
        task_id = f"task_{brief2.brief_id}_active"
        can_run, _, _ = task_manager.register_task(task_id, brief2.brief_id, 1)
        self.assertTrue(can_run)

        # Second launch attempt must be rejected
        resp_dup = self.client.post(
            "/api/research/stream",
            json={"topic": brief2.topic, "brief_id": brief2.brief_id},
        )
        self.assertEqual(resp_dup.status_code, 200)
        dup_events = [json.loads(line.replace("data: ", "")) for line in resp_dup.text.strip().split("\n") if line.startswith("data: ")]
        rejections = [e for e in dup_events if "rejected" in e.get("node", "")]
        self.assertEqual(len(rejections), 1)
        self.assertIn("already running", rejections[0]["update"]["error"])

    # -------------------------------------------------------------------------
    # 4. Editing a brief invalidates prior approval
    # -------------------------------------------------------------------------
    def test_editing_brief_invalidates_prior_approval(self):
        """Substantive updates increment version, revert status to PENDING_APPROVAL, and reject stale approvals."""
        # 1. Create and approve brief v1
        brief = prepare_research_brief(
            topic="Perovskite Tandem Solar Cell Degradation",
            research_question="What degrades perovskite-silicon interfaces?",
            db_path=self.db_path,
        )
        success, approved_brief, _ = approve_research_brief(brief.brief_id, version=1, db_path=self.db_path)
        self.assertTrue(success)
        self.assertTrue(approved_brief.is_approved())

        # Verify approval verification passes for v1
        is_valid, _, _ = verify_brief_approval(brief.brief_id, expected_version=1, db_path=self.db_path)
        self.assertTrue(is_valid)

        # 2. Update brief substantively via API
        update_resp = self.client.post(
            "/api/research/brief/update",
            json={
                "brief_id": brief.brief_id,
                "updates": {
                    "hypotheses": ["Halide segregation is accelerated by moisture ingress under 1-sun illumination."],
                    "search_scope": "Peer-reviewed journals with impact factor > 5",
                },
            },
        )
        self.assertEqual(update_resp.status_code, 200)
        updated_brief = update_resp.json()["brief"]

        # Version must increment to 2 and approval must be invalidated
        self.assertEqual(updated_brief["version"], 2)
        self.assertEqual(updated_brief["approval_status"], BriefApprovalStatus.PENDING_APPROVAL)
        self.assertIsNone(updated_brief["approved_version"])

        # Approval barrier must now reject execution for the updated brief
        is_valid_after_edit, _, reason = verify_brief_approval(brief.brief_id, db_path=self.db_path)
        self.assertFalse(is_valid_after_edit)
        self.assertIn("Approval Barrier", reason)

        # 3. Attempting to approve using stale version 1 must be rejected with 409 Conflict
        stale_resp = self.client.post(
            "/api/research/brief/approve",
            json={"brief_id": brief.brief_id, "version": 1},
        )
        self.assertEqual(stale_resp.status_code, 409)
        err_msg = stale_resp.json().get("detail", stale_resp.json().get("error", ""))
        self.assertIn("Stale approval rejected", err_msg)

        # 4. Approving current version 2 succeeds and restores valid execution
        approve_v2_resp = self.client.post(
            "/api/research/brief/approve",
            json={"brief_id": brief.brief_id, "version": 2},
        )
        self.assertEqual(approve_v2_resp.status_code, 200)
        self.assertEqual(approve_v2_resp.json()["brief"]["approved_version"], 2)

        is_valid_v2, _, _ = verify_brief_approval(brief.brief_id, expected_version=2, db_path=self.db_path)
        self.assertTrue(is_valid_v2)

    # -------------------------------------------------------------------------
    # 5. A cancelled or stale task cannot silently proceed
    # -------------------------------------------------------------------------
    def test_cancelled_or_stale_task_halts_immediately(self):
        """When cancellation is signaled, cancel_event is set and pipeline halts without continuing work."""
        brief = prepare_research_brief(
            topic="Cold Fusion Replication Attempts",
            research_question="What are the calorimetric limits of palladium deuteride cells?",
            db_path=self.db_path,
        )
        approve_research_brief(brief.brief_id, version=1, db_path=self.db_path)

        # Register task and obtain cancellation event
        task_id = "task_test_cancellation_123"
        can_run, cancel_event, _ = task_manager.register_task(task_id, brief.brief_id, version=1)
        self.assertTrue(can_run)
        self.assertFalse(cancel_event.is_set())

        # Signal cancellation via endpoint
        cancel_resp = self.client.post("/api/research/cancel", json={"task_id": task_id})
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertTrue(cancel_resp.json()["cancelled"])
        self.assertTrue(cancel_event.is_set())

        # Verify pipeline loop halts at first check when cancel_event is set
        state = create_initial_state("Cold Fusion Replication Attempts", scrape_top_n=5, brief=brief)
        events = list(stream_research_pipeline("Cold Fusion Replication Attempts", state, cancel_event=cancel_event))

        # Must contain cancellation node and state must record cancelled = True
        cancel_nodes = [e for e in events if e[0] == "cancelled"]
        self.assertEqual(len(cancel_nodes), 1)
        self.assertTrue(cancel_nodes[0][2]["cancelled"])
        # Pipeline must not have run search or writer nodes
        self.assertNotIn("search", [e[0] for e in events])
        self.assertNotIn("writer", [e[0] for e in events])

    # -------------------------------------------------------------------------
    # 6. Brainstorming escalation preserves hypothesis and thinker context
    # -------------------------------------------------------------------------
    def test_brainstorming_escalation_preserves_hypothesis_and_thinker_context(self):
        """Escalating from a thinker sparring session retains hypothesis, objections, archetype, and biases into writer."""
        thinker_payload = {
            "topic": "Quantum Measurement Problem in Many-Worlds",
            "chat_turns": [
                {"user": "Everettian many-worlds avoids wavefunction collapse.", "assistant": "Popper would ask how branching can be empirically falsified."},
                {"user": "Can cosmological decoherence experiments test this?", "assistant": "Only if branch weight branch interference can be detected."},
            ],
            "thinker_id": "popper",
            "hypothesis": "Branch interference is fundamentally unobservable due to environmental decoherence timescales < 1e-20s.",
            "selection_criteria": ["Empirical falsification bounds", "Decoherence experimental setups"],
        }

        # 1. Prepare brief with thinker escalation metadata
        prep_resp = self.client.post("/api/research/brief/prepare", json=thinker_payload)
        self.assertEqual(prep_resp.status_code, 200)
        brief_data = prep_resp.json()["brief"]

        # Verify thinker context lineage
        tc = brief_data.get("thinker_context")
        self.assertIsNotNone(tc)
        self.assertEqual(tc["thinker_id"], "popper")
        self.assertEqual(tc["archetype"], "Falsificationist Warrior")
        self.assertIn("empirical", tc["perspective"].lower())
        self.assertTrue(len(tc["unresolved_objections"]) >= 1)

        # 2. Approve brief
        approve_research_brief(brief_data["brief_id"], version=1, db_path=self.db_path)
        brief_obj = get_research_brief(brief_data["brief_id"], db_path=self.db_path)

        # 3. Create initial pipeline state with brief
        state = create_initial_state(brief_data["topic"], brief=brief_obj)
        self.assertIn("thinker_context", state)
        self.assertEqual(state["thinker_context"]["thinker_id"], "popper")
        self.assertEqual(state["hypotheses"], [thinker_payload["hypothesis"]])
        self.assertEqual(state["selection_criteria"], thinker_payload["selection_criteria"])

        # 4. Verify writer_node incorporates thinker context in prompt
        state["cumulative_sources"] = [{"id": "s1", "title": "Decoherence in Many Worlds", "authors": ["Zurek"], "year": 2024, "url": "https://example.com"}]
        state["extracted_passages"] = [{"source_id": "s1", "text": "Branch selection is dynamically irreversible."}]

        with patch("backend.pipeline.writer_chain") as mock_writer_chain:
            mock_writer_chain.invoke.return_value = "# Dialectical Synthesis Report"
            updated_state = writer_node(state)
            self.assertIn("report", updated_state)

            # Check prompt sent to LLM
            mock_writer_chain.invoke.assert_called_once()
            call_kwargs = mock_writer_chain.invoke.call_args[0][0]
            context_str = call_kwargs.get("research", call_kwargs.get("context", ""))

            # Must contain thinker instructions, hypothesis, and selection criteria
            self.assertIn("INTELLECTUAL RIGOUR PERSPECTIVE", context_str)
            self.assertIn("Karl Popper", context_str)
            self.assertIn("Branch interference is fundamentally unobservable", context_str)
            self.assertIn("Empirical falsification bounds", context_str)

    # -------------------------------------------------------------------------
    # 7. Existing research and follow-up routes remain compatible
    # -------------------------------------------------------------------------
    def test_existing_research_and_followup_compatibility(self):
        """Legacy ResearchMandate conversion and follow-up routes maintain full backward compatibility."""
        # Test bidirectional conversion: Brief <-> Mandate
        brief = ResearchBrief(
            topic="Quantum Dot Cellular Automata",
            research_question="What are clocking dissipation limits in QCA?",
            objectives=["Measure Landauer dissipation", "Evaluate clocking schemes"],
            hypotheses=["Adiabatic clocking suppresses dissipation below kT ln 2."],
            context_and_assumptions=["Bistable quantum cells implemented with metal dots."],
            search_scope="Nanotechnology peer-reviewed literature",
            selection_criteria=["Cryogenic measurement data only"],
        )
        mandate = brief.to_mandate()
        self.assertIsInstance(mandate, ResearchMandate)
        self.assertEqual(mandate.topic, brief.topic)
        self.assertEqual(mandate.primary_question, brief.research_question)
        self.assertIn("Measure Landauer dissipation", mandate.objective)
        self.assertEqual(mandate.hypotheses, brief.hypotheses)
        self.assertEqual(mandate.known_facts, brief.context_and_assumptions)

        roundtrip_brief = ResearchBrief.from_mandate(mandate)
        self.assertEqual(roundtrip_brief.topic, brief.topic)
        self.assertEqual(roundtrip_brief.research_question, brief.research_question)
        self.assertEqual(roundtrip_brief.hypotheses, brief.hypotheses)

        # Test clarification check endpoint compatibility
        clarify_resp = self.client.post(
            "/api/research/clarify",
            json={"topic": "Quantum Computing"},
        )
        self.assertEqual(clarify_resp.status_code, 200)
        self.assertIn("clarification", clarify_resp.json())

        # Test followup route compatibility
        with patch("backend.api.routes_followup.direct_chat_chain") as mock_chat:
            mock_chat.invoke.return_value = "Followup answer to research questions."
            fu_resp = self.client.post(
                "/api/followup/stream",
                json={
                    "user_query": "Can you elaborate on clocking circuits?",
                    "state": {},
                    "mode_override": "fast_chat",
                },
            )
            self.assertEqual(fu_resp.status_code, 200)
            self.assertIn("Followup answer", fu_resp.text)


if __name__ == "__main__":
    unittest.main()
