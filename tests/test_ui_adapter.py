import json
import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from web_server import app, is_casual_query

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

    def test_vault_note_detail_endpoint_serialization(self):
        from backend.memory.vault import Note
        sample_note = Note(
            note_id="topic-quantum-test",
            note_type="topics",
            content="# Quantum Test\nDetailed markdown content.",
            frontmatter={"confidence": 0.95, "sources": ["src-1"]},
            file_path="/tmp/topic-quantum-test.md"
        )
        with patch("web_server.read_note", return_value=sample_note):
            response = self.client.get("/api/vault/note/topic-quantum-test")
            self.assertEqual(response.status_code, 200)
            data = response.json()

            self.assertEqual(data["id"], "topic-quantum-test")
            self.assertEqual(data["type"], "topics")
            self.assertEqual(data["content"], "# Quantum Test\nDetailed markdown content.")
            self.assertEqual(data["frontmatter"]["confidence"], 0.95)

            self.assertEqual(data["note_id"], "topic-quantum-test")
            self.assertEqual(data["note_type"], "topics")
            self.assertEqual(data["file_path"], "/tmp/topic-quantum-test.md")

            self.assertTrue(len(json.dumps(data)) > 0)

    def test_vault_note_detail_endpoint_not_found(self):
        with patch("web_server.read_note", side_effect=FileNotFoundError("Note not found")):
            response = self.client.get("/api/vault/note/missing-nonexistent-note")
            self.assertEqual(response.status_code, 404)
            data = response.json()
            self.assertIn("detail", data)
            self.assertIn("missing-nonexistent-note", data["detail"])

    def test_vault_graph_endpoint(self):
        response = self.client.get("/api/vault/graph")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

    def test_research_stream_casual_query_fast_path(self):
        mock_direct = MagicMock()
        mock_direct.invoke.return_value = "Greetings! I am Thoth. How may I assist your scientific research today?"

        with patch("web_server.direct_chat_chain", mock_direct):
            response = self.client.post("/api/research/stream", json={"topic": "Hi Thoth"})
            self.assertEqual(response.status_code, 200)

            mock_direct.invoke.assert_called_once_with({"user_query": "Hi Thoth"})

            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            self.assertGreaterEqual(len(data_lines), 2)
            first_event = json.loads(data_lines[0].replace("data:", "").strip())
            self.assertEqual(first_event.get("node"), "direct_chat")
            self.assertIn("Greetings! I am Thoth.", first_event.get("update", {}).get("answer", ""))

            second_event = json.loads(data_lines[1].replace("data:", "").strip())
            self.assertEqual(second_event.get("node"), "complete")

    def test_followup_stream_casual_query_fast_path(self):
        mock_direct = MagicMock()
        mock_direct.invoke.return_value = "I am at your service. How may I assist your research?"
        mock_followup = MagicMock()

        with patch("web_server.direct_chat_chain", mock_direct), \
             patch("web_server.stream_followup_turn", mock_followup):
            response = self.client.post(
                "/api/followup/stream",
                json={"user_query": "Hey, how are you?", "state": {}}
            )
            self.assertEqual(response.status_code, 200)

            mock_direct.invoke.assert_called_once_with({"user_query": "Hey, how are you?"})
            mock_followup.assert_not_called()

            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            self.assertGreaterEqual(len(data_lines), 2)
            ans_event = json.loads(data_lines[0].replace("data:", "").strip())
            self.assertEqual(ans_event.get("event"), "answer")
            self.assertEqual(ans_event.get("payload", {}).get("route"), "FAST_CHAT")

            comp_event = json.loads(data_lines[1].replace("data:", "").strip())
            self.assertEqual(comp_event.get("event"), "followup_complete")
            self.assertEqual(comp_event.get("payload", {}).get("route"), "FAST_CHAT")

    def test_followup_stream_substantive_query_calls_pipeline(self):
        mock_direct = MagicMock()
        mock_followup = MagicMock(return_value=[
            ("router", {"route": "LOCAL_QA", "reasoning": "Technical query", "search_query": ""}),
            ("answer", {"answer": "Surface codes have a 1% threshold.", "route": "LOCAL_QA", "citations": []}),
        ])

        with patch("web_server.direct_chat_chain", mock_direct), \
             patch("web_server.stream_followup_turn", mock_followup):
            response = self.client.post(
                "/api/followup/stream",
                json={"user_query": "Hi Thoth, explain fault tolerance in surface codes", "state": {}}
            )
            self.assertEqual(response.status_code, 200)

            mock_followup.assert_called_once()
            mock_direct.invoke.assert_not_called()

    def test_followup_stream_thinker_command_calls_pipeline(self):
        mock_direct = MagicMock()
        mock_followup = MagicMock(return_value=[
            ("router", {"route": "THINKER_REVIEW", "reasoning": "Popper review", "search_query": ""})
        ])

        with patch("web_server.direct_chat_chain", mock_direct), \
             patch("web_server.stream_followup_turn", mock_followup):
            response = self.client.post(
                "/api/followup/stream",
                json={"user_query": "/popper Check error model claims", "state": {}}
            )
            self.assertEqual(response.status_code, 200)

            mock_followup.assert_called_once()
            mock_direct.invoke.assert_not_called()

    def test_followup_stream_pipeline_completion_event_contract(self):
        mock_followup = MagicMock(return_value=[
            ("router", {"route": "LOCAL_QA", "reasoning": "Direct local lookup", "search_query": ""}),
            ("answer", {"answer": "Fault-tolerant threshold is ~1%.", "route": "LOCAL_QA", "citations": ["note-1"]}),
            ("followup_complete", {
                "user_query": "What is the threshold?",
                "answer": "Fault-tolerant threshold is ~1%.",
                "route": "LOCAL_QA",
                "citations": ["note-1"],
                "chat_turns": [{"turn": 1, "user_query": "What is the threshold?", "assistant_response": "Fault-tolerant threshold is ~1%."}],
                "conversation_summary": "Initial quantum research summary.",
                "follow_up_questions": ["What about topological codes?"],
                "report": "# Quantum Error Correction"
            })
        ])

        with patch("web_server.stream_followup_turn", mock_followup):
            response = self.client.post(
                "/api/followup/stream",
                json={"user_query": "What is the threshold?", "state": {}}
            )
            self.assertEqual(response.status_code, 200)

            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l.replace("data:", "").strip()) for l in data_lines]

            event_names = [e.get("event") for e in events]
            self.assertEqual(event_names, ["router", "answer", "followup_complete"])

            comp_payload = events[2].get("payload", {})
            self.assertEqual(comp_payload.get("route"), "LOCAL_QA")
            self.assertEqual(comp_payload.get("answer"), "Fault-tolerant threshold is ~1%.")
            self.assertEqual(len(comp_payload.get("chat_turns", [])), 1)
            self.assertEqual(comp_payload.get("conversation_summary"), "Initial quantum research summary.")
            self.assertEqual(comp_payload.get("follow_up_questions"), ["What about topological codes?"])
            self.assertEqual(comp_payload.get("report"), "# Quantum Error Correction")

    def test_followup_stream_pipeline_failure_does_not_emit_false_completion(self):
        def failing_generator(*args, **kwargs):
            yield ("router", {"route": "LOCAL_QA", "reasoning": "Lookup", "search_query": ""})
            raise RuntimeError("Pipeline failed mid-turn")

        with patch("web_server.stream_followup_turn", side_effect=failing_generator):
            response = self.client.post(
                "/api/followup/stream",
                json={"user_query": "Explain threshold failure", "state": {}}
            )
            self.assertEqual(response.status_code, 200)

            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l.replace("data:", "").strip()) for l in data_lines]

            event_names = [e.get("event") for e in events]
            self.assertIn("error", event_names)
            self.assertNotIn("followup_complete", event_names)

            error_event = next(e for e in events if e.get("event") == "error")
            self.assertIn("Pipeline failed mid-turn", error_event.get("payload", {}).get("error", ""))

class TestDirectChatErrorHandlingAndLogging(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_test_a_successful_direct_chat_marks_non_degraded(self):
        mock_direct = MagicMock()
        mock_direct.invoke.return_value = "Greetings! I am ready to conduct verified research on your topic."

        with patch("web_server.direct_chat_chain", mock_direct):
            response = self.client.post("/api/research/stream", json={"topic": "Hello Thoth"})
            self.assertEqual(response.status_code, 200)
            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l.replace("data:", "").strip()) for l in data_lines]

            chat_event = events[0]
            self.assertEqual(chat_event.get("node"), "direct_chat")
            self.assertFalse(chat_event.get("update", {}).get("fallback"))
            self.assertFalse(chat_event.get("update", {}).get("degraded"))
            self.assertFalse(chat_event.get("state", {}).get("fallback"))
            self.assertTrue(len(chat_event.get("state", {}).get("follow_up_questions", [])) > 0)

    def test_test_b_missing_credentials_triggers_fallback_and_logs(self):
        mock_direct = MagicMock()
        mock_direct.invoke.side_effect = ValueError("Did not find nvidia_api_key in environment. Please set NVIDIA_API_KEY.")

        with patch("web_server.direct_chat_chain", mock_direct), \
             self.assertLogs("ThothWebServer", level="ERROR") as cm:
            response = self.client.post("/api/research/stream", json={"topic": "Hi there"})
            self.assertEqual(response.status_code, 200)
            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l.replace("data:", "").strip()) for l in data_lines]

            chat_event = events[0]
            self.assertTrue(chat_event.get("update", {}).get("fallback"))
            self.assertTrue(chat_event.get("update", {}).get("degraded"))
            self.assertIn("ValueError", chat_event.get("update", {}).get("error", ""))
            self.assertEqual(chat_event.get("state", {}).get("follow_up_questions"), [])
            self.assertIn("Greetings! I am Thoth", chat_event.get("update", {}).get("answer", ""))

            self.assertTrue(any("Direct chat invocation failed" in log for log in cm.output))

    def test_test_c_timeout_connection_failure_no_research_pipeline(self):
        mock_direct = MagicMock()
        mock_direct.invoke.side_effect = TimeoutError("HTTP request timed out after 60.0s")
        mock_stream_research = MagicMock()

        with patch("web_server.direct_chat_chain", mock_direct), \
             patch("web_server.stream_research_pipeline", mock_stream_research):
            response = self.client.post("/api/research/stream", json={"topic": "Good morning"})
            self.assertEqual(response.status_code, 200)
            mock_stream_research.assert_not_called()

            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l.replace("data:", "").strip()) for l in data_lines]
            self.assertEqual(events[0].get("node"), "direct_chat")
            self.assertTrue(events[0].get("update", {}).get("degraded"))

    def test_test_d_rate_limit_provider_error_handled_gracefully(self):
        mock_direct = MagicMock()
        mock_direct.invoke.side_effect = RuntimeError("Rate limit exceeded 429 Too Many Requests: TPM quota reached")

        with patch("web_server.direct_chat_chain", mock_direct), \
             self.assertLogs("ThothWebServer", level="ERROR") as cm:
            response = self.client.post("/api/followup/stream", json={"user_query": "Hey", "state": {}})
            self.assertEqual(response.status_code, 200)

            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l.replace("data:", "").strip()) for l in data_lines]

            ans_event = events[0]
            comp_event = events[1]

            self.assertTrue(ans_event.get("payload", {}).get("fallback"))
            self.assertTrue(ans_event.get("payload", {}).get("degraded"))
            self.assertTrue(comp_event.get("payload", {}).get("fallback"))
            self.assertTrue(comp_event.get("payload", {}).get("degraded"))
            self.assertEqual(comp_event.get("payload", {}).get("follow_up_questions"), [])
            self.assertTrue(any("429 Too Many Requests" in log for log in cm.output))

    def test_test_e_chitchat_execution_failure_isolation(self):
        mock_router = MagicMock()
        mock_router.invoke.return_value = '{"route": "CHITCHAT", "reasoning": "Greeting", "search_query": ""}'
        mock_direct = MagicMock()
        mock_direct.invoke.side_effect = RuntimeError("Model provider 503 Service Unavailable")
        mock_hybrid_search = MagicMock()
        mock_qa = MagicMock()

        current_state = {
            "topic": "Quantum Error Correction",
            "report": "Initial report",
            "mindmap": {"nodes": [], "edges": []},
            "chat_turns": [],
            "conversation_summary": "",
            "cumulative_sources": []
        }

        with patch("backend.pipeline.router_chain", mock_router), \
             patch("backend.pipeline.direct_chat_chain", mock_direct), \
             patch("backend.memory.index.hybrid_search", mock_hybrid_search), \
             patch("backend.pipeline.mindmap_qa_chain", mock_qa), \
             self.assertLogs("ThothPipeline", level="ERROR") as cm:
            from backend.pipeline import stream_followup_turn
            gen = stream_followup_turn(current_state, user_query="Hello again")
            first_event = next(gen)
            self.assertEqual(first_event[0], "router")

            with self.assertRaises(RuntimeError) as ctx:
                next(gen)
            self.assertIn("503 Service Unavailable", str(ctx.exception))
            self.assertTrue(any("Direct chat chain execution failed" in log for log in cm.output))
            mock_hybrid_search.assert_not_called()
            mock_qa.invoke.assert_not_called()

        with patch("backend.pipeline.router_chain", mock_router), \
             patch("backend.pipeline.direct_chat_chain", mock_direct):
            response = self.client.post(
                "/api/followup/stream",
                json={"user_query": "Hello again", "state": current_state, "mode_override": "auto"}
            )
            self.assertEqual(response.status_code, 200)
            data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l.replace("data:", "").strip()) for l in data_lines]

            event_names = [e.get("event") for e in events]
            self.assertIn("error", event_names)
            self.assertNotIn("followup_complete", event_names)

    def test_test_f_both_http_endpoints_distinguish_degradation(self):
        mock_failing_direct = MagicMock()
        mock_failing_direct.invoke.side_effect = RuntimeError("Inference engine offline")

        with patch("web_server.direct_chat_chain", mock_failing_direct):
            res_research = self.client.post("/api/research/stream", json={"topic": "Hi"})
            self.assertEqual(res_research.status_code, 200)
            r_events = [json.loads(l.replace("data:", "").strip()) for l in res_research.text.split("\n") if l.startswith("data:")]
            self.assertTrue(r_events[0].get("update", {}).get("degraded"))
            self.assertTrue(r_events[0].get("update", {}).get("fallback"))

            res_followup = self.client.post("/api/followup/stream", json={"user_query": "Hello", "state": {}})
            self.assertEqual(res_followup.status_code, 200)
            f_events = [json.loads(l.replace("data:", "").strip()) for l in res_followup.text.split("\n") if l.startswith("data:")]
            self.assertTrue(f_events[0].get("payload", {}).get("degraded"))
            self.assertTrue(f_events[0].get("payload", {}).get("fallback"))
            self.assertTrue(f_events[1].get("payload", {}).get("degraded"))
            self.assertTrue(f_events[1].get("payload", {}).get("fallback"))

    def test_test_g_logging_safety_redacts_credentials(self):
        from backend.agents import sanitize_log_message

        self.assertNotIn("nvapi-secret123456789", sanitize_log_message("Failed with key nvapi-secret123456789"))
        self.assertIn("nvapi-***REDACTED***", sanitize_log_message("Failed with key nvapi-secret123456789"))

        self.assertNotIn("gsk_groqsecret12345", sanitize_log_message("Groq error with gsk_groqsecret12345"))
        self.assertIn("gsk_***REDACTED***", sanitize_log_message("Groq error with gsk_groqsecret12345"))

        self.assertNotIn("sk-openai123456789", sanitize_log_message("OpenAI key sk-openai123456789"))
        self.assertIn("sk-***REDACTED***", sanitize_log_message("OpenAI key sk-openai123456789"))

        self.assertNotIn("Bearer secret_token_xyz123", sanitize_log_message("Authorization: Bearer secret_token_xyz123"))
        self.assertIn("Bearer ***REDACTED***", sanitize_log_message("Authorization: Bearer secret_token_xyz123"))

        mock_leak_direct = MagicMock()
        mock_leak_direct.invoke.side_effect = RuntimeError("API error with key nvapi-live-super-secret-key-12345")

        with patch("web_server.direct_chat_chain", mock_leak_direct), \
             self.assertLogs("ThothWebServer", level="ERROR") as cm:
            self.client.post("/api/followup/stream", json={"user_query": "Hey", "state": {}})
            combined_logs = "\n".join(cm.output)
            self.assertNotIn("nvapi-live-super-secret-key-12345", combined_logs)
            self.assertIn("nvapi-***REDACTED***", combined_logs)

if __name__ == "__main__":
    unittest.main()
