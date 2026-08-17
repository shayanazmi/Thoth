import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.scholarly import (
    SourceCandidate,
    parse_arxiv_xml,
    parse_semantic_scholar_json,
    parse_openalex_json,
    _reconstruct_openalex_abstract,
    search_arxiv,
    search_semantic_scholar,
    search_openalex,
    search_tavily,
    search_scholarly_sources,
)
from backend.dispatcher import Dispatcher


SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title type="html">arXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <published>2024-01-15T10:00:00Z</published>
    <title>Agentic AI Workflows in Scientific Discovery</title>
    <summary>We present an autonomous agentic framework for scientific research.</summary>
    <author>
      <name>Alice Smith</name>
    </author>
    <author>
      <name>Bob Johnson</name>
    </author>
    <arxiv:doi>10.1234/arxiv.2401.12345</arxiv:doi>
    <link href="http://arxiv.org/abs/2401.12345v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""

SAMPLE_S2_JSON = {
    "data": [
        {
            "paperId": "s2_paper_1",
            "title": "Hierarchical Agents for LLM Reasoning",
            "abstract": "This study explores multi-agent hierarchical tree search.",
            "url": "https://www.semanticscholar.org/paper/s2_paper_1",
            "year": 2024,
            "citationCount": 85,
            "publicationDate": "2024-02-10",
            "authors": [{"authorId": "1", "name": "Charlie Lee"}, {"authorId": "2", "name": "Dana White"}],
            "externalIds": {"DOI": "10.1016/j.artint.2024.104000", "ArXiv": "2402.54321"}
        }
    ]
}

SAMPLE_OPENALEX_JSON = {
    "results": [
        {
            "id": "https://openalex.org/W123456789",
            "doi": "https://doi.org/10.1109/access.2025.123456",
            "title": "Autonomous Multi-Agent Architecture for Complex Problem Solving",
            "publication_date": "2025-01-01",
            "cited_by_count": 120,
            "abstract_inverted_index": {
                "Autonomous": [0],
                "agents": [1],
                "accelerate": [2],
                "scientific": [3],
                "workflows.": [4]
            },
            "primary_location": {
                "landing_page_url": "https://ieeexplore.ieee.org/document/123456"
            },
            "authorships": [
                {"author": {"display_name": "Eva Green"}}
            ],
            "ids": {
                "arxiv": "https://arxiv.org/abs/2501.99999"
            }
        }
    ]
}


class TestScholarlyModule(unittest.IsolatedAsyncioTestCase):

    def test_source_candidate_methods(self):
        candidate = SourceCandidate(
            title="Sample Title",
            authors=["Author One", "Author Two"],
            abstract="Sample abstract text for testing candidate snippet formatting.",
            url="https://example.com/paper.pdf",
            doi="10.1000/182",
            citation_count=42,
            published_date="2024-01-01",
            source_api="arxiv",
            arxiv_id="2401.00001"
        )
        data = candidate.to_dict()
        self.assertEqual(data["title"], "Sample Title")
        self.assertEqual(data["authors"], ["Author One", "Author Two"])
        self.assertEqual(data["citation_count"], 42)

        snippet = candidate.to_formatted_snippet()
        self.assertIn("Sample Title", snippet)
        self.assertIn("Author One, Author Two", snippet)
        self.assertIn("Citations: 42", snippet)
        self.assertIn("DOI: 10.1000/182", snippet)
        self.assertIn("arXiv: 2401.00001", snippet)

    def test_parse_arxiv_xml(self):
        candidates = parse_arxiv_xml(SAMPLE_ARXIV_XML)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.title, "Agentic AI Workflows in Scientific Discovery")
        self.assertEqual(c.authors, ["Alice Smith", "Bob Johnson"])
        self.assertEqual(c.url, "http://arxiv.org/pdf/2401.12345v1")
        self.assertEqual(c.arxiv_id, "2401.12345v1")
        self.assertEqual(c.published_date, "2024-01-15")
        self.assertEqual(c.doi, "10.1234/arxiv.2401.12345")
        self.assertEqual(c.source_api, "arxiv")

    def test_parse_semantic_scholar_json(self):
        candidates = parse_semantic_scholar_json(SAMPLE_S2_JSON)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.title, "Hierarchical Agents for LLM Reasoning")
        self.assertEqual(c.authors, ["Charlie Lee", "Dana White"])
        self.assertEqual(c.citation_count, 85)
        self.assertEqual(c.doi, "10.1016/j.artint.2024.104000")
        self.assertEqual(c.arxiv_id, "2402.54321")
        self.assertEqual(c.source_api, "semantic_scholar")

    def test_parse_openalex_json(self):
        candidates = parse_openalex_json(SAMPLE_OPENALEX_JSON)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.title, "Autonomous Multi-Agent Architecture for Complex Problem Solving")
        self.assertEqual(c.abstract, "Autonomous agents accelerate scientific workflows.")
        self.assertEqual(c.authors, ["Eva Green"])
        self.assertEqual(c.citation_count, 120)
        self.assertEqual(c.arxiv_id, "2501.99999")
        self.assertEqual(c.url, "https://ieeexplore.ieee.org/document/123456")
        self.assertEqual(c.source_api, "openalex")

    def test_reconstruct_openalex_abstract(self):
        inv = {"Hello": [0], "world": [1], "again": [2]}
        text = _reconstruct_openalex_abstract(inv)
        self.assertEqual(text, "Hello world again")

    async def test_search_arxiv_with_dispatcher(self):
        disp = Dispatcher(max_concurrent=2, max_attempts=2)
        with patch("backend.scholarly._fetch_arxiv_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = SAMPLE_ARXIV_XML
            results = await search_arxiv("test query", max_results=3, dispatcher=disp)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].source_api, "arxiv")
            mock_fetch.assert_called_once_with("test query", 3)

    async def test_search_semantic_scholar_error_handling(self):
        disp = Dispatcher(max_concurrent=2, max_attempts=2)
        with patch("backend.scholarly._fetch_semantic_scholar_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("429 Too Many Requests")
            results = await search_semantic_scholar("test query", max_results=3, dispatcher=disp)
            self.assertEqual(results, [])

    async def test_search_tavily_adapter(self):
        disp = Dispatcher(max_concurrent=2, max_attempts=2)
        sample_tavily_results = [
            {"title": "Web Result 1", "url": "https://example.org/news", "content": "News snippet"}
        ]
        with patch("backend.scholarly._fetch_tavily_sync") as mock_sync:
            mock_sync.return_value = sample_tavily_results
            results = await search_tavily("test web query", max_results=1, dispatcher=disp)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Web Result 1")
            self.assertEqual(results[0].source_api, "tavily")

    async def test_search_scholarly_sources_aggregation_and_dedup(self):
        disp = Dispatcher(max_concurrent=3, max_attempts=2)

        cand_arxiv = SourceCandidate(
            title="Shared Paper Title",
            authors=["Alice"],
            abstract="Arxiv abstract",
            url="https://arxiv.org/abs/2401.00001",
            doi="10.1000/1",
            source_api="arxiv"
        )
        cand_s2 = SourceCandidate(
            title="Shared Paper Title",
            authors=["Alice"],
            abstract="S2 abstract",
            url="https://semanticscholar.org/paper/1",
            doi="10.1000/1",
            source_api="semantic_scholar"
        )
        cand_openalex = SourceCandidate(
            title="Distinct OpenAlex Paper",
            authors=["Bob"],
            abstract="OpenAlex abstract",
            url="https://openalex.org/w2",
            doi="10.1000/2",
            source_api="openalex"
        )

        with patch("backend.scholarly.search_arxiv", new_callable=AsyncMock) as mock_arxiv, \
             patch("backend.scholarly.search_semantic_scholar", new_callable=AsyncMock) as mock_s2, \
             patch("backend.scholarly.search_openalex", new_callable=AsyncMock) as mock_oa, \
             patch("backend.scholarly.search_tavily", new_callable=AsyncMock) as mock_tavily:

            mock_arxiv.return_value = [cand_arxiv]
            mock_s2.return_value = [cand_s2]
            mock_oa.return_value = [cand_openalex]
            mock_tavily.return_value = []

            results = await search_scholarly_sources("Agentic AI", max_results=5, min_scholarly_results=2, dispatcher=disp)
            # cand_arxiv and cand_s2 share DOI / title, so they deduplicate to 1
            # plus cand_openalex = 2 unique candidates
            self.assertEqual(len(results), 2)
            titles = [r.title for r in results]
            self.assertIn("Shared Paper Title", titles)
            self.assertIn("Distinct OpenAlex Paper", titles)
            mock_tavily.assert_not_called()

    async def test_search_scholarly_sources_fallback_to_tavily(self):
        disp = Dispatcher(max_concurrent=3, max_attempts=2)

        cand_tavily = SourceCandidate(
            title="Fallback Web Title",
            abstract="Web snippet",
            url="https://news.com/agentic",
            source_api="tavily"
        )

        with patch("backend.scholarly.search_arxiv", new_callable=AsyncMock) as mock_arxiv, \
             patch("backend.scholarly.search_semantic_scholar", new_callable=AsyncMock) as mock_s2, \
             patch("backend.scholarly.search_openalex", new_callable=AsyncMock) as mock_oa, \
             patch("backend.scholarly.search_tavily", new_callable=AsyncMock) as mock_tavily:

            mock_arxiv.return_value = []
            mock_s2.return_value = []
            mock_oa.return_value = []
            mock_tavily.return_value = [cand_tavily]

            results = await search_scholarly_sources("obscure niche topic", max_results=3, min_scholarly_results=2, dispatcher=disp)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Fallback Web Title")
            self.assertEqual(results[0].source_api, "tavily")
            mock_tavily.assert_called_once()

    def test_search_node_scholarly_primary(self):
        from backend.pipeline import search_node

        cand1 = SourceCandidate(
            title="Scholarly Paper A",
            authors=["Dr. A"],
            abstract="Abstract of Paper A",
            url="https://arxiv.org/pdf/2401.11111",
            doi="10.1000/a",
            source_api="arxiv"
        )
        cand2 = SourceCandidate(
            title="Scholarly Paper B",
            authors=["Dr. B"],
            abstract="Abstract of Paper B",
            url="https://openalex.org/w/22222",
            doi="10.1000/b",
            source_api="openalex"
        )

        with patch("backend.pipeline.search_scholarly_sources", new_callable=AsyncMock) as mock_scholarly:
            mock_scholarly.return_value = [cand1, cand2]

            state = {"topic": "Deep Learning Optimization"}
            update = search_node(state)

            self.assertIn("search_results", update)
            self.assertIn("cumulative_sources", update)
            self.assertIn("Scholarly Paper A", update["search_results"])
            self.assertEqual(len(update["cumulative_sources"]), 2)
            self.assertEqual(update["cumulative_sources"][0]["source_api"], "arxiv")
            self.assertEqual(update["cumulative_sources"][1]["source_api"], "openalex")

    def test_search_node_fallback_to_web_agent(self):
        from backend.pipeline import search_node

        mock_agent_res = {
            "messages": [
                MagicMock(content="Web agent response citing https://techcrunch.com/article1", type="ai")
            ]
        }
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = mock_agent_res

        with patch("backend.pipeline.search_scholarly_sources", new_callable=AsyncMock) as mock_scholarly, \
             patch("backend.pipeline.build_search_agent", return_value=mock_agent):

            # Scholarly returns empty list -> triggers fallback to search_agent
            mock_scholarly.return_value = []

            state = {"topic": "Latest Silicon Valley Venture Capital Funding"}
            update = search_node(state)

            self.assertIn("search_results", update)
            self.assertIn("techcrunch.com", update["search_results"])
            self.assertTrue(any("techcrunch.com" in s["url"] for s in update["cumulative_sources"]))
            mock_agent.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
