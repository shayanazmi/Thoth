import unittest
from starlette.testclient import TestClient

from web_server import app


class TestWebServerEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("app", data)

    def test_status_endpoint(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("circuit_breaker_state", data)
        self.assertIn("primary_provider", data)
        self.assertIn("fallback_provider", data)

    def test_list_sessions_endpoint(self):
        response = self.client.get("/api/sessions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_list_reports_endpoint(self):
        response = self.client.get("/api/reports")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_vault_notes_endpoint(self):
        response = self.client.get("/api/vault/notes")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("notes", data)
        self.assertIsInstance(data["notes"], list)

    def test_vault_graph_endpoint(self):
        response = self.client.get("/api/vault/graph")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)


if __name__ == "__main__":
    unittest.main()
