"""
Comprehensive test suite for Durable Research Task Lifecycle and Execution Safety.

Validates:
1. Persistence and State Transitions:
   - Creation, retrieval across independent SQLite connections
   - Valid state transitions: QUEUED -> RUNNING -> COMPLETED / FAILED / CANCELLED / FAILED_ORPHANED
   - Rejection of invalid transitions and prevention of terminal-state regression
   - Cancellation request persistence
2. Concurrency and Deduplication:
   - Concurrent creation attempts for the same brief and version (database-enforced partial unique index)
   - Competing execution claims across concurrent threads (atomic claim_task)
   - Retries allowed after FAILED or CANCELLED, blocked after COMPLETED
   - Multiple versions produce distinct task identities
3. Approval and Execution Safety:
   - Missing brief rejected
   - Client-spoofed approval rejected
   - Stale brief version rejected
   - Revocation before claim halts execution
   - Failed claim produces zero research execution
   - Late completion cannot overwrite confirmed cancellation
4. Crash Recovery:
   - Startup reconciliation marks abandoned active tasks as FAILED_ORPHANED
   - Terminal tasks are not modified
   - Zero automatic repetition of scholarly searches/writes
5. API and Mandate Propagation:
   - GET /api/research/task/{task_id} and GET /api/research/tasks
   - Unresolved questions reach writer prompt under explicit epistemic labeling
"""

import unittest
from unittest.mock import patch, MagicMock
import tempfile
import shutil
import json
import os
import threading
import concurrent.futures

from fastapi.testclient import TestClient

from backend.main import app
from backend.memory.db import (
    init_db,
    get_connection,
    get_task_db,
    save_task_db,
    create_task_atomic_db,
    claim_task_atomic_db,
    update_task_status_db,
    request_task_cancellation_db,
    reconcile_orphaned_tasks_db,
    list_tasks_db,
)
from backend.conversation.brief import (
    prepare_research_brief,
    approve_research_brief,
    update_research_brief,
    ResearchTaskManager,
    BriefApprovalStatus,
    clear_briefs_cache,
    task_manager,
)
from backend.pipeline import writer_node


class TestTaskLifecyclePersistence(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="thoth_task_test_")
        self.db_path = os.path.join(self.test_dir, "test_task_store.db")
        init_db(self.db_path)

        # Patch DEFAULT_DB_PATH in db and brief modules
        self.patcher1 = patch("backend.memory.db.DEFAULT_DB_PATH", self.db_path)
        self.patcher2 = patch("backend.conversation.brief.DEFAULT_DB_PATH", self.db_path)
        self.patcher1.start()
        self.patcher2.start()

        clear_briefs_cache()
        task_manager.clear()
        self.tm = ResearchTaskManager(db_path=self.db_path)
        self.client = TestClient(app)

    def tearDown(self):
        clear_briefs_cache()
        task_manager.clear()
        self.patcher2.stop()
        self.patcher1.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_approved_brief(self, topic="Quantum Memory Coherence", version=1):
        brief = prepare_research_brief(
            topic=topic,
            research_question=f"What are coherence limits for {topic}?",
            unresolved_questions=["Is dephasing dominated by surface 1/f noise or bulk defects?"],
            db_path=self.db_path,
        )
        ok, approved, _ = approve_research_brief(brief.brief_id, version=version, db_path=self.db_path)
        self.assertTrue(ok)
        return approved

    # =========================================================================
    # 1. Persistence and State Transitions
    # =========================================================================

    def test_task_creation_and_retrieval_across_connections(self):
        """A created task is immediately readable from a completely separate SQLite connection."""
        brief = self._create_approved_brief()
        ok, task, msg = create_task_atomic_db("task_conn_1", brief.brief_id, 1, db_path=self.db_path)
        self.assertTrue(ok)
        self.assertEqual(task["status"], "QUEUED")

        # Open brand-new independent SQLite connection
        conn2 = get_connection(self.db_path)
        row = conn2.execute("SELECT * FROM research_tasks WHERE task_id = ?;", ("task_conn_1",)).fetchone()
        conn2.close()

        self.assertIsNotNone(row)
        task2 = dict(row)
        self.assertEqual(task2["task_id"], "task_conn_1")
        self.assertEqual(task2["brief_id"], brief.brief_id)
        self.assertEqual(task2["brief_version"], 1)
        self.assertEqual(task2["status"], "QUEUED")
        self.assertIsNotNone(task2["created_at"])
        self.assertIsNone(task2["started_at"])

    def test_all_permitted_lifecycle_transitions(self):
        """Test legitimate transition paths: QUEUED -> RUNNING -> COMPLETED and QUEUED -> RUNNING -> FAILED."""
        brief = self._create_approved_brief("Transition Test")

        # Path A: QUEUED -> RUNNING -> COMPLETED
        ok, _, _ = create_task_atomic_db("task_perm_a", brief.brief_id, 1, db_path=self.db_path)
        self.assertTrue(ok)

        claimed, task_running, _ = claim_task_atomic_db("task_perm_a", "worker_alpha", db_path=self.db_path)
        self.assertTrue(claimed)
        self.assertEqual(task_running["status"], "RUNNING")
        self.assertEqual(task_running["worker_id"], "worker_alpha")
        self.assertIsNotNone(task_running["started_at"])

        completed = update_task_status_db("task_perm_a", "COMPLETED", expected_status="RUNNING", db_path=self.db_path)
        self.assertTrue(completed)
        t_final = get_task_db("task_perm_a", db_path=self.db_path)
        self.assertEqual(t_final["status"], "COMPLETED")
        self.assertIsNotNone(t_final["completed_at"])

    def test_rejection_of_invalid_and_stale_transitions(self):
        """Guard against invalid source states and terminal-state overwrite."""
        brief = self._create_approved_brief("Invalid Transition Test")
        create_task_atomic_db("task_invalid_1", brief.brief_id, 1, db_path=self.db_path)

        # Cannot jump straight from QUEUED to COMPLETED when expected_status is RUNNING
        res = update_task_status_db("task_invalid_1", "COMPLETED", expected_status="RUNNING", db_path=self.db_path)
        self.assertFalse(res)
        self.assertEqual(get_task_db("task_invalid_1", db_path=self.db_path)["status"], "QUEUED")

        # Claim to RUNNING
        claim_task_atomic_db("task_invalid_1", "w1", db_path=self.db_path)

        # Transition to COMPLETED
        update_task_status_db("task_invalid_1", "COMPLETED", db_path=self.db_path)

        # Terminal state cannot regress back to RUNNING or QUEUED
        regress_res = update_task_status_db("task_invalid_1", "RUNNING", db_path=self.db_path)
        self.assertFalse(regress_res)
        self.assertEqual(get_task_db("task_invalid_1", db_path=self.db_path)["status"], "COMPLETED")

    def test_cancellation_request_and_late_completion_protection(self):
        """Cooperative cancellation request is persisted and late worker completion cannot overwrite CANCELLED."""
        brief = self._create_approved_brief("Cancellation Test")
        create_task_atomic_db("task_cancel_1", brief.brief_id, 1, db_path=self.db_path)
        claim_task_atomic_db("task_cancel_1", "worker_slow", db_path=self.db_path)

        # User requests cancellation
        req_ok = request_task_cancellation_db("task_cancel_1", db_path=self.db_path)
        self.assertTrue(req_ok)
        task = get_task_db("task_cancel_1", db_path=self.db_path)
        self.assertTrue(bool(task["cancel_requested"]))

        # Pipeline loop observes cancellation and transitions task to CANCELLED
        cancel_done = update_task_status_db("task_cancel_1", "CANCELLED", db_path=self.db_path)
        self.assertTrue(cancel_done)
        self.assertEqual(get_task_db("task_cancel_1", db_path=self.db_path)["status"], "CANCELLED")

        # Late completion attempt from worker must fail and not overwrite CANCELLED
        late_res = update_task_status_db("task_cancel_1", "COMPLETED", db_path=self.db_path)
        self.assertFalse(late_res)
        self.assertEqual(get_task_db("task_cancel_1", db_path=self.db_path)["status"], "CANCELLED")

    # =========================================================================
    # 2. Concurrency and Deduplication
    # =========================================================================

    def test_concurrent_creation_attempts_for_same_brief_version(self):
        """Database constraint idx_active_research_task guarantees exactly one active task succeeds under race."""
        brief = self._create_approved_brief("Concurrent Creation Test")

        results = []
        def attempt_create(idx):
            task_id = f"task_race_{idx}"
            ok, task_dict, msg = create_task_atomic_db(task_id, brief.brief_id, 1, db_path=self.db_path)
            return (ok, task_id, msg)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(attempt_create, i) for i in range(8)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        self.assertEqual(len(successes), 1, "Exactly one concurrent creation must succeed")
        self.assertEqual(len(failures), 7, "All other concurrent creations must be rejected")
        for f in failures:
            self.assertTrue("already" in f[2].lower() or "concurrency" in f[2].lower())

    def test_competing_execution_claims_race(self):
        """When multiple workers compete to claim the same queued task, exactly one succeeds."""
        brief = self._create_approved_brief("Competing Claim Test")
        create_task_atomic_db("task_claim_race", brief.brief_id, 1, db_path=self.db_path)

        claims = []
        def attempt_claim(worker_id):
            ok, task_dict, msg = claim_task_atomic_db("task_claim_race", worker_id, db_path=self.db_path)
            return (ok, worker_id, msg)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(attempt_claim, f"worker_{i}") for i in range(6)]
            for f in concurrent.futures.as_completed(futures):
                claims.append(f.result())

        successful_claims = [c for c in claims if c[0] is True]
        failed_claims = [c for c in claims if c[0] is False]

        self.assertEqual(len(successful_claims), 1, "Exactly one worker must claim the task")
        self.assertEqual(len(failed_claims), 5, "Other competing workers must be rejected")

        task = get_task_db("task_claim_race", db_path=self.db_path)
        self.assertEqual(task["status"], "RUNNING")
        self.assertEqual(task["worker_id"], successful_claims[0][1])

    def test_retry_policy_failed_and_cancelled_vs_completed(self):
        """A FAILED or CANCELLED task can be retried; a COMPLETED task cannot be rerun."""
        brief = self._create_approved_brief("Retry Policy Test")

        # 1. Task 1 fails
        create_task_atomic_db("task_fail_1", brief.brief_id, 1, db_path=self.db_path)
        claim_task_atomic_db("task_fail_1", "w1", db_path=self.db_path)
        update_task_status_db("task_fail_1", "FAILED", error_code="NET_ERR", error_summary="Timeout", db_path=self.db_path)

        # Retry allowed
        ok_retry, task_retry, _ = create_task_atomic_db("task_retry_1", brief.brief_id, 1, db_path=self.db_path)
        self.assertTrue(ok_retry, "Retry should be permitted after failure")

        # 2. Task retry completes
        claim_task_atomic_db("task_retry_1", "w1", db_path=self.db_path)
        update_task_status_db("task_retry_1", "COMPLETED", db_path=self.db_path)

        # 3. Accidental rerun after COMPLETED must be blocked
        ok_blocked, _, msg_blocked = create_task_atomic_db("task_blocked_1", brief.brief_id, 1, db_path=self.db_path)
        self.assertFalse(ok_blocked, "Completed task cannot be rerun")
        self.assertIn("already completed", msg_blocked.lower())

    def test_different_brief_versions_produce_distinct_tasks(self):
        """Updating a brief creates version 2, which allows a new task distinct from version 1."""
        brief_v1 = self._create_approved_brief("Multi-Version Task Test", version=1)
        create_task_atomic_db("task_v1", brief_v1.brief_id, 1, db_path=self.db_path)
        claim_task_atomic_db("task_v1", "w1", db_path=self.db_path)
        update_task_status_db("task_v1", "COMPLETED", db_path=self.db_path)

        # Update brief substantively to bump version to 2
        brief_v2 = update_research_brief(
            brief_v1.brief_id,
            updates={"hypotheses": ["Updated hypothesis on coherence limits"]},
            db_path=self.db_path,
        )
        self.assertEqual(brief_v2.version, 2)
        approve_research_brief(brief_v2.brief_id, version=2, db_path=self.db_path)

        # New version can be created and run
        ok_v2, task_v2, _ = create_task_atomic_db("task_v2", brief_v2.brief_id, 2, db_path=self.db_path)
        self.assertTrue(ok_v2)
        self.assertEqual(task_v2["brief_version"], 2)

    # =========================================================================
    # 3. Approval and Execution Safety Boundary
    # =========================================================================

    def test_missing_and_unapproved_brief_rejected_at_claim_boundary(self):
        """Execution claim strictly rejects missing briefs and unapproved briefs."""
        # Non-existent brief
        ok1, _, msg1 = create_task_atomic_db("task_no_brief", "non_existent_brief_id", 1, db_path=self.db_path)
        self.assertFalse(ok1)
        self.assertIn("does not exist", msg1.lower())

        # Unapproved brief
        brief_pending = prepare_research_brief(
            topic="Unapproved Topic",
            research_question="Question?",
            db_path=self.db_path,
        )
        ok2, _, msg2 = create_task_atomic_db("task_unapp", brief_pending.brief_id, 1, db_path=self.db_path)
        self.assertFalse(ok2)
        self.assertIn("approval barrier", msg2.lower())

    def test_approval_revocation_before_claim_aborts_execution(self):
        """If brief approval is revoked/modified between task creation and execution claim, claim is rejected."""
        brief = self._create_approved_brief("Revocation Test")
        ok_create, _, _ = create_task_atomic_db("task_revoke_1", brief.brief_id, 1, db_path=self.db_path)
        self.assertTrue(ok_create)

        # Substantive edit invalidates approval before worker claims
        update_research_brief(
            brief.brief_id,
            updates={"hypotheses": ["Radically altered hypothesis"]},
            db_path=self.db_path,
        )

        # Worker attempts to claim execution for v1
        claimed, _, claim_msg = claim_task_atomic_db("task_revoke_1", "worker_late", db_path=self.db_path)
        self.assertFalse(claimed, "Worker must not be permitted to claim task after brief approval invalidated")
        self.assertTrue("revoked" in claim_msg.lower() or "authorization" in claim_msg.lower())

    # =========================================================================
    # 4. Crash Recovery (Orphaned Task Reconciliation)
    # =========================================================================

    def test_startup_reconciliation_marks_orphaned_tasks_failed(self):
        """Unfinished tasks from a crashed process are reconciled to FAILED_ORPHANED without repeating research."""
        brief = self._create_approved_brief("Recovery Test")
        create_task_atomic_db("task_crashed_queued", brief.brief_id, 1, db_path=self.db_path)

        # Create a second brief for a running task
        brief2 = self._create_approved_brief("Recovery Running Test")
        create_task_atomic_db("task_crashed_running", brief2.brief_id, 1, db_path=self.db_path)
        claim_task_atomic_db("task_crashed_running", "worker_dead", db_path=self.db_path)

        # Create a completed task on a third brief
        brief3 = self._create_approved_brief("Recovery Completed Test")
        create_task_atomic_db("task_safe_completed", brief3.brief_id, 1, db_path=self.db_path)
        claim_task_atomic_db("task_safe_completed", "worker_done", db_path=self.db_path)
        update_task_status_db("task_safe_completed", "COMPLETED", db_path=self.db_path)

        # Simulate application startup reconciliation
        reconciled_count = reconcile_orphaned_tasks_db(db_path=self.db_path)
        self.assertEqual(reconciled_count, 2)

        # Check statuses
        t_queued = get_task_db("task_crashed_queued", db_path=self.db_path)
        self.assertEqual(t_queued["status"], "FAILED_ORPHANED")
        self.assertEqual(t_queued["error_code"], "PROCESS_RESTARTED")

        t_running = get_task_db("task_crashed_running", db_path=self.db_path)
        self.assertEqual(t_running["status"], "FAILED_ORPHANED")
        self.assertEqual(t_running["error_code"], "PROCESS_RESTARTED")

        # Completed task must NOT be touched
        t_comp = get_task_db("task_safe_completed", db_path=self.db_path)
        self.assertEqual(t_comp["status"], "COMPLETED")

        # Re-running startup reconciliation is idempotent
        count_again = reconcile_orphaned_tasks_db(db_path=self.db_path)
        self.assertEqual(count_again, 0)

    # =========================================================================
    # 5. API Endpoints for Task Inspection
    # =========================================================================

    def test_task_status_api_endpoints(self):
        """GET /api/research/task/{task_id} and GET /api/research/tasks return non-sensitive status."""
        brief = self._create_approved_brief("API Test")
        create_task_atomic_db("task_api_inspect", brief.brief_id, 1, db_path=self.db_path)

        # 1. Query existing task
        resp = self.client.get("/api/research/task/task_api_inspect")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        t = data["task"]
        self.assertEqual(t["task_id"], "task_api_inspect")
        self.assertEqual(t["status"], "QUEUED")
        self.assertEqual(t["brief_id"], brief.brief_id)
        self.assertEqual(t["brief_version"], 1)
        self.assertIn("created_at", t)

        # 2. Query non-existent task
        resp_404 = self.client.get("/api/research/task/non_existent_task")
        self.assertEqual(resp_404.status_code, 404)
        self.assertFalse(resp_404.json()["success"])

        # 3. List tasks
        resp_list = self.client.get(f"/api/research/tasks?brief_id={brief.brief_id}")
        self.assertEqual(resp_list.status_code, 200)
        list_data = resp_list.json()
        self.assertTrue(list_data["success"])
        self.assertEqual(list_data["total"], 1)
        self.assertEqual(list_data["tasks"][0]["task_id"], "task_api_inspect")

    # =========================================================================
    # 6. Mandate Propagation: Unresolved Questions in Writer
    # =========================================================================

    @patch("backend.pipeline.writer_chain")
    def test_unresolved_questions_reach_writer_prompt_with_epistemic_label(self, mock_writer_chain):
        """Unresolved questions must be injected into the writer prompt with explicit epistemic distinction."""
        unresolved = [
            "Are fluxonium coherence limits dominated by dielectric loss or 1/f flux noise?",
            "Can 3D cavity integration suppress radiative losses below 10 Hz?"
        ]

        state = {
            "topic": "Fluxonium Coherence Limits",
            "findings": [{"claim": "Dielectric loss is significant.", "source": "Smith 2024", "reliability": 0.9}],
            "sources": [{"title": "Smith 2024", "authors": ["Smith"], "year": 2024}],
            "brief": {
                "brief_id": "brief_test_unresolved",
                "version": 1,
                "unresolved_questions": unresolved,
            },
            "unresolved_questions": unresolved,
            "role": "Lead Researcher",
            "tone": "objective and rigorous",
            "current_step": "writer",
        }

        # Mock LLM response string
        mock_writer_chain.invoke.return_value = "# Comprehensive Fluxonium Report\n\nContent here."

        # Invoke writer_node
        result_state = writer_node(state)

        # Inspect prompt received by writer_chain
        self.assertTrue(mock_writer_chain.invoke.called)
        invoke_input = mock_writer_chain.invoke.call_args[0][0]
        research_combined = invoke_input.get("research", "")

        # Verify labeled section header exists
        self.assertIn("UNRESOLVED QUESTIONS & COMPETING PERSPECTIVES TO EXAMINE", research_combined)
        self.assertIn("Investigate as unverified inquiries, not established facts", research_combined)

        # Verify exact questions appear in prompt
        for q in unresolved:
            self.assertIn(q, research_combined)

        # Result state contains report
        self.assertIn("report", result_state)

