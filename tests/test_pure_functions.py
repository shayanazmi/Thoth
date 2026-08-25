import unittest
from backend.pipeline import (
    _slugify as pipeline_slugify,
    count_tokens as pipeline_count_tokens,
    truncate_text_to_tokens as pipeline_truncate_tokens,
    fit_context_to_token_budget,
    _extract_domain,
    _extract_urls_from_text,
)
from backend.memory.session import (
    count_tokens as session_count_tokens,
    truncate_text_to_tokens as session_truncate_tokens,
)
from backend.orchestrator import (
    create_initial_state,
    extract_atomic_claims,
)
from backend.memory.vault import (
    Note,
    extract_links,
    _validate_claims_citations,
)
from backend.memory.index import (
    _sanitize_fts_query,
)
from backend.scholarly import (
    SourceCandidate,
    _reconstruct_openalex_abstract,
    parse_arxiv_xml,
    parse_semantic_scholar_json,
    parse_openalex_json,
)
from backend.agents import (
    strip_chain_of_thought,
    safe_extract_json,
)


class TestPipelinePureFunctions(unittest.TestCase):
    """Pure unit tests for backend/pipeline.py utilities without mocks."""

    def test_slugify_expected_input(self):
        self.assertEqual(pipeline_slugify("Quantum Computing 101"), "quantum_computing_101")
        self.assertEqual(pipeline_slugify("Agentic-AI & LLMs!"), "agentic-ai_llms")

    def test_slugify_edge_cases(self):
        # Empty string fallback
        self.assertEqual(pipeline_slugify(""), "note")
        self.assertEqual(pipeline_slugify("   "), "note")
        # Pure special characters without word/dash/underscore chars
        self.assertEqual(pipeline_slugify("!@#$%^&*()+=~"), "note")
        # Boundary length truncation
        long_title = "a" * 100
        self.assertEqual(len(pipeline_slugify(long_title, max_len=30)), 30)

    def test_slugify_malformed_input(self):
        # Multiple contiguous underscores
        self.assertEqual(pipeline_slugify("___hello____world___"), "hello_world")
        # Unicode characters replaced by underscore
        res = pipeline_slugify("Café & Résumé 2026")
        self.assertIn("caf", res)
        self.assertNotIn(" ", res)

    def test_extract_domain_expected_input(self):
        self.assertEqual(_extract_domain("https://arxiv.org/abs/2401.12345"), "arxiv.org")
        self.assertEqual(_extract_domain("https://www.nature.com/articles/s41586-024"), "nature.com")

    def test_extract_domain_edge_cases(self):
        self.assertEqual(_extract_domain(""), "")
        self.assertEqual(_extract_domain("https://subdomain.domain.co.uk/path/file.html"), "subdomain.domain.co.uk")

    def test_extract_domain_malformed_input(self):
        # Plain non-URL string without scheme (has empty netloc)
        self.assertEqual(_extract_domain("not_a_valid_url"), "")
        # Incomplete scheme
        self.assertEqual(_extract_domain("http:///"), "")

    def test_extract_urls_from_text_expected_input(self):
        text = "Check out https://arxiv.org/abs/1 and http://semanticscholar.org/paper/2 for details."
        urls = _extract_urls_from_text(text)
        self.assertEqual(urls, ["https://arxiv.org/abs/1", "http://semanticscholar.org/paper/2"])

    def test_extract_urls_from_text_edge_cases(self):
        self.assertEqual(_extract_urls_from_text(""), [])
        self.assertEqual(_extract_urls_from_text("No links present in this text."), [])
        # Deduplication preserving order
        text = "Links: https://example.com/one and https://example.com/one again."
        self.assertEqual(_extract_urls_from_text(text), ["https://example.com/one"])

    def test_extract_urls_from_text_malformed_and_punctuation(self):
        # Trailing punctuation like period, comma, colon, quotes
        text = "Visit 'https://example.com/test.', (https://example.com/parens), and https://example.com/comma,"
        urls = _extract_urls_from_text(text)
        self.assertEqual(urls, ["https://example.com/test", "https://example.com/parens", "https://example.com/comma"])

    def test_fit_context_to_token_budget_expected(self):
        topic = "Quantum Teleportation"
        user_query = "What is the fidelity limit?"
        context = "CONTEXT BLOCK: " + "Superconducting qubits fidelity records. " * 30
        summary = "SUMMARY: " + "Initial experiments showed 99.9% gate fidelity. " * 10
        chat_turns = [
            {"turn": 1, "user_query": "Q1", "assistant_response": "A1 " * 40},
            {"turn": 2, "user_query": "Q2", "assistant_response": "A2 " * 40},
        ]

        trimmed_ctx, trimmed_sum, recent_turns = fit_context_to_token_budget(
            topic=topic,
            context_block=context,
            summary=summary,
            chat_turns=chat_turns,
            user_query=user_query,
            max_tokens=600
        )

        total_tokens = (
            pipeline_count_tokens(f"Topic: {topic}\nUser Query: {user_query}")
            + pipeline_count_tokens(trimmed_ctx)
            + pipeline_count_tokens(trimmed_sum)
            + pipeline_count_tokens(recent_turns)
        )
        self.assertLessEqual(total_tokens, 600)
        self.assertTrue(len(trimmed_ctx) > 0)
        self.assertTrue(len(trimmed_sum) > 0)

    def test_fit_context_to_token_budget_edge_and_tight_ceiling(self):
        # Empty context and empty turns
        trimmed_ctx, trimmed_sum, recent_turns = fit_context_to_token_budget(
            topic="AI",
            context_block="",
            summary="",
            chat_turns=[],
            user_query="Hello",
            max_tokens=1000
        )
        self.assertEqual(trimmed_ctx, "")
        self.assertEqual(trimmed_sum, "")
        self.assertEqual(recent_turns, "")

        # Very tight ceiling (remaining budget <= 200 tokens)
        trimmed_ctx2, trimmed_sum2, recent_turns2 = fit_context_to_token_budget(
            topic="A very long topic string " * 10,
            context_block="Some context " * 50,
            summary="Some summary " * 20,
            chat_turns=[{"turn": 1, "user_query": "q", "assistant_response": "a" * 100}],
            user_query="A very detailed user query " * 10,
            max_tokens=150
        )
        # Should gracefully cap context, summary, and drop recent turns
        self.assertEqual(recent_turns2, "")
        self.assertLessEqual(pipeline_count_tokens(trimmed_ctx2), 200)
        self.assertLessEqual(pipeline_count_tokens(trimmed_sum2), 100)


class TestTokenCountingDuplicationParity(unittest.TestCase):
    """
    CRITICAL CONTRACT: Asserts that pipeline.py's and memory/session.py's
    count_tokens and truncate_text_to_tokens implementations produce identical
    outputs on all inputs, guarding against silent drift across duplicated utilities.
    """

    def test_count_tokens_identical_behavior(self):
        test_inputs = [
            "",
            "Hello world",
            "The quick brown fox jumps over the lazy dog.",
            "Quantum error correction using surface codes and cat qubits.\n\n--- Source: https://arxiv.org/abs/2401.12345 ---\nDetailed results.",
            "Special characters: !@#$%^&*()_+-=[]{}|;':\",./<>?`~",
            "Multi-byte Unicode: 科学研究 and 🚀🤖🔬 and café résumé",
            "Long paragraph: " + ("Synthetic benchmark text for agent evaluation. " * 100),
        ]

        for text in test_inputs:
            p_count = pipeline_count_tokens(text)
            s_count = session_count_tokens(text)
            self.assertEqual(
                p_count,
                s_count,
                f"count_tokens divergence on input '{text[:30]}...': pipeline={p_count} vs session={s_count}"
            )

    def test_count_tokens_none_and_edge_inputs(self):
        self.assertEqual(pipeline_count_tokens(None), 0)
        self.assertEqual(session_count_tokens(None), 0)
        self.assertEqual(pipeline_count_tokens(""), 0)
        self.assertEqual(session_count_tokens(""), 0)

    def test_truncate_tokens_identical_behavior(self):
        sample_corpus = (
            "Section 1: Executive Summary.\n\n"
            "Autonomous agent workflows require rigorous verification loops.\n\n"
            "--- Source: https://arxiv.org/abs/2401.00001 ---\n"
            "We present benchmark evaluations across 500 scientific tasks.\n\n"
            "--- Source: https://arxiv.org/abs/2401.00002 ---\n"
            "Multi-modal feedback reduces hallucinations by 42%.\n\n"
            "Section 2: Concluding Remarks."
        )

        test_budgets = [0, -5, 1, 5, 10, 25, 50, 100, 500, 1000]

        for budget in test_budgets:
            p_trunc = pipeline_truncate_tokens(sample_corpus, budget)
            s_trunc = session_truncate_tokens(sample_corpus, budget)
            self.assertEqual(
                p_trunc,
                s_trunc,
                f"truncate_text_to_tokens divergence at budget={budget}:\nPipeline:\n'{p_trunc}'\nSession:\n'{s_trunc}'"
            )

    def test_truncate_tokens_boundary_and_edge_inputs(self):
        for budget in [-1, 0, 10]:
            self.assertEqual(pipeline_truncate_tokens("", budget), "")
            self.assertEqual(session_truncate_tokens("", budget), "")
            self.assertEqual(pipeline_truncate_tokens(None, budget), "")
            self.assertEqual(session_truncate_tokens(None, budget), "")


class TestOrchestratorPureFunctions(unittest.TestCase):
    """Pure unit tests for backend/orchestrator.py state initialization and claim extraction."""

    def test_create_initial_state_expected(self):
        state = create_initial_state(
            topic="Neuromorphic Computing",
            role="lead AI architect",
            tone="technical",
            language="German",
            scrape_top_n=4,
            min_score=8.0,
            max_retries=3
        )
        self.assertIsInstance(state, dict)
        self.assertEqual(state["topic"], "Neuromorphic Computing")
        self.assertEqual(state["role"], "lead AI architect")
        self.assertEqual(state["tone"], "technical")
        self.assertEqual(state["language"], "German")
        self.assertEqual(state["scrape_top_n"], 4)
        self.assertEqual(state["min_score"], 8.0)
        self.assertEqual(state["max_retries"], 3)
        self.assertEqual(state["attempt"], 0)
        self.assertEqual(state["score"], 0.0)
        self.assertEqual(state["mindmap"], {"nodes": [], "edges": []})
        self.assertEqual(state["cumulative_sources"], [])
        self.assertEqual(state["chat_turns"], [])

    def test_create_initial_state_defaults_and_boundaries(self):
        state = create_initial_state(topic="")
        self.assertEqual(state["topic"], "")
        self.assertEqual(state["role"], "senior academic researcher")
        self.assertEqual(state["tone"], "formal and analytical")
        self.assertEqual(state["language"], "English")
        self.assertEqual(state["scrape_top_n"], 2)
        self.assertEqual(state["min_score"], 6.5)
        self.assertEqual(state["max_retries"], 2)

    def test_extract_atomic_claims_expected(self):
        source_ids = ["src-quantum_algorithms", "src-superconducting_qubits"]
        verification_results = [
            {
                "claim": "Shor's algorithm provides exponential speedup for integer factorization.",
                "is_valid": True,
                "supporting_source_id": "src-quantum_algorithms"
            },
            {
                "claim": "Transmon qubits suffer from charge noise sensitivity.",
                "is_valid": True,
                "supporting_source_id": "src-superconducting_qubits"
            }
        ]

        claims = extract_atomic_claims(
            draft="Draft report text...",
            source_ids=source_ids,
            verification_results=verification_results
        )
        self.assertEqual(len(claims), 2)
        self.assertIn("- Shor's algorithm provides exponential speedup for integer factorization. [[src-quantum_algorithms]]", claims)
        self.assertIn("- Transmon qubits suffer from charge noise sensitivity. [[src-superconducting_qubits]]", claims)

    def test_extract_atomic_claims_drops_invalid_and_unattributed(self):
        source_ids = ["src-valid_source"]
        verification_results = [
            {
                "claim": "Valid cited claim",
                "is_valid": True,
                "supporting_source_id": "src-valid_source"
            },
            {
                "claim": "Valid but missing source attribution claim",
                "is_valid": True,
                "supporting_source_id": ""  # Unattributed
            },
            {
                "claim": "False or contradicted claim",
                "is_valid": False,  # Invalid
                "supporting_source_id": "src-valid_source"
            },
            {
                "claim": "Claim citing nonexistent source ID",
                "is_valid": True,
                "supporting_source_id": "src-unknown_hallucinated_source"
            }
        ]

        claims = extract_atomic_claims(
            draft="Draft text",
            source_ids=source_ids,
            verification_results=verification_results
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0], "- Valid cited claim [[src-valid_source]]")

    def test_extract_atomic_claims_edge_cases(self):
        # Empty sources list
        self.assertEqual(extract_atomic_claims("Draft", [], []), [])
        # None verification results
        self.assertEqual(extract_atomic_claims("Draft", ["src-1"], None), [])
        # Empty verification results list
        self.assertEqual(extract_atomic_claims("Draft", ["src-1"], []), [])

    def test_extract_atomic_claims_normalization_resilience(self):
        # Supporting source ID with brackets [[src-paper]] or hyphen/underscore variations
        source_ids = ["src-neural_network_scaling"]
        verification_results = [
            {
                "claim": "Loss scales as a power law with compute.",
                "is_valid": True,
                "supporting_source_id": "[[src-neural_network_scaling]]"  # Has markdown brackets
            },
            {
                "claim": "Batch size scales with critical batch size.",
                "is_valid": True,
                "supporting_source_id": "src-neural-network-scaling"  # Hyphen vs underscore
            }
        ]
        claims = extract_atomic_claims(
            draft="Draft text",
            source_ids=source_ids,
            verification_results=verification_results
        )
        self.assertEqual(len(claims), 2)
        self.assertTrue(all("[[src-neural_network_scaling]]" in c for c in claims))


class TestMemoryVaultPureFunctions(unittest.TestCase):
    """Pure unit tests for Note serialization, link extraction, and citation validation in vault.py."""

    def test_note_to_dict_expected(self):
        note = Note(
            note_id="topic-quantum",
            note_type="topics",
            content="# Quantum Overview\nBody content.",
            frontmatter={"confidence": 0.95, "sources": ["src-q1"]},
            file_path="/vault/topics/topic-quantum.md"
        )
        d = note.to_dict()
        self.assertEqual(d["note_id"], "topic-quantum")
        self.assertEqual(d["type"], "topics")
        self.assertEqual(d["content"], "# Quantum Overview\nBody content.")
        self.assertEqual(d["frontmatter"]["confidence"], 0.95)
        self.assertEqual(d["file_path"], "/vault/topics/topic-quantum.md")

    def test_note_to_dict_defaults(self):
        note = Note(note_id="src-1", note_type="sources", content="Biblio")
        d = note.to_dict()
        self.assertEqual(d["note_id"], "src-1")
        self.assertEqual(d["type"], "sources")
        self.assertEqual(d["frontmatter"], {})
        self.assertIsNone(d["file_path"])

    def test_extract_links_expected(self):
        content = "Claims: [[src-paper_1]] and [[src-paper_2]] linked to [[topic-quantum]]."
        links = extract_links(content)
        self.assertEqual(links, ["src-paper_1", "src-paper_2", "topic-quantum"])

    def test_extract_links_edge_cases(self):
        self.assertEqual(extract_links(""), [])
        self.assertEqual(extract_links(None), [])
        self.assertEqual(extract_links("No wikilinks here."), [])
        # Deduplication preserving first seen order
        content = "[[src-1]] followed by [[src-2]] and [[src-1]] again."
        self.assertEqual(extract_links(content), ["src-1", "src-2"])

    def test_extract_links_malformed_patterns(self):
        # Nested brackets, empty brackets, and malformed tags
        content = "Invalid [[unclosed and [[]] and [[  ]] and [[valid_link]] and normal [markdown](url)"
        links = extract_links(content)
        self.assertEqual(links, ["valid_link"])

    def test_validate_claims_citations_expected(self):
        valid_content = """# Topic Note

## Claims
- First verified finding [[src-paper_1]]
- Second verified finding [[src-paper_2]]

## Discussion
General text without citations is allowed in other sections.
"""
        # Should not raise exception
        _validate_claims_citations("topic-test", valid_content)

    def test_validate_claims_citations_edge_cases(self):
        # Content without claims section
        _validate_claims_citations("topic-test", "# Pure Overview\nNo claims section here.")
        _validate_claims_citations("topic-test", "")
        _validate_claims_citations("topic-test", None)
        # Empty claims section
        _validate_claims_citations("topic-test", "# Topic\n\n## Claims\n\n## Next Section")

    def test_validate_claims_citations_uncited_claim_raises_value_error(self):
        invalid_content = """# Topic Note

## Claims
- Valid cited claim [[src-paper_1]]
- Rogue uncited claim without wikilink at the end

## Next Section
"""
        with self.assertRaises(ValueError) as ctx:
            _validate_claims_citations("topic-invalid", invalid_content)
        
        err_msg = str(ctx.exception)
        self.assertIn("Uncited claim in note 'topic-invalid'", err_msg)
        self.assertIn("must end with a [[source-note-id]] citation", err_msg)
        self.assertIn("Rogue uncited claim", err_msg)


class TestMemoryIndexPureFunctions(unittest.TestCase):
    """Pure unit tests for SQLite FTS query sanitization in index.py."""

    def test_sanitize_fts_query_expected(self):
        self.assertEqual(_sanitize_fts_query("quantum computing"), '"quantum" "computing"')
        self.assertEqual(_sanitize_fts_query("agentic AI 2026"), '"agentic" "AI" "2026"')

    def test_sanitize_fts_query_edge_cases(self):
        self.assertEqual(_sanitize_fts_query(""), '""')
        self.assertEqual(_sanitize_fts_query("   "), '""')
        self.assertEqual(_sanitize_fts_query("!@#$%^&*()+="), '""')

    def test_sanitize_fts_query_malformed_and_sql_injection(self):
        # Malformed punctuation & quotes
        self.assertEqual(_sanitize_fts_query('query "with" \'nested\' `quotes`'), '"query" "with" "nested" "quotes"')
        # SQL Injection attempt
        injection = "test' OR '1'='1; DROP TABLE notes; --"
        sanitized = _sanitize_fts_query(injection)
        self.assertEqual(sanitized, '"test" "OR" "1" "1" "DROP" "TABLE" "notes"')


class TestScholarlyPureFunctions(unittest.TestCase):
    """Pure unit tests for bibliographic models, abstract reconstruction, and XML/JSON parsers in scholarly.py."""

    def test_source_candidate_to_dict_and_snippet(self):
        cand = SourceCandidate(
            title="Transformer Scaling Laws",
            authors=["J. Kaplan", "S. McCandlish"],
            abstract="We investigate empirical scaling laws for language model performance.",
            url="https://arxiv.org/abs/2001.08361",
            doi="10.48550/arXiv.2001.08361",
            citation_count=1500,
            published_date="2020-01-23",
            source_api="arxiv",
            arxiv_id="2001.08361"
        )
        d = cand.to_dict()
        self.assertEqual(d["title"], "Transformer Scaling Laws")
        self.assertEqual(d["citation_count"], 1500)
        self.assertEqual(d["source_api"], "arxiv")

        snippet = cand.to_formatted_snippet()
        self.assertIn("Title: Transformer Scaling Laws", snippet)
        self.assertIn("Authors: J. Kaplan, S. McCandlish", snippet)
        self.assertIn("Citations: 1500", snippet)
        self.assertIn("DOI: 10.48550/arXiv.2001.08361", snippet)
        self.assertIn("arXiv: 2001.08361", snippet)
        self.assertIn("Abstract / Snippet: We investigate empirical scaling laws", snippet)

    def test_source_candidate_defaults(self):
        cand = SourceCandidate(title="Bare Minimum Title")
        d = cand.to_dict()
        self.assertEqual(d["title"], "Bare Minimum Title")
        self.assertEqual(d["authors"], [])
        self.assertIsNone(d["citation_count"])
        self.assertIsNone(d["doi"])
        self.assertIsNone(d["arxiv_id"])

        snippet = cand.to_formatted_snippet()
        self.assertIn("Title: Bare Minimum Title", snippet)
        self.assertIn("Authors: Unknown Authors", snippet)
        self.assertNotIn("DOI:", snippet)
        self.assertNotIn("arXiv:", snippet)

    def test_reconstruct_openalex_abstract_expected(self):
        inverted = {
            "Large": [0],
            "language": [1],
            "models": [2],
            "exhibit": [3],
            "reasoning.": [4]
        }
        text = _reconstruct_openalex_abstract(inverted)
        self.assertEqual(text, "Large language models exhibit reasoning.")

    def test_reconstruct_openalex_abstract_edge_cases(self):
        self.assertEqual(_reconstruct_openalex_abstract(None), "")
        self.assertEqual(_reconstruct_openalex_abstract({}), "")

    def test_reconstruct_openalex_abstract_malformed_and_unordered(self):
        # Inverted index with multi-position words and shuffled keys
        inverted = {
            "world": [3],
            "hello": [0, 2],
            "brave": [1]
        }
        text = _reconstruct_openalex_abstract(inverted)
        self.assertEqual(text, "hello brave hello world")

    def test_parse_arxiv_xml_expected(self):
        sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.99999v1</id>
    <title>Quantum Neural Networks for Chemistry</title>
    <summary>We benchmark VQE algorithms on noisy intermediate-scale quantum devices.</summary>
    <author><name>Dr. Jane Doe</name></author>
    <author><name>Dr. John Ray</name></author>
    <arxiv:doi>10.1000/qchem.2024</arxiv:doi>
    <published>2024-01-20T12:00:00Z</published>
    <link href="http://arxiv.org/pdf/2401.99999v1" rel="related" type="application/pdf"/>
  </entry>
</feed>"""
        candidates = parse_arxiv_xml(sample_xml)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.title, "Quantum Neural Networks for Chemistry")
        self.assertEqual(c.authors, ["Dr. Jane Doe", "Dr. John Ray"])
        self.assertEqual(c.url, "http://arxiv.org/pdf/2401.99999v1")
        self.assertEqual(c.arxiv_id, "2401.99999v1")
        self.assertEqual(c.doi, "10.1000/qchem.2024")
        self.assertEqual(c.source_api, "arxiv")
        self.assertEqual(c.published_date, "2024-01-20")

    def test_parse_arxiv_xml_edge_and_malformed(self):
        # Empty feed
        self.assertEqual(parse_arxiv_xml("<feed></feed>"), [])
        # Empty string
        self.assertEqual(parse_arxiv_xml(""), [])
        # Corrupt XML
        self.assertEqual(parse_arxiv_xml("<feed><unclosed>garbage XML"), [])

    def test_parse_semantic_scholar_json_expected(self):
        sample_s2 = {
            "data": [
                {
                    "title": "Chain-of-Thought Prompting in LLMs",
                    "authors": [{"name": "Jason Wei"}, {"name": "Xuezhi Wang"}],
                    "abstract": "Generating a chain of thought improves reasoning.",
                    "url": "https://www.semanticscholar.org/paper/cot-123",
                    "citationCount": 3500,
                    "publicationDate": "2022-01-28",
                    "externalIds": {"DOI": "10.48550/arxiv.2201.11903", "ArXiv": "2201.11903"}
                }
            ]
        }
        candidates = parse_semantic_scholar_json(sample_s2)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.title, "Chain-of-Thought Prompting in LLMs")
        self.assertEqual(c.authors, ["Jason Wei", "Xuezhi Wang"])
        self.assertEqual(c.citation_count, 3500)
        self.assertEqual(c.doi, "10.48550/arxiv.2201.11903")
        self.assertEqual(c.arxiv_id, "2201.11903")
        self.assertEqual(c.source_api, "semantic_scholar")

    def test_parse_semantic_scholar_json_edge_and_malformed(self):
        self.assertEqual(parse_semantic_scholar_json({}), [])
        self.assertEqual(parse_semantic_scholar_json({"data": []}), [])
        # Item with None values and missing fields
        corrupt_data = {
            "data": [
                {"title": None},
                {"title": "Paper Without Fields", "authors": None, "externalIds": None}
            ]
        }
        candidates = parse_semantic_scholar_json(corrupt_data)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].title, "Untitled")
        self.assertEqual(candidates[1].title, "Paper Without Fields")
        self.assertEqual(candidates[1].authors, [])

    def test_parse_openalex_json_expected(self):
        sample_oa = {
            "results": [
                {
                    "title": "Direct Preference Optimization",
                    "authorships": [{"author": {"display_name": "Rafael Rafailov"}}],
                    "abstract_inverted_index": {"DPO": [0], "aligns": [1], "models": [2]},
                    "doi": "https://doi.org/10.48550/arXiv.2305.18290",
                    "cited_by_count": 800,
                    "publication_date": "2023-05-29",
                    "primary_location": {"landing_page_url": "https://arxiv.org/abs/2305.18290"},
                    "ids": {"arxiv": "https://arxiv.org/abs/2305.18290"}
                }
            ]
        }
        candidates = parse_openalex_json(sample_oa)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.title, "Direct Preference Optimization")
        self.assertEqual(c.authors, ["Rafael Rafailov"])
        self.assertEqual(c.abstract, "DPO aligns models")
        self.assertEqual(c.citation_count, 800)
        self.assertEqual(c.doi, "https://doi.org/10.48550/arXiv.2305.18290")
        self.assertEqual(c.arxiv_id, "2305.18290")
        self.assertEqual(c.source_api, "openalex")

    def test_parse_openalex_json_edge_and_malformed(self):
        self.assertEqual(parse_openalex_json({}), [])
        self.assertEqual(parse_openalex_json({"results": []}), [])
        # Results with nulls
        corrupt_oa = {
            "results": [
                {"title": None},
                {
                    "title": "Valid Title",
                    "authorships": None,
                    "primary_location": None,
                    "abstract_inverted_index": None,
                    "ids": None
                }
            ]
        }
        candidates = parse_openalex_json(corrupt_oa)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].title, "Untitled")
        self.assertEqual(candidates[1].title, "Valid Title")
        self.assertEqual(candidates[1].authors, [])
        self.assertEqual(candidates[1].abstract, "")


class TestAgentsPureFunctions(unittest.TestCase):
    """Pure unit tests for LLM output sanitization and resilient JSON extraction in agents.py."""

    def test_strip_chain_of_thought_expected(self):
        raw_text = (
            "<think>\n"
            "The user is asking for quantum hardware analysis.\n"
            "I should structure the response into sections.\n"
            "</think>\n\n"
            "### 1. Quantum Processing Units\n"
            "Superconducting qubits operate at 15 mK."
        )
        cleaned = strip_chain_of_thought(raw_text)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("The user is asking", cleaned)
        self.assertTrue(cleaned.startswith("### 1. Quantum Processing Units"))

    def test_strip_chain_of_thought_preamble_removal(self):
        raw_text = (
            "Let me outline the master synthesis report for this topic.\n"
            "I will write the introduction followed by evidence.\n\n"
            "# Neuromorphic Computing Architecture\n\n"
            "Spiking neural networks provide event-driven execution."
        )
        cleaned = strip_chain_of_thought(raw_text)
        self.assertNotIn("Let me outline", cleaned)
        self.assertNotIn("I will write", cleaned)
        self.assertTrue(cleaned.startswith("# Neuromorphic Computing Architecture"))

    def test_strip_chain_of_thought_edge_cases(self):
        self.assertEqual(strip_chain_of_thought(""), "")
        self.assertEqual(strip_chain_of_thought(None), "")
        plain_text = "Just a direct paragraph with no think tags or headings."
        self.assertEqual(strip_chain_of_thought(plain_text), plain_text)

    def test_safe_extract_json_expected_dict_and_list(self):
        # Direct JSON dict
        res_dict = safe_extract_json('{"key": "value", "count": 42}')
        self.assertEqual(res_dict, {"key": "value", "count": 42})

        # Direct JSON list
        res_list = safe_extract_json('["item_1", "item_2", "item_3"]')
        self.assertEqual(res_list, ["item_1", "item_2", "item_3"])

    def test_safe_extract_json_markdown_codeblocks(self):
        # Fenced ```json ... ``` block
        fenced_text = """Here is the extracted analysis:
```json
{
  "route": "WEB_SEARCH",
  "reasoning": "Need recent benchmark data.",
  "search_query": "mamba vs transformer 2026"
}
```
Hope this helps!"""
        extracted = safe_extract_json(fenced_text)
        self.assertEqual(extracted.get("route"), "WEB_SEARCH")
        self.assertEqual(extracted.get("search_query"), "mamba vs transformer 2026")

    def test_safe_extract_json_edge_cases(self):
        self.assertIsNone(safe_extract_json(""))
        self.assertIsNone(safe_extract_json("   "))
        self.assertIsNone(safe_extract_json(None))
        # Custom default
        self.assertEqual(safe_extract_json("", default={"default": True}), {"default": True})
        self.assertEqual(safe_extract_json("Not JSON at all", default=[]), [])
        # Already parsed python structures
        self.assertEqual(safe_extract_json({"already": "parsed"}), {"already": "parsed"})
        self.assertEqual(safe_extract_json([1, 2, 3]), [1, 2, 3])

    def test_safe_extract_json_partial_array_salvage(self):
        # Unclosed JSON array from an LLM token limit cutoff
        truncated_array = """Thinking: Here are the verification results.
[
  {"claim": "Claim 1 is verified.", "is_valid": true, "reason_if_failed": "", "supporting_source_id": "src-1"},
  {"claim": "Claim 2 is verified.", "is_valid": true, "reason_if_failed": "", "supporting_source_id": "src-2"},
  {"claim": "Claim 3 was in progress...
"""
        salvaged = safe_extract_json(truncated_array, default=None)
        self.assertIsNotNone(salvaged)
        self.assertIn("results", salvaged)
        self.assertEqual(len(salvaged["results"]), 2)
        self.assertEqual(salvaged["results"][0]["claim"], "Claim 1 is verified.")
        self.assertEqual(salvaged["results"][1]["claim"], "Claim 2 is verified.")


if __name__ == "__main__":
    unittest.main()
