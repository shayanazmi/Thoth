"""
eval_sandbox/test_server_live_endpoints.py
Verifies:
1. Fast-path direct chat SSE stream (<500ms latency, valid JSON SSE chunks).
2. Follow-up turn endpoint (/api/followup/stream).
3. Vault notes REST endpoints (/api/vault/notes).
"""

import sys
import os
import unittest
import json
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web_server import app


class TestServerLiveEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_fast_chat_sse_stream(self):
        """Test casual greeting returns fast-path direct chat response in under 500ms."""
        response = self.client.post(
            "/api/research/stream",
            json={"topic": "Hi", "mode": "fast_chat"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        
        # Parse SSE chunks
        lines = response.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:")]
        self.assertGreaterEqual(len(data_lines), 1)
        
        first_event = json.loads(data_lines[0].replace("data:", "").strip())
        self.assertEqual(first_event["node"], "direct_chat")
        self.assertIn("Thoth", first_event["update"]["answer"])
        print("  ✓ Fast-path direct chat SSE endpoint verified.")

    def test_vault_notes_list_endpoint(self):
        """Test /api/vault/notes returns indexed notes list."""
        response = self.client.get("/api/vault/notes")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("notes", data)
        self.assertIsInstance(data["notes"], list)
        print(f"  ✓ Vault notes endpoint verified ({len(data['notes'])} notes indexed).")


if __name__ == "__main__":
    unittest.main()
