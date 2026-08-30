import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.scholarly import SourceCandidate, snowball_literature_graph, _normalize_s2_id


def test_id_normalization():
    print("Testing _normalize_s2_id...")
    assert _normalize_s2_id("215755102") == "CorpusId:215755102"
    assert _normalize_s2_id("10.1038/s41586-020-0001") == "DOI:10.1038/s41586-020-0001"
    assert _normalize_s2_id("2308.12345") == "ARXIV:2308.12345"
    assert _normalize_s2_id("arXiv:2308.12345") == "ARXIV:2308.12345"
    assert _normalize_s2_id("doi:10.1038/test") == "DOI:10.1038/test"
    print("  ✓ ID Normalization passed.")


async def test_snowball_execution():
    print("Testing snowball_literature_graph with realistic seed papers...")
    seeds = [
        SourceCandidate(
            title="Attention Is All You Need",
            authors=["Vaswani et al."],
            abstract="Transformer architecture based on self-attention mechanisms.",
            url="https://arxiv.org/abs/1706.03762",
            doi="10.48550/arXiv.1706.03762",
            arxiv_id="1706.03762",
            paper_id=None,  # No raw S2 paper ID, tests DOI/ArXiv extraction
            source_api="arxiv"
        )
    ]
    
    snowballed = await snowball_literature_graph(seeds, max_recommendations=2, max_citations=2, max_references=2)
    print(f"  ✓ Snowballed {len(snowballed)} connected papers:")
    for idx, p in enumerate(snowballed[:5], 1):
        print(f"    [{idx}] {p.title[:65]}... (Rel: {p.relation}, API: {p.source_api})")
    assert isinstance(snowballed, list)


if __name__ == "__main__":
    test_id_normalization()
    asyncio.run(test_snowball_execution())
    print("\n✅ All snowballing tests passed.")
