import os
import shutil
import tempfile
import time
import unittest
import sqlite3

from backend.memory.db import (
    init_db,
    get_connection,
    save_session,
    get_session,
    list_sessions,
    delete_session,
    save_report,
    get_report,
    list_reports,
    get_latest_report,
)


class TestSessionReportDatabaseCRUD(unittest.TestCase):
    """
    Integration tests covering the entire session and report CRUD surface in backend/memory/db.py.
    Uses a real temporary SQLite database with WAL and foreign keys enabled on disk per test — zero mocks.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="thoth_test_db_")
        self.db_path = os.path.join(self.test_dir, "test_store.db")
        init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Session CRUD Operations
    # -------------------------------------------------------------------------

    def test_save_and_get_session_expected(self):
        meta = {"tags": ["quantum", "research"], "priority": "high", "runs": 3}
        created = save_session(
            session_id="sess_001",
            title="Quantum Superconducting Circuits",
            summary="Initial discovery on transmon qubits.",
            metadata=meta,
            db_path=self.db_path
        )

        self.assertIsNotNone(created)
        self.assertEqual(created["session_id"], "sess_001")
        self.assertEqual(created["title"], "Quantum Superconducting Circuits")
        self.assertEqual(created["summary"], "Initial discovery on transmon qubits.")
        self.assertEqual(created["metadata"], meta)
        self.assertTrue(created["created_at"])
        self.assertTrue(created["updated_at"])

        # Retrieve session
        fetched = get_session("sess_001", db_path=self.db_path)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["session_id"], "sess_001")
        self.assertEqual(fetched["title"], "Quantum Superconducting Circuits")
        self.assertEqual(fetched["metadata"]["tags"], ["quantum", "research"])

    def test_save_session_upsert_updates_fields(self):
        save_session(
            session_id="sess_upsert",
            title="Initial Title",
            summary="Initial Summary",
            metadata={"v": 1},
            db_path=self.db_path
        )

        time.sleep(0.01)  # Ensure updated_at timestamp advances

        updated = save_session(
            session_id="sess_upsert",
            title="Updated Title",
            summary="Updated Summary",
            metadata={"v": 2, "revised": True},
            db_path=self.db_path
        )

        self.assertEqual(updated["session_id"], "sess_upsert")
        self.assertEqual(updated["title"], "Updated Title")
        self.assertEqual(updated["summary"], "Updated Summary")
        self.assertEqual(updated["metadata"], {"v": 2, "revised": True})

        # Confirm only 1 session exists in DB
        all_sess = list_sessions(db_path=self.db_path)
        self.assertEqual(len(all_sess), 1)

    def test_get_session_nonexistent_returns_none(self):
        res = get_session("nonexistent_session_id", db_path=self.db_path)
        self.assertIsNone(res)

    def test_list_sessions_ordering_and_limit(self):
        # Insert 3 sessions with slight pauses to guarantee timestamp order
        for i in range(1, 4):
            save_session(
                session_id=f"sess_{i}",
                title=f"Session {i}",
                summary=f"Summary {i}",
                db_path=self.db_path
            )
            time.sleep(0.02)

        # Update sess_1 so its updated_at timestamp becomes the newest
        time.sleep(0.02)
        save_session(
            session_id="sess_1",
            title="Session 1 - Revised",
            summary="Summary 1 - Revised",
            db_path=self.db_path
        )

        all_sessions = list_sessions(db_path=self.db_path)
        self.assertEqual(len(all_sessions), 3)
        # Most recently updated must be first (sess_1)
        self.assertEqual(all_sessions[0]["session_id"], "sess_1")
        self.assertEqual(all_sessions[1]["session_id"], "sess_3")
        self.assertEqual(all_sessions[2]["session_id"], "sess_2")

        # Test limit
        limited_sessions = list_sessions(limit=2, db_path=self.db_path)
        self.assertEqual(len(limited_sessions), 2)
        self.assertEqual(limited_sessions[0]["session_id"], "sess_1")
        self.assertEqual(limited_sessions[1]["session_id"], "sess_3")

    # -------------------------------------------------------------------------
    # 2. Report CRUD Operations
    # -------------------------------------------------------------------------

    def test_save_and_get_report_expected(self):
        mindmap_data = {
            "nodes": [
                {"id": "root", "label": "Topic", "type": "topic"},
                {"id": "sub1", "label": "Hardware", "type": "subtopic"}
            ],
            "edges": [
                {"from": "root", "to": "sub1", "label": "explores"}
            ]
        }

        report = save_report(
            report_id="rep_101",
            session_id="sess_parent",
            topic="Neuromorphic Vision",
            content="# Neuromorphic Vision\nEvent-based sensors process visual streams.",
            score=8.7,
            verifier_feedback="All 5 claims verified.",
            mindmap=mindmap_data,
            db_path=self.db_path
        )

        self.assertIsNotNone(report)
        self.assertEqual(report["report_id"], "rep_101")
        self.assertEqual(report["session_id"], "sess_parent")
        self.assertEqual(report["topic"], "Neuromorphic Vision")
        self.assertEqual(report["score"], 8.7)
        self.assertEqual(report["verifier_feedback"], "All 5 claims verified.")
        self.assertEqual(report["mindmap"], mindmap_data)

        # Retrieve report
        fetched = get_report("rep_101", db_path=self.db_path)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["report_id"], "rep_101")
        self.assertEqual(fetched["content"], "# Neuromorphic Vision\nEvent-based sensors process visual streams.")
        self.assertEqual(fetched["mindmap"]["nodes"][0]["id"], "root")

    def test_save_report_auto_creates_parent_session_if_missing(self):
        # Verify sess_auto does not exist prior to saving report
        self.assertIsNone(get_session("sess_auto", db_path=self.db_path))

        save_report(
            report_id="rep_auto",
            session_id="sess_auto",
            topic="CRISPR Advances",
            content="Gene editing overview...",
            score=9.1,
            db_path=self.db_path
        )

        # Confirm parent session was automatically provisioned
        parent_session = get_session("sess_auto", db_path=self.db_path)
        self.assertIsNotNone(parent_session)
        self.assertEqual(parent_session["title"], "CRISPR Advances")

    def test_save_report_upsert_updates_fields(self):
        save_report(
            report_id="rep_upsert",
            session_id="sess_main",
            topic="AI Safety",
            content="Draft v1",
            score=6.0,
            db_path=self.db_path
        )

        updated = save_report(
            report_id="rep_upsert",
            session_id="sess_main",
            topic="AI Safety & Alignment",
            content="Draft v2 (Revised)",
            score=9.2,
            verifier_feedback="Passed verification",
            mindmap={"nodes": [{"id": "n1"}], "edges": []},
            db_path=self.db_path
        )

        self.assertEqual(updated["topic"], "AI Safety & Alignment")
        self.assertEqual(updated["content"], "Draft v2 (Revised)")
        self.assertEqual(updated["score"], 9.2)
        self.assertEqual(updated["verifier_feedback"], "Passed verification")

        all_reports = list_reports(session_id="sess_main", db_path=self.db_path)
        self.assertEqual(len(all_reports), 1)

    def test_get_report_nonexistent_returns_none(self):
        self.assertIsNone(get_report("rep_nonexistent", db_path=self.db_path))

    def test_list_reports_filtered_and_unfiltered(self):
        # Create 2 reports in Session A and 1 report in Session B
        save_report("rep_a1", "sess_a", "Topic A1", "Content A1", score=8.0, db_path=self.db_path)
        time.sleep(0.01)
        save_report("rep_a2", "sess_a", "Topic A2", "Content A2", score=8.5, db_path=self.db_path)
        time.sleep(0.01)
        save_report("rep_b1", "sess_b", "Topic B1", "Content B1", score=9.0, db_path=self.db_path)

        # Unfiltered list
        all_reports = list_reports(db_path=self.db_path)
        self.assertEqual(len(all_reports), 3)

        # Filtered by session_id
        session_a_reports = list_reports(session_id="sess_a", db_path=self.db_path)
        self.assertEqual(len(session_a_reports), 2)
        rep_ids_a = [r["report_id"] for r in session_a_reports]
        self.assertIn("rep_a1", rep_ids_a)
        self.assertIn("rep_a2", rep_ids_a)
        self.assertNotIn("rep_b1", rep_ids_a)

        session_b_reports = list_reports(session_id="sess_b", db_path=self.db_path)
        self.assertEqual(len(session_b_reports), 1)
        self.assertEqual(session_b_reports[0]["report_id"], "rep_b1")

        # Limited query
        limited = list_reports(limit=2, db_path=self.db_path)
        self.assertEqual(len(limited), 2)

    def test_get_latest_report(self):
        # Empty DB returns None
        self.assertIsNone(get_latest_report(db_path=self.db_path))

        # Add 2 reports sequentially
        save_report("rep_first", "sess_timeline", "Timeline Topic 1", "Content 1", db_path=self.db_path)
        time.sleep(0.02)
        save_report("rep_latest", "sess_timeline", "Timeline Topic 2", "Content 2", db_path=self.db_path)

        latest = get_latest_report(db_path=self.db_path)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["report_id"], "rep_latest")

        # Filtered by session
        latest_sess = get_latest_report(session_id="sess_timeline", db_path=self.db_path)
        self.assertEqual(latest_sess["report_id"], "rep_latest")

        # Filtered by nonexistent session
        self.assertIsNone(get_latest_report(session_id="nonexistent_sess", db_path=self.db_path))

    # -------------------------------------------------------------------------
    # 3. Foreign Key Cascade Deletion Tests
    # -------------------------------------------------------------------------

    def test_delete_session_cascades_and_deletes_all_linked_reports(self):
        """
        CRITICAL FOREIGN KEY CASCADE INTEGRATION TEST:
        Creates a session with two linked reports, executes delete_session,
        and directly asserts against the underlying SQLite reports table
        to prove linked reports are physically deleted by ON DELETE CASCADE.
        """
        # 1. Create a parent session
        save_session(
            session_id="sess_to_cascade",
            title="Session for Cascade Deletion Test",
            summary="Testing cascading foreign key deletion",
            db_path=self.db_path
        )

        # 2. Create two linked child reports
        save_report(
            report_id="rep_child_1",
            session_id="sess_to_cascade",
            topic="Topic Child 1",
            content="Child 1 report content",
            score=8.1,
            db_path=self.db_path
        )
        save_report(
            report_id="rep_child_2",
            session_id="sess_to_cascade",
            topic="Topic Child 2",
            content="Child 2 report content",
            score=8.9,
            db_path=self.db_path
        )

        # Also create an independent session with its own report to ensure no over-deletion
        save_session("sess_independent", title="Independent Session", db_path=self.db_path)
        save_report("rep_independent", "sess_independent", "Independent Topic", "Content", db_path=self.db_path)

        # Verify initial state: 2 child reports exist for sess_to_cascade
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reports WHERE session_id = ?;", ("sess_to_cascade",))
        initial_child_count = cursor.fetchone()[0]
        self.assertEqual(initial_child_count, 2)

        # 3. Delete the parent session
        deleted = delete_session("sess_to_cascade", db_path=self.db_path)
        self.assertTrue(deleted, "delete_session should return True when deleting an existing session")

        # 4. Verify session is deleted
        self.assertIsNone(get_session("sess_to_cascade", db_path=self.db_path))

        # 5. HARD ASSERTION: Query SQLite directly to confirm linked reports are physically deleted from disk
        cursor.execute("SELECT COUNT(*) FROM reports WHERE session_id = ?;", ("sess_to_cascade",))
        remaining_child_count = cursor.fetchone()[0]
        self.assertEqual(
            remaining_child_count,
            0,
            "Linked reports were NOT deleted from the reports table upon session deletion! Cascade failed."
        )

        # 6. Confirm individual get_report calls return None
        self.assertIsNone(get_report("rep_child_1", db_path=self.db_path))
        self.assertIsNone(get_report("rep_child_2", db_path=self.db_path))
        self.assertEqual(list_reports(session_id="sess_to_cascade", db_path=self.db_path), [])

        # 7. Confirm independent session and its report were NOT affected
        self.assertIsNotNone(get_session("sess_independent", db_path=self.db_path))
        self.assertIsNotNone(get_report("rep_independent", db_path=self.db_path))
        cursor.execute("SELECT COUNT(*) FROM reports WHERE session_id = ?;", ("sess_independent",))
        self.assertEqual(cursor.fetchone()[0], 1)

    def test_delete_session_nonexistent_returns_false(self):
        res = delete_session("nonexistent_session_id", db_path=self.db_path)
        self.assertFalse(res, "delete_session should return False when attempting to delete a non-existent session")


if __name__ == "__main__":
    unittest.main()
