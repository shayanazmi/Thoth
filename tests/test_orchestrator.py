import unittest
from unittest.mock import patch, MagicMock
from threading import Event
from backend.orchestrator import (
    create_initial_state,
    stream_research_pipeline,
    run_research_pipeline
)


class TestOrchestrator(unittest.TestCase):

    def test_create_initial_state(self):
        state = create_initial_state(topic="Quantum Mechanics", scrape_top_n=3, min_score=7.0)
        self.assertEqual(state["topic"], "Quantum Mechanics")
        self.assertEqual(state["scrape_top_n"], 3)
        self.assertEqual(state["min_score"], 7.0)
        self.assertEqual(state["attempt"], 0)
        self.assertEqual(state["score"], 0.0)

    @patch("backend.orchestrator.search_node")
    @patch("backend.orchestrator.concurrent_scrape_urls")
    @patch("backend.orchestrator.writer_node")
    @patch("backend.orchestrator.concurrent_verifier_and_critic")
    @patch("backend.orchestrator.mindmap_node")
    @patch("backend.orchestrator.follow_up_node")
    def test_orchestrator_linear_pipeline_flow(
        self, mock_followup, mock_mindmap, mock_ver_crit, mock_writer, mock_scrape, mock_search
    ):
        mock_search.return_value = {"search_results": "Mock search data", "cumulative_sources": [{"url": "https://example.com"}]}
        mock_scrape.return_value = ("Mock scraped content", [{"url": "https://example.com"}])
        mock_writer.return_value = {"report": "Draft Report v1", "attempt": 1}
        mock_ver_crit.return_value = ({"verifier_feedback": ""}, {"feedback": "Good report", "score": 8.0})
        mock_mindmap.return_value = {"mindmap": {"nodes": [{"id": "r", "label": "Root"}], "edges": []}}
        mock_followup.return_value = {"follow_up_questions": ["Q1?", "Q2?"]}

        yielded_nodes = []
        for node_name, update, current_state in stream_research_pipeline(topic="Test Topic"):
            yielded_nodes.append(node_name)

        # Assert full Plan -> Act -> Observe -> Replan flow sequence
        expected_nodes = ["search", "scrape", "writer", "verifier", "critic", "vault", "mindmap", "follow_up"]
        self.assertEqual(yielded_nodes, expected_nodes)

    @patch("backend.orchestrator.search_node")
    @patch("backend.orchestrator.concurrent_scrape_urls")
    @patch("backend.orchestrator.writer_node")
    @patch("backend.orchestrator.concurrent_verifier_and_critic")
    @patch("backend.orchestrator.mindmap_node")
    @patch("backend.orchestrator.follow_up_node")
    def test_orchestrator_replan_loopback_on_low_critic_score(
        self, mock_followup, mock_mindmap, mock_ver_crit, mock_writer, mock_scrape, mock_search
    ):
        mock_search.return_value = {"search_results": "Search data"}
        mock_scrape.return_value = ("Scraped content", [])
        
        mock_writer.side_effect = [
            {"report": "Draft Report v1", "attempt": 1},
            {"report": "Revised Report v2", "attempt": 2}
        ]
        
        # Critic returns 5.0 on attempt 1, 8.5 on attempt 2
        mock_ver_crit.side_effect = [
            ({"verifier_feedback": ""}, {"feedback": "Needs work", "score": 5.0}),
            ({"verifier_feedback": ""}, {"feedback": "Exceeds threshold", "score": 8.5})
        ]
        mock_mindmap.return_value = {"mindmap": {"nodes": [], "edges": []}}
        mock_followup.return_value = {"follow_up_questions": []}

        yielded_nodes = []
        for node_name, update, current_state in stream_research_pipeline(topic="Low Score Topic", min_score=6.5, max_retries=2):
            yielded_nodes.append(node_name)

        # Expected flow: search -> scrape -> writer (1) -> verifier -> critic (5.0) -> REPLAN -> writer (2) -> verifier -> critic (8.5) -> vault -> mindmap -> follow_up
        expected = ["search", "scrape", "writer", "verifier", "critic", "writer", "verifier", "critic", "vault", "mindmap", "follow_up"]
        self.assertEqual(yielded_nodes, expected)

    @patch("backend.orchestrator.search_node")
    def test_orchestrator_cancellation_event(self, mock_search):
        cancel = Event()
        cancel.set()  # Immediately cancelled

        yielded_nodes = []
        for node_name, update, current_state in stream_research_pipeline(topic="Cancelled Topic", cancel_event=cancel):
            yielded_nodes.append(node_name)

        self.assertEqual(len(yielded_nodes), 0)
        mock_search.assert_not_called()

    def test_persist_turn_to_vault_creates_and_indexes_notes(self):
        import tempfile
        import os
        import shutil
        from backend.orchestrator import persist_turn_to_vault
        from backend.memory.vault import read_note, list_notes
        from backend.memory.index import search_keyword, hybrid_search

        temp_dir = tempfile.mkdtemp()
        vault_dir = os.path.join(temp_dir, "vault")
        db_path = os.path.join(temp_dir, "test_store.db")

        try:
            fake_state = {
                "topic": "Neuromorphic Computing Spiking Networks",
                "draft": """# Neuromorphic Computing Overview
Neuromorphic architectures emulate biological nervous systems.

## Key Findings
- Spiking neural networks reduce inference energy consumption by up to 90%
- Event-driven processing eliminates idle power consumption in edge sensors
- Memristive crossbar arrays provide efficient in-memory matrix-vector multiplication
""",
                "score": 9.0,
                "verification_results": [
                    {
                        "claim": "Spiking neural networks reduce inference energy consumption by up to 90%",
                        "is_valid": True,
                        "supporting_source_id": "src-energy-efficient_neuromorphic_silic"
                    }
                ],
                "cumulative_sources": [
                    {
                        "title": "Energy-efficient Neuromorphic Silicon",
                        "url": "https://arxiv.org/abs/2401.99999",
                        "domain": "arxiv.org",
                        "source_api": "arxiv",
                        "doi": "10.1000/neuro.2024",
                        "snippet": "We demonstrate sub-milliwatt spiking network hardware."
                    }
                ]
            }

            vault_update = persist_turn_to_vault(fake_state, vault_dir=vault_dir, db_path=db_path)

            self.assertIn("vault_notes", vault_update)
            self.assertIn("primary_topic_note", vault_update)
            self.assertIn("source_notes", vault_update)

            # Confirm files exist in vault
            all_notes = list_notes(vault_dir=vault_dir)
            self.assertTrue(len(all_notes) >= 2)
            self.assertIn(vault_update["primary_topic_note"], all_notes)

            # Confirm topic note claims have valid citations
            topic_note = read_note(vault_update["primary_topic_note"], vault_dir=vault_dir)
            self.assertIn("Claims", topic_note.content)
            self.assertIn("[[src-", topic_note.content)

            # Confirm hybrid search finds the topic
            search_hits = hybrid_search("biological nervous systems energy", top_k=2, db_path=db_path, vault_dir=vault_dir)
            self.assertTrue(len(search_hits) > 0)
            self.assertEqual(search_hits[0]["note_id"], vault_update["primary_topic_note"])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
