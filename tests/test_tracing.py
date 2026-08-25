import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from backend.telemetry import (
    enable_local_tracing,
    clear_local_traces,
    get_local_traces,
    DEEPEVAL_AVAILABLE
)
from backend.orchestrator import (
    stream_research_pipeline,
    run_research_pipeline,
    concurrent_scrape_urls,
    create_initial_state
)
from backend.pipeline import (
    search_node,
    writer_node,
    verifier_node,
    critic_node,
    mindmap_node,
    follow_up_node,
    route_followup_intent,
    stream_followup_turn
)
from backend.scholarly import (
    search_arxiv,
    search_semantic_scholar,
    search_openalex,
    search_tavily,
    SourceCandidate
)
from backend.memory.index import hybrid_search, index_note
from backend.memory.vault import write_note, Note
from backend.memory.db import init_db


@unittest.skipUnless(DEEPEVAL_AVAILABLE, "DeepEval is required for tracing tests")
class TestDeepEvalTracingIntegration(unittest.TestCase):
    """
    Offline local integration test suite verifying DeepEval @observe telemetry instrumentation
    across Thoth's agent, llm, tool, and retriever spans.
    """

    def setUp(self):
        enable_local_tracing()
        clear_local_traces()
        self.test_dir = tempfile.mkdtemp(prefix="thoth_trace_test_")
        self.db_path = os.path.join(self.test_dir, "test_store.db")
        self.vault_dir = os.path.join(self.test_dir, "vault")
        init_db(self.db_path)

    def tearDown(self):
        clear_local_traces()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_stream_research_pipeline_agent_and_nested_spans(self):
        """
        Executes stream_research_pipeline with mocked internal chains/tools
        and asserts that the parent AgentSpan contains nested LLM and Tool child spans.
        """
        mock_candidates = [
            SourceCandidate(
                title="Superconducting Qubits Overview",
                authors=["Alice"],
                abstract="Overview of transmon qubits.",
                url="https://arxiv.org/abs/2401.00001",
                doi="10.1000/1",
                citation_count=10,
                published_date="2024-01-01",
                source_api="arxiv",
                arxiv_id="2401.00001"
            )
        ]

        mock_writer = MagicMock()
        mock_writer.invoke.return_value = "Draft report on superconducting qubits."

        mock_verifier = MagicMock()
        mock_verifier.invoke.return_value = '{"results": [{"claim": "Qubits exist", "is_valid": true, "supporting_source_id": "src-superconducting_qubits_overview", "reason_if_failed": ""}]}'

        mock_critic = MagicMock()
        mock_critic.invoke.return_value = '{"overall_score": 9.0, "faithfulness": 9.0, "relevance": 9.0, "completeness": 9.0, "evidence_quality": 9.0, "clarity_and_coherence": 9.0, "strengths": ["Clear"], "areas_to_improve": [], "verdict": "Publish", "reasoning": "Solid"}'

        mock_mindmap = MagicMock()
        mock_mindmap.invoke.return_value = '{"nodes": [{"id": "root", "label": "Qubits"}], "edges": []}'

        mock_followup = MagicMock()
        mock_followup.invoke.return_value = '["What is coherence time?"]'

        mock_scrape = MagicMock()
        mock_scrape.invoke.return_value = "Scraped text about superconducting transmon circuits."

        with patch("backend.pipeline.search_scholarly_sources", return_value=mock_candidates), \
             patch("backend.pipeline.writer_chain", mock_writer), \
             patch("backend.pipeline.verifier_chain", mock_verifier), \
             patch("backend.pipeline.critic_chain", mock_critic), \
             patch("backend.pipeline.mindmap_extractor_chain", mock_mindmap), \
             patch("backend.pipeline.follow_up_chain", mock_followup), \
             patch("backend.orchestrator.scrape_url", mock_scrape):

            events = []
            for node_name, update, state in stream_research_pipeline(
                topic="Superconducting Qubits",
                scrape_top_n=1,
                min_score=7.0,
                max_retries=1
            ):
                events.append(node_name)

        self.assertIn("search", events)
        self.assertIn("writer", events)
        self.assertIn("verifier", events)
        self.assertIn("critic", events)
        self.assertIn("mindmap", events)
        self.assertIn("follow_up", events)

        # Retrieve offline in-memory traces
        traces = get_local_traces()
        self.assertGreaterEqual(len(traces), 1, "At least one trace should be captured.")

        # Find the root agent trace
        agent_trace = None
        for t in traces:
            root_spans = t.get("root_spans") if isinstance(t, dict) else getattr(t, "root_spans", [])
            for s in root_spans:
                s_name = s.get("name") if isinstance(s, dict) else getattr(s, "name", None)
                if s_name == "stream_research_pipeline":
                    agent_trace = (t, s)
                    break
            if agent_trace:
                break

        self.assertIsNotNone(agent_trace, "Parent AgentSpan for stream_research_pipeline was not found in traces.")
        trace_obj, root_span = agent_trace

        children = root_span.get("children") if isinstance(root_span, dict) else getattr(root_span, "children", [])
        child_names = [
            c.get("name") if isinstance(c, dict) else getattr(c, "name", None)
            for c in children
        ]

        # Verify child spans are present under the agent span
        self.assertIn("search_node", child_names)
        self.assertIn("concurrent_scrape_urls", child_names)
        self.assertIn("writer_node", child_names)
        self.assertIn("verifier_node", child_names)
        self.assertIn("critic_node", child_names)
        self.assertIn("mindmap_node", child_names)
        self.assertIn("follow_up_node", child_names)

    def test_hybrid_search_retriever_span_with_context(self):
        """
        Tests that hybrid_search creates a retriever span and populates its retrieval_context.
        """
        # Create and index two test notes
        write_note(
            note_id="note_transmon",
            note_type="concept",
            content="Transmon qubits reduce sensitivity to charge noise via large shunt capacitance.",
            frontmatter={"title": "Transmon Qubits", "tags": ["quantum", "hardware"]},
            vault_dir=self.vault_dir
        )
        write_note(
            note_id="note_fluxonium",
            note_type="concept",
            content="Fluxonium qubits offer large anharmonicity using Josephson junction arrays.",
            frontmatter={"title": "Fluxonium Qubits", "tags": ["quantum", "hardware"]},
            vault_dir=self.vault_dir
        )
        n1 = Note(
            note_id="note_transmon",
            note_type="concept",
            content="Transmon qubits reduce sensitivity to charge noise via large shunt capacitance.",
            frontmatter={"title": "Transmon Qubits", "tags": ["quantum", "hardware"]}
        )
        n2 = Note(
            note_id="note_fluxonium",
            note_type="concept",
            content="Fluxonium qubits offer large anharmonicity using Josephson junction arrays.",
            frontmatter={"title": "Fluxonium Qubits", "tags": ["quantum", "hardware"]}
        )
        index_note(n1, db_path=self.db_path)
        index_note(n2, db_path=self.db_path)

        # Mock sentence transformer embeddings
        import numpy as np
        dummy_emb = np.array([0.1] * 384, dtype=np.float32)
        with patch("backend.memory.index.get_embedding_model") as mock_emb_fn:
            mock_model = MagicMock()
            mock_model.encode.return_value = dummy_emb
            mock_emb_fn.return_value = mock_model

            results = hybrid_search(
                query="Transmon charge noise",
                top_k=2,
                db_path=self.db_path,
                vault_dir=self.vault_dir,
                model=mock_model
            )

        self.assertGreater(len(results), 0)

        traces = get_local_traces()
        retriever_span = None
        for t in traces:
            root_spans = t.get("root_spans") if isinstance(t, dict) else getattr(t, "root_spans", [])
            for s in root_spans:
                s_name = s.get("name") if isinstance(s, dict) else getattr(s, "name", None)
                if s_name == "hybrid_search":
                    retriever_span = s
                    break
            if retriever_span:
                break

        self.assertIsNotNone(retriever_span, "Retriever span for hybrid_search not found.")
        retrieval_ctx = (
            retriever_span.get("retrieval_context")
            if isinstance(retriever_span, dict)
            else getattr(retriever_span, "retrieval_context", [])
        )
        self.assertTrue(len(retrieval_ctx) > 0, "hybrid_search must set non-empty retrieval_context on its span.")
        self.assertTrue(any("Transmon" in c for c in retrieval_ctx))

    def test_intent_router_llm_span_and_schema_confinement(self):
        """
        Tests that route_followup_intent produces an LLM span and enforces schema confinement
        against malformed LLM output or unknown route types.
        """
        mock_router = MagicMock()

        # Test Case 1: Valid WEB_SEARCH route
        mock_router.invoke.return_value = '{"route": "WEB_SEARCH", "reasoning": "Need 2026 update", "search_query": "Quantum chips 2026"}'
        with patch("backend.pipeline.router_chain", mock_router):
            decision = route_followup_intent(
                topic="Quantum Computing",
                mindmap_summary="8 concepts",
                report_summary="Report text",
                user_query="What are 2026 developments?"
            )
            self.assertEqual(decision["route"], "WEB_SEARCH")
            self.assertEqual(decision["search_query"], "Quantum chips 2026")

        # Test Case 2: Malformed output / unknown route -> Fallback to LOCAL_QA
        mock_router.invoke.return_value = "<think>I should use a weird action</think> {\"route\": \"UNSUPPORTED_BRANCH\"}"
        with patch("backend.pipeline.router_chain", mock_router):
            decision2 = route_followup_intent(
                topic="Quantum Computing",
                mindmap_summary="8 concepts",
                report_summary="Report text",
                user_query="Explain the basics"
            )
            self.assertEqual(decision2["route"], "LOCAL_QA")

        # Verify LLM spans captured
        traces = get_local_traces()
        router_spans = []
        for t in traces:
            root_spans = t.get("root_spans") if isinstance(t, dict) else getattr(t, "root_spans", [])
            for s in root_spans:
                s_name = s.get("name") if isinstance(s, dict) else getattr(s, "name", None)
                if s_name == "route_followup_intent":
                    router_spans.append(s)

        self.assertGreaterEqual(len(router_spans), 2)

    def test_scholarly_search_tool_spans(self):
        """
        Tests that academic and web search functions generate tool spans.
        """
        import asyncio

        with patch("backend.scholarly._fetch_arxiv_raw", return_value="<xml></xml>"), \
             patch("backend.scholarly._fetch_semantic_scholar_raw", return_value={"data": []}), \
             patch("backend.scholarly._fetch_openalex_raw", return_value={"results": []}), \
             patch("backend.scholarly._fetch_tavily_sync", return_value=[]):

            async def run_tools():
                await search_arxiv("quantum", max_results=1)
                await search_semantic_scholar("quantum", max_results=1)
                await search_openalex("quantum", max_results=1)
                await search_tavily("quantum", max_results=1)

            asyncio.run(run_tools())

        traces = get_local_traces()
        captured_names = []
        for t in traces:
            root_spans = t.get("root_spans") if isinstance(t, dict) else getattr(t, "root_spans", [])
            for s in root_spans:
                s_name = s.get("name") if isinstance(s, dict) else getattr(s, "name", None)
                if s_name:
                    captured_names.append(s_name)

        self.assertIn("search_arxiv", captured_names)
        self.assertIn("search_semantic_scholar", captured_names)
        self.assertIn("search_openalex", captured_names)
        self.assertIn("search_tavily", captured_names)


if __name__ == "__main__":
    unittest.main()
