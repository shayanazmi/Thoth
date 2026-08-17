import os
import shutil
import tempfile
import unittest

from backend.memory.vault import (
    write_note,
    read_note,
    list_notes,
    extract_links,
    Note,
)
from backend.memory.db import init_db, get_connection
from backend.memory.index import (
    index_note,
    search_keyword,
    search_semantic,
    hybrid_search,
)
from backend.memory.graph import (
    add_edge,
    infer_edges_from_note,
    traverse,
    get_subgraph,
)


class TestVaultAndMemory(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.vault_dir = os.path.join(self.test_dir, "vault")
        self.db_path = os.path.join(self.test_dir, "test_store.db")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Vault Unit Tests
    # -------------------------------------------------------------------------

    def test_extract_links(self):
        content = "Here is a claim referencing [[source-arxiv-2401]] and [[topic-agentic-ai]] and another [[source-arxiv-2401]]."
        links = extract_links(content)
        self.assertEqual(links, ["source-arxiv-2401", "topic-agentic-ai"])

    def test_write_and_read_note_valid_citation(self):
        valid_content = """# Agentic AI in Radiology

## Overview
Autonomous agents are transforming clinical imaging.

## Claims
- Agentic frameworks reduce radiologist fatigue by 34% [[source-nature-med-2024]]
- Multi-modal verification guards against hallucinations [[source-arxiv-2501]]
"""
        note_path = write_note(
            note_id="topic-agentic-radiology",
            note_type="topics",
            content=valid_content,
            frontmatter={"confidence": 0.95, "created": "2026-08-17T00:00:00Z"},
            vault_dir=self.vault_dir
        )

        self.assertTrue(os.path.isfile(note_path))

        # Read the note back
        note = read_note("topic-agentic-radiology", vault_dir=self.vault_dir)
        self.assertEqual(note.note_id, "topic-agentic-radiology")
        self.assertEqual(note.note_type, "topics")
        self.assertEqual(note.frontmatter["confidence"], 0.95)
        self.assertIn("source-nature-med-2024", note.frontmatter["sources"])
        self.assertIn("Agentic AI in Radiology", note.content)

    def test_write_note_uncited_claim_raises_error(self):
        invalid_content = """# Deep Learning Optimization

## Claims
- Learning rate warmup is universally required for transformer convergence
"""
        with self.assertRaises(ValueError) as ctx:
            write_note(
                note_id="topic-uncited-dl",
                note_type="topics",
                content=invalid_content,
                vault_dir=self.vault_dir
            )

        self.assertIn("Uncited claim in note", str(ctx.exception))
        self.assertIn("must end with a [[source-note-id]] citation", str(ctx.exception))

    def test_list_notes_and_filtering(self):
        write_note("topic-one", "topics", "Overview [[src-1]]", vault_dir=self.vault_dir)
        write_note("topic-two", "topics", "Overview [[src-2]]", vault_dir=self.vault_dir)
        write_note("entity-dr-smith", "entities", "Bio [[src-3]]", vault_dir=self.vault_dir)
        write_note("src-1", "sources", "Biblio info", vault_dir=self.vault_dir)

        all_notes = list_notes(vault_dir=self.vault_dir)
        self.assertEqual(len(all_notes), 4)
        self.assertIn("topic-one", all_notes)
        self.assertIn("entity-dr-smith", all_notes)

        topic_notes = list_notes(note_type="topics", vault_dir=self.vault_dir)
        self.assertEqual(len(topic_notes), 2)
        self.assertIn("topic-one", topic_notes)
        self.assertIn("topic-two", topic_notes)
        self.assertNotIn("entity-dr-smith", topic_notes)

    # -------------------------------------------------------------------------
    # 2. Database Schema Tests
    # -------------------------------------------------------------------------

    def test_init_db_idempotency_and_tables(self):
        conn = init_db(self.db_path)
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
        self.assertIn("notes", tables)
        self.assertIn("notes_fts", tables)
        self.assertIn("embeddings", tables)
        self.assertIn("edges", tables)

        # Call again to confirm idempotency
        conn2 = init_db(self.db_path)
        self.assertIsNotNone(conn2)

    # -------------------------------------------------------------------------
    # 3. Indexing & Hybrid Search Tests
    # -------------------------------------------------------------------------

    def test_index_and_hybrid_search(self):
        # 1. Populate vault with 6 distinct domain notes
        notes_data = [
            ("topic-quantum", "topics", "Quantum Computing advances using superconducting qubits and quantum error correction [[src-q1]]"),
            ("topic-crispr", "topics", "CRISPR-Cas9 gene editing mechanisms for targeted genomic modifications [[src-c1]]"),
            ("topic-agentic-ai", "topics", "Autonomous AI agents executing multi-step decision loops with planning and tool use [[src-a1]]"),
            ("topic-transformer", "topics", "Self-attention mechanism and multi-head attention in transformer language models [[src-t1]]"),
            ("topic-climate", "topics", "Global carbon capture technology and atmospheric greenhouse gas mitigation strategies [[src-cl1]]"),
            ("topic-neuroscience", "topics", "Neural synaptic plasticity and hippocampal memory consolidation dynamics [[src-n1]]"),
        ]

        for nid, ntype, body in notes_data:
            write_note(nid, ntype, body, vault_dir=self.vault_dir)
            note_obj = read_note(nid, vault_dir=self.vault_dir)
            index_note(note_obj, db_path=self.db_path)

        # 2. Test exact keyword search
        kw_hits = search_keyword("CRISPR", top_k=3, db_path=self.db_path)
        self.assertIn("topic-crispr", kw_hits)

        # 3. Test semantic paraphrased search (query without exact match words)
        sem_hits = search_semantic("self-governing robotic decision systems", top_k=3, db_path=self.db_path)
        self.assertIn("topic-agentic-ai", sem_hits)

        # 4. Test hybrid search with reciprocal rank fusion
        hybrid_hits = hybrid_search("quantum error correction qubits", top_k=3, db_path=self.db_path, vault_dir=self.vault_dir)
        self.assertTrue(len(hybrid_hits) > 0)
        self.assertEqual(hybrid_hits[0]["note_id"], "topic-quantum")
        self.assertIn("rrf_score", hybrid_hits[0])
        self.assertIn("superconducting qubits", hybrid_hits[0]["content"])

        # 5. Semantic search for genetic modification
        gene_hits = hybrid_search("molecular DNA sequence alterations in genome", top_k=3, db_path=self.db_path, vault_dir=self.vault_dir)
        self.assertEqual(gene_hits[0]["note_id"], "topic-crispr")

    # -------------------------------------------------------------------------
    # 4. Knowledge Graph Traversal Tests
    # -------------------------------------------------------------------------

    def test_graph_add_edge_and_traverse(self):
        init_db(self.db_path)

        # Graph topology:
        # A --cites--> B
        # A --cites--> C
        # B --contradicts--> D
        # C --supports--> E
        # D --part_of--> F (depth 3 from A)

        add_edge("note-A", "cites", "note-B", confidence=0.9, db_path=self.db_path)
        add_edge("note-A", "cites", "note-C", confidence=0.85, db_path=self.db_path)
        add_edge("note-B", "contradicts", "note-D", confidence=0.7, db_path=self.db_path)
        add_edge("note-C", "supports", "note-E", confidence=0.95, db_path=self.db_path)
        add_edge("note-D", "part_of", "note-F", confidence=0.6, db_path=self.db_path)

        # Depth 1 from note-A
        depth_1_all = traverse("note-A", max_depth=1, db_path=self.db_path)
        self.assertEqual(sorted(depth_1_all), ["note-B", "note-C"])

        # Depth 2 from note-A
        depth_2_all = traverse("note-A", max_depth=2, db_path=self.db_path)
        self.assertEqual(sorted(depth_2_all), ["note-B", "note-C", "note-D", "note-E"])
        self.assertNotIn("note-F", depth_2_all)

        # Depth 3 from note-A
        depth_3_all = traverse("note-A", max_depth=3, db_path=self.db_path)
        self.assertIn("note-F", depth_3_all)

        # Filtered traversal: only follows "contradicts"
        depth_2_contra = traverse("note-B", relation="contradicts", max_depth=2, db_path=self.db_path)
        self.assertEqual(depth_2_contra, ["note-D"])

        # Test infer_edges_from_note
        test_note = Note(
            note_id="note-origin",
            note_type="topics",
            content="Summary linking to [[target-x]] and [[target-y]]."
        )
        inferred = infer_edges_from_note(test_note, default_relation="related", db_path=self.db_path)
        self.assertEqual(sorted(inferred), ["target-x", "target-y"])
        traversed = traverse("note-origin", max_depth=1, db_path=self.db_path)
        self.assertEqual(sorted(traversed), ["target-x", "target-y"])

        # Test get_subgraph
        subgraph = get_subgraph("note-A", max_depth=2, db_path=self.db_path)
        self.assertIn("note-A", subgraph["nodes"])
        self.assertIn("note-B", subgraph["nodes"])
        self.assertIn("note-D", subgraph["nodes"])
        self.assertTrue(len(subgraph["edges"]) >= 4)


if __name__ == "__main__":
    unittest.main()
