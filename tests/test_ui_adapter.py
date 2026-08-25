import unittest
from unittest.mock import patch, MagicMock

from frontend.ui_adapter import (
    ResearchPipelineRunner,
    read_vault_note,
    traverse_vault_graph,
    list_stored_reports,
    list_stored_sessions,
    get_telemetry_status
)
from backend.memory.vault import Note


class TestUIAdapterContracts(unittest.TestCase):

    def test_runner_schema_version_and_attributes(self):
        runner = ResearchPipelineRunner()
        self.assertEqual(runner._schema_version, ResearchPipelineRunner.SCHEMA_VERSION)
        self.assertFalse(runner.followup_completed)
        self.assertFalse(runner.is_running())

    @patch("backend.memory.vault.read_note")
    def test_read_vault_note_returns_dict_with_frontmatter(self, mock_read_note):
        mock_note = Note(
            note_id="topic-quantum_test",
            note_type="topics",
            content="## Overview\nQuantum test content referencing [[src-test_ref]].",
            frontmatter={"type": "topics", "confidence": 0.95, "sources": ["src-test_ref"]},
            file_path="/tmp/fake_path.md"
        )
        mock_read_note.return_value = mock_note

        data = read_vault_note("topic-quantum_test")
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("note_id"), "topic-quantum_test")
        self.assertEqual(data.get("type"), "topics")
        self.assertIn("content", data)
        self.assertIn("frontmatter", data)
        self.assertIsInstance(data.get("frontmatter"), dict)
        self.assertEqual(data["frontmatter"].get("confidence"), 0.95)

    @patch("backend.memory.graph.get_subgraph")
    def test_traverse_vault_graph_returns_edge_dicts(self, mock_get_subgraph):
        mock_get_subgraph.return_value = {
            "nodes": ["NoteA", "NoteB", "NoteC"],
            "edges": [
                {"source": "NoteA", "relation": "cites", "target": "NoteB", "confidence": 0.9},
                {"source": "NoteA", "relation": "supports", "target": "NoteC", "confidence": 0.85}
            ]
        }

        edges = traverse_vault_graph("NoteA", max_depth=1)
        self.assertIsInstance(edges, list)
        self.assertEqual(len(edges), 2)
        targets = [e.get("target") for e in edges]
        relations = [e.get("relation") for e in edges]
        self.assertIn("NoteB", targets)
        self.assertIn("NoteC", targets)
        self.assertIn("cites", relations)
        self.assertIn("supports", relations)

    @patch("backend.memory.db.list_reports")
    @patch("backend.memory.db.list_sessions")
    def test_list_stored_reports_and_sessions(self, mock_list_sessions, mock_list_reports):
        mock_list_reports.return_value = [{
            "report_id": "rep_123",
            "session_id": "sess_123",
            "topic": "Test Topic",
            "content": "Report content",
            "score": 8.5,
            "mindmap": {"nodes": [{"id": "n1", "label": "N1"}], "edges": []}
        }]
        mock_list_sessions.return_value = [{
            "session_id": "sess_123",
            "title": "Test Session"
        }]

        reps = list_stored_reports(limit=10)
        self.assertIsInstance(reps, list)
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["topic"], "Test Topic")
        self.assertIsInstance(reps[0]["mindmap"], dict)
        self.assertEqual(len(reps[0]["mindmap"]["nodes"]), 1)

        sess = list_stored_sessions(limit=10)
        self.assertIsInstance(sess, list)
        self.assertEqual(len(sess), 1)
        self.assertEqual(sess[0]["title"], "Test Session")

    def test_get_telemetry_status(self):
        status = get_telemetry_status()
        self.assertIsInstance(status, dict)
        self.assertIn("circuit_breaker_state", status)
        self.assertIn("primary_provider", status)
        self.assertIn("fallback_provider", status)
        self.assertIn(status["circuit_breaker_state"], ["CLOSED", "OPEN", "HALF_OPEN"])


if __name__ == "__main__":
    unittest.main()
