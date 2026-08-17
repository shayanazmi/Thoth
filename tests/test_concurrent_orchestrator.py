import unittest
import asyncio
import time
from unittest.mock import patch, AsyncMock
from backend.dispatcher import Dispatcher
from backend.orchestrator import (
    concurrent_scrape_urls,
    concurrent_verifier_and_critic,
    stream_research_pipeline
)


class TestConcurrentOrchestrator(unittest.IsolatedAsyncioTestCase):

    async def test_concurrent_scrape_urls_fans_out(self):
        urls = ["https://site1.com", "https://site2.com", "https://site3.com"]
        dispatcher = Dispatcher(max_concurrent=3, max_attempts=1, base_delay=0.01)

        async def mock_call(fn, *args, **kwargs):
            arg_dict = args[0] if args else kwargs
            return f"Content for {arg_dict.get('url')}"

        with patch.object(dispatcher, "call", side_effect=mock_call):
            start_time = time.time()
            content, sources = await concurrent_scrape_urls(urls, dispatcher)
            elapsed = time.time() - start_time

            self.assertEqual(len(sources), 3)
            self.assertIn("https://site1.com", content)
            self.assertIn("https://site2.com", content)
            self.assertIn("https://site3.com", content)

    async def test_concurrent_verifier_and_critic_runs_in_parallel(self):
        dispatcher = Dispatcher(max_concurrent=3, max_attempts=1, base_delay=0.01)
        state = {"report": "Draft Report Content", "scraped_content": "Source Text"}

        with patch("backend.orchestrator.verifier_node") as mock_ver, \
             patch("backend.orchestrator.critic_node") as mock_crit:
            
            mock_ver.return_value = {"verifier_feedback": "Verified"}
            mock_crit.return_value = {"feedback": "Good", "score": 9.0}

            v_update, c_update = await concurrent_verifier_and_critic(state, dispatcher)

            self.assertEqual(v_update, {"verifier_feedback": "Verified"})
            self.assertEqual(c_update, {"feedback": "Good", "score": 9.0})
            mock_ver.assert_called_once()
            mock_crit.assert_called_once()


class TestConcurrentPipelineStream(unittest.TestCase):

    @patch("backend.orchestrator.search_node")
    @patch("backend.orchestrator.concurrent_scrape_urls")
    @patch("backend.orchestrator.writer_node")
    @patch("backend.orchestrator.concurrent_verifier_and_critic")
    @patch("backend.orchestrator.mindmap_node")
    @patch("backend.orchestrator.follow_up_node")
    def test_stream_pipeline_concurrent_act_phase(
        self, mock_followup, mock_mindmap, mock_ver_crit, mock_writer, mock_scrape_async, mock_search
    ):
        mock_search.return_value = {
            "search_results": "https://site1.com https://site2.com",
            "cumulative_sources": [{"url": "https://site1.com"}, {"url": "https://site2.com"}]
        }
        mock_scrape_async.return_value = ("Scraped Data", [{"url": "https://site1.com"}])
        mock_writer.return_value = {"report": "Draft v1", "attempt": 1}
        mock_ver_crit.return_value = ({"verifier_feedback": ""}, {"feedback": "Excellent", "score": 8.5})
        mock_mindmap.return_value = {"mindmap": {"nodes": [], "edges": []}}
        mock_followup.return_value = {"follow_up_questions": []}

        yielded = []
        for node_name, update, state in stream_research_pipeline(topic="Concurrent Test"):
            yielded.append(node_name)

        expected = ["search", "scrape", "writer", "verifier", "critic", "vault", "mindmap", "follow_up"]
        self.assertEqual(yielded, expected)


if __name__ == "__main__":
    unittest.main()
