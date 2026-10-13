import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from backend.scholarly import SourceCandidate
from backend.pipeline import search_node, scrape_node, verifier_node, snowball_node
from backend.orchestrator import concurrent_scrape_urls, stream_research_pipeline
from backend.dispatcher import Dispatcher


class TestSourceProvenanceAndEvidenceRetention(unittest.IsolatedAsyncioTestCase):
    """
    Prompt 15 Regression Suite:
    Validates end-to-end source metadata preservation, deterministic source identification,
    source-attributed extracted text retention, truth guard input construction, and failure handling.
    """

    def setUp(self):
        self.candidate_arxiv = SourceCandidate(
            title="Quantum Memory Architectures",
            authors=["Alice Physicist", "Bob Quantum"],
            abstract="We demonstrate a scalable quantum memory architecture with optical cavities.",
            url="https://arxiv.org/abs/2405.00001",
            doi="10.1038/s41586-024-00001",
            citation_count=18,
            published_date="2024-05-10",
            source_api="arxiv",
            arxiv_id="2405.00001",
            pmid=None,
        )

        self.candidate_pubmed = SourceCandidate(
            title="Clinical Cognitive Assessment via Structured Tasks",
            authors=["Carol Psychologist", "Dave Neuro"],
            abstract="Evaluation of working memory tasks across healthy controls and patient cohorts.",
            url="https://pubmed.ncbi.nlm.nih.gov/38800001/",
            doi="10.1016/j.neuro.2024.01.002",
            citation_count=35,
            published_date="2024-02-15",
            source_api="pubmed",
            arxiv_id=None,
            pmid="38800001",
        )

    # 1. Metadata preservation
    def test_search_node_preserves_full_source_metadata(self):
        """Authors, abstracts, dates, persistent identifiers, and provider survive ingestion into state."""
        with patch("backend.pipeline.search_scholarly_sources", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [self.candidate_arxiv, self.candidate_pubmed]

            state = {"topic": "Quantum & Cognitive State"}
            update = search_node(state)

            sources = update.get("cumulative_sources", [])
            self.assertEqual(len(sources), 2)

            src1 = sources[0]
            self.assertEqual(src1["title"], "Quantum Memory Architectures")
            self.assertEqual(src1["authors"], ["Alice Physicist", "Bob Quantum"])
            self.assertEqual(src1["abstract"], "We demonstrate a scalable quantum memory architecture with optical cavities.")
            self.assertEqual(src1["snippet"], src1["abstract"])
            self.assertEqual(src1["published_date"], "2024-05-10")
            self.assertEqual(src1["doi"], "10.1038/s41586-024-00001")
            self.assertEqual(src1["arxiv_id"], "2405.00001")
            self.assertEqual(src1["source_api"], "arxiv")
            self.assertEqual(src1["citation_count"], 18)
            self.assertEqual(src1["extracted_text"], "")
            self.assertEqual(src1["scrape_status"], "unscraped")
            self.assertIsNone(src1["scrape_error"])

            src2 = sources[1]
            self.assertEqual(src2["title"], "Clinical Cognitive Assessment via Structured Tasks")
            self.assertEqual(src2["authors"], ["Carol Psychologist", "Dave Neuro"])
            self.assertEqual(src2["abstract"], "Evaluation of working memory tasks across healthy controls and patient cohorts.")
            self.assertEqual(src2["pmid"], "38800001")
            self.assertEqual(src2["doi"], "10.1016/j.neuro.2024.01.002")
            self.assertEqual(src2["source_api"], "pubmed")
            self.assertEqual(src2["citation_count"], 35)

    # 2. Source identity
    def test_source_identity_deterministic_and_preserved(self):
        """Each retained record has a deterministic, unique source ID that can be reliably attributed."""
        with patch("backend.pipeline.search_scholarly_sources", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [self.candidate_arxiv, self.candidate_pubmed]

            update1 = search_node({"topic": "Topic A"})
            update2 = search_node({"topic": "Topic A"})

            ids1 = [s["id"] for s in update1["cumulative_sources"]]
            ids2 = [s["id"] for s in update2["cumulative_sources"]]

            self.assertEqual(ids1, ids2, "Deterministic IDs should match across identical runs")
            self.assertTrue(ids1[0].startswith("src-"))
            self.assertIn("quantum", ids1[0].lower())
            self.assertNotEqual(ids1[0], ids1[1])

    # 3. Successful extraction attached to source
    async def test_successful_extraction_stored_on_source_record(self):
        """Extracted text is stored directly on the corresponding source record with status success."""
        dispatcher = Dispatcher(max_concurrent=2, max_attempts=1, base_delay=0.01)

        async def mock_dispatcher_call(fn, *args, **kwargs):
            arg_dict = args[0] if args else kwargs
            return f"Full extracted paper text for {arg_dict.get('url')}"

        with patch.object(dispatcher, "call", side_effect=mock_dispatcher_call):
            content, new_sources = await concurrent_scrape_urls(["https://arxiv.org/abs/2405.00001"], dispatcher)

            self.assertEqual(len(new_sources), 1)
            src = new_sources[0]
            self.assertEqual(src["scrape_status"], "success")
            self.assertIn("Full extracted paper text", src["extracted_text"])
            self.assertIsNone(src["scrape_error"])

    # 4. Multiple sources attribution and non-swapping
    async def test_multiple_sources_attribution_preserved_without_swapping(self):
        """Text from multiple distinct sources is correctly attached to their respective records without merging or swapping."""
        url_a = "https://arxiv.org/abs/2405.00001"
        url_b = "https://pubmed.ncbi.nlm.nih.gov/38800001/"

        existing_sources = [
            {
                "id": "src-quantum_memory",
                "url": url_a,
                "title": "Quantum Memory",
                "abstract": "Quantum abstract",
                "extracted_text": "",
                "scrape_status": "unscraped"
            },
            {
                "id": "src-cognitive_assessment",
                "url": url_b,
                "title": "Cognitive Assessment",
                "abstract": "Cognitive abstract",
                "extracted_text": "",
                "scrape_status": "unscraped"
            }
        ]

        dispatcher = Dispatcher(max_concurrent=2, max_attempts=1, base_delay=0.01)

        async def mock_call(fn, *args, **kwargs):
            arg_dict = args[0] if args else kwargs
            u = arg_dict.get("url")
            if "arxiv" in u:
                return "EXCLUSIVE QUANTUM OPTICS CORPUS"
            return "EXCLUSIVE COGNITIVE NEUROSCIENCE CORPUS"

        with patch.object(dispatcher, "call", side_effect=mock_call):
            scraped_content, new_sources = await concurrent_scrape_urls([url_a, url_b], dispatcher)

            # Simulate orchestrator merge logic
            new_by_url = {s["url"]: s for s in new_sources}
            merged = []
            for s in existing_sources:
                s_copy = dict(s)
                if s["url"] in new_by_url:
                    s_copy["extracted_text"] = new_by_url[s["url"]]["extracted_text"]
                    s_copy["scrape_status"] = new_by_url[s["url"]]["scrape_status"]
                merged.append(s_copy)

            self.assertEqual(merged[0]["title"], "Quantum Memory")
            self.assertEqual(merged[0]["extracted_text"], "EXCLUSIVE QUANTUM OPTICS CORPUS")
            self.assertNotIn("COGNITIVE", merged[0]["extracted_text"])

            self.assertEqual(merged[1]["title"], "Cognitive Assessment")
            self.assertEqual(merged[1]["extracted_text"], "EXCLUSIVE COGNITIVE NEUROSCIENCE CORPUS")
            self.assertNotIn("QUANTUM", merged[1]["extracted_text"])

    # 5. Scraping failure honesty
    async def test_scraping_failure_represented_honestly(self):
        """A failed scrape is recorded as failed with error details, not masqueraded as successful evidence."""
        dispatcher = Dispatcher(max_concurrent=2, max_attempts=1, base_delay=0.01)

        async def mock_failing_call(fn, *args, **kwargs):
            return "Could not scrape URL: HTTP 403 Forbidden"

        with patch.object(dispatcher, "call", side_effect=mock_failing_call):
            content, new_sources = await concurrent_scrape_urls(["https://paywalled.com/paper"], dispatcher)

            self.assertEqual(len(new_sources), 1)
            src = new_sources[0]
            self.assertEqual(src["scrape_status"], "failed")
            self.assertEqual(src["extracted_text"], "")
            self.assertIn("403 Forbidden", src["scrape_error"])

    # 6. Aggregate compatibility
    async def test_aggregate_scraped_content_preserved_for_backward_compatibility(self):
        """The aggregate state['scraped_content'] continues to be produced with clear source demarcations."""
        dispatcher = Dispatcher(max_concurrent=2, max_attempts=1, base_delay=0.01)

        async def mock_call(fn, *args, **kwargs):
            arg_dict = args[0] if args else kwargs
            return f"Body text of {arg_dict.get('url')}"

        with patch.object(dispatcher, "call", side_effect=mock_call):
            content, new_sources = await concurrent_scrape_urls(["https://site-a.org", "https://site-b.org"], dispatcher)

            self.assertIn("--- Source: https://site-a.org ---", content)
            self.assertIn("--- Source: https://site-b.org ---", content)
            self.assertIn("Body text of https://site-a.org", content)

    # 7. Truth Guard receives attributed source text
    def test_verifier_node_supplies_retained_evidence_to_truth_guard(self):
        """Truth Guard receives source-attributed excerpts from extracted text and abstract, not empty strings."""
        sources = [
            {
                "id": "src-quantum_optics",
                "title": "Quantum Optics Experiment",
                "url": "https://nature.com/articles/123",
                "authors": ["Dr. Photon"],
                "abstract": "We trap single atoms in high-finesse optical resonators.",
                "extracted_text": "Experimental results show 99.8% fidelity for qubit entanglement across 50 nodes.",
                "scrape_status": "success",
                "doi": "10.1038/s41586-024-00123"
            }
        ]

        state = {
            "topic": "Atomic Entanglement",
            "report": "Single atoms achieved 99.8% fidelity.",
            "cumulative_sources": sources
        }

        captured_inputs = {}

        mock_verifier = MagicMock()
        def mock_verifier_invoke(inputs):
            captured_inputs.update(inputs)
            return '{"results": [{"claim": "Fidelity is 99.8%", "is_valid": true, "supporting_source_id": "src-quantum_optics"}]}'
        mock_verifier.invoke.side_effect = mock_verifier_invoke

        with patch("backend.pipeline.verifier_chain", mock_verifier):
            result = verifier_node(state)

            self.assertIn("sources", captured_inputs)
            sources_text = captured_inputs["sources"]

            self.assertIn("[src-quantum_optics]", sources_text)
            self.assertIn("Title: Quantum Optics Experiment", sources_text)
            self.assertIn("DOI: 10.1038/s41586-024-00123", sources_text)
            self.assertIn("99.8% fidelity for qubit entanglement", sources_text)
            self.assertIn("high-finesse optical resonators", sources_text)

    # 8. Missing evidence honestly reported to Truth Guard
    def test_verifier_node_reports_missing_evidence_honestly(self):
        """A source with failed/missing scrape and no abstract is explicitly marked as lacking substantive text."""
        sources = [
            {
                "id": "src-paywalled_source",
                "title": "Secret Study",
                "url": "https://paywall.com/paper",
                "authors": ["Anonymous"],
                "abstract": "",
                "extracted_text": "",
                "scrape_status": "failed",
                "scrape_error": "HTTP 403 Forbidden"
            }
        ]

        state = {
            "topic": "Secret Topics",
            "report": "Claim from secret study.",
            "cumulative_sources": sources
        }

        captured_inputs = {}

        mock_verifier = MagicMock()
        def mock_verifier_invoke(inputs):
            captured_inputs.update(inputs)
            return '{"results": []}'
        mock_verifier.invoke.side_effect = mock_verifier_invoke

        with patch("backend.pipeline.verifier_chain", mock_verifier):
            verifier_node(state)

            sources_text = captured_inputs["sources"]
            self.assertIn("[src-paywalled_source]", sources_text)
            self.assertIn("No substantive text or abstract available for this source", sources_text)
            self.assertIn("Scrape status: failed", sources_text)

    # 9. Scrape node attaches text to cumulative sources
    def test_scrape_node_attaches_extracted_text_to_records(self):
        """Synchronous scrape_node attaches extracted text and scrape status to matching sources."""
        sources = [
            {
                "id": "src-paper_x",
                "url": "https://example.com/paper_x",
                "title": "Paper X",
                "abstract": "Abstract X",
                "extracted_text": "",
                "scrape_status": "unscraped"
            }
        ]

        state = {
            "topic": "Paper X topic",
            "cumulative_sources": sources,
            "scrape_top_n": 5
        }

        mock_scrape = MagicMock()
        mock_scrape.invoke.return_value = "Extracted body text from paper X"
        with patch("backend.pipeline.scrape_url", mock_scrape):
            update = scrape_node(state)

            self.assertIn("scraped_content", update)
            self.assertIn("Extracted body text from paper X", update["scraped_content"])

            updated_sources = update["cumulative_sources"]
            self.assertEqual(len(updated_sources), 1)
            self.assertEqual(updated_sources[0]["scrape_status"], "success")
            self.assertEqual(updated_sources[0]["extracted_text"], "Extracted body text from paper X")
            self.assertIsNone(updated_sources[0]["scrape_error"])


if __name__ == "__main__":
    unittest.main()
