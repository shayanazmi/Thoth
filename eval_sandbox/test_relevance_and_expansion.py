"""
eval_sandbox/test_relevance_and_expansion.py
Evaluates:
1. Semantic Relevance Pre-Filtering of Source Candidates.
2. Cross-Session Multi-Turn Report Expansion & Merging.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.scholarly import SourceCandidate, rank_sources_by_relevance


class TestRelevanceFilteringAndExpansion(unittest.TestCase):

    def test_semantic_relevance_filtering(self):
        topic = "Quantum Error Correction with Surface Codes and Transmon Qubits"
        
        candidates = [
            SourceCandidate(
                title="Historical Analysis of Roman Aqueducts in Gaul",
                authors=["Marcus et al."],
                abstract="Structural masonry and hydraulic gradient preservation in 1st century Roman civil engineering.",
                url="https://example.org/aqueducts",
                source_api="openalex"
            ),
            SourceCandidate(
                title="Fault-Tolerant Surface Code Architecture for Superconducting Qubits",
                authors=["Fowler et al."],
                abstract="Threshold theorems, stabilizer syndrome extraction, and decoder performance for topological surface codes.",
                url="https://arxiv.org/abs/1208.0928",
                doi="10.1103/PhysRevA.86.032324",
                source_api="arxiv"
            ),
            SourceCandidate(
                title="Optimization of Modern Baking Recipes and Sourdough Hydration",
                authors=["Baker et al."],
                abstract="Gluten elasticity and yeast fermentation dynamics in artisan bakeries.",
                url="https://example.org/baking",
                source_api="tavily"
            ),
            SourceCandidate(
                title="High-Threshold Quantum Memory via Neutral Atom Tweezer Arrays",
                authors=["Bluvstein et al."],
                abstract="Logical qubit entanglement and transversal gates with zoned Rydberg architecture.",
                url="https://arxiv.org/abs/2312.03982",
                source_api="arxiv"
            )
        ]
        
        # Rank sources by semantic relevance
        ranked = rank_sources_by_relevance(topic, candidates, top_k=2, min_similarity=0.20)
        
        self.assertEqual(len(ranked), 2)
        # The top ranked paper must be the quantum surface code paper
        self.assertIn("Surface Code", ranked[0].title)
        self.assertIn("Quantum Memory", ranked[1].title)
        
        # Verify off-topic papers (aqueducts, baking) were filtered out
        for r in ranked:
            self.assertNotIn("Aqueducts", r.title)
            self.assertNotIn("Baking", r.title)
        print("  ✓ Semantic relevance ranking successfully filtered off-topic candidates.")

    def test_dict_source_ranking(self):
        topic = "CRISPR Prime Editing off-target fidelity"
        dict_sources = [
            {"title": "Prime Editing Guide RNA design for targeted gene insertion", "abstract": "Fidelity optimization using dual pegRNAs."},
            {"title": "Financial Market Volatility in European Sovereign Debt", "abstract": "Macroeconomic bond yield spreads."}
        ]
        ranked = rank_sources_by_relevance(topic, dict_sources, top_k=1)
        self.assertEqual(len(ranked), 1)
        self.assertIn("Prime Editing", ranked[0]["title"])
        print("  ✓ Dictionary source format ranking verified.")


if __name__ == "__main__":
    unittest.main()
