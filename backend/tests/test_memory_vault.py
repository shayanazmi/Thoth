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
    format_vault_context_with_contradictions,
)

class TestVaultAndMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.vault_dir = os.path.join(self.test_dir, "vault")
        self.db_path = os.path.join(self.test_dir, "test_store.db")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

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

    def test_init_db_idempotency_and_tables(self):
        conn = init_db(self.db_path)
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
        self.assertIn("notes", tables)
        self.assertIn("notes_fts", tables)
        self.assertIn("embeddings", tables)
        self.assertIn("edges", tables)

        conn2 = init_db(self.db_path)
        self.assertIsNotNone(conn2)

    def test_index_and_hybrid_search(self):
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

        kw_hits = search_keyword("CRISPR", top_k=3, db_path=self.db_path)
        self.assertIn("topic-crispr", kw_hits)

        sem_hits = search_semantic("self-governing robotic decision systems", top_k=3, db_path=self.db_path)
        self.assertIn("topic-agentic-ai", sem_hits)

        hybrid_hits = hybrid_search("quantum error correction qubits", top_k=3, db_path=self.db_path, vault_dir=self.vault_dir)
        self.assertTrue(len(hybrid_hits) > 0)
        self.assertEqual(hybrid_hits[0]["note_id"], "topic-quantum")
        self.assertIn("rrf_score", hybrid_hits[0])
        self.assertIn("superconducting qubits", hybrid_hits[0]["content"])

        gene_hits = hybrid_search("molecular DNA sequence alterations in genome", top_k=3, db_path=self.db_path, vault_dir=self.vault_dir)
        self.assertEqual(gene_hits[0]["note_id"], "topic-crispr")

    def test_graph_add_edge_and_traverse(self):
        init_db(self.db_path)

        add_edge("note-A", "cites", "note-B", confidence=0.9, db_path=self.db_path)
        add_edge("note-A", "cites", "note-C", confidence=0.85, db_path=self.db_path)
        add_edge("note-B", "contradicts", "note-D", confidence=0.7, db_path=self.db_path)
        add_edge("note-C", "supports", "note-E", confidence=0.95, db_path=self.db_path)
        add_edge("note-D", "part_of", "note-F", confidence=0.6, db_path=self.db_path)

        depth_1_all = traverse("note-A", max_depth=1, db_path=self.db_path)
        self.assertEqual(sorted(depth_1_all), ["note-B", "note-C"])

        depth_2_all = traverse("note-A", max_depth=2, db_path=self.db_path)
        self.assertEqual(sorted(depth_2_all), ["note-B", "note-C", "note-D", "note-E"])
        self.assertNotIn("note-F", depth_2_all)

        depth_3_all = traverse("note-A", max_depth=3, db_path=self.db_path)
        self.assertIn("note-F", depth_3_all)

        depth_2_contra = traverse("note-B", relation="contradicts", max_depth=2, db_path=self.db_path)
        self.assertEqual(depth_2_contra, ["note-D"])

        test_note = Note(
            note_id="note-origin",
            note_type="topics",
            content="Summary linking to [[target-x]] and [[target-y]]."
        )
        inferred = infer_edges_from_note(test_note, default_relation="related", db_path=self.db_path)
        self.assertEqual(sorted(inferred), ["target-x", "target-y"])
        traversed = traverse("note-origin", max_depth=1, db_path=self.db_path)
        self.assertEqual(sorted(traversed), ["target-x", "target-y"])

        subgraph = get_subgraph("note-A", max_depth=2, db_path=self.db_path)
        self.assertIn("note-A", subgraph["nodes"])
        self.assertIn("note-B", subgraph["nodes"])
        self.assertIn("note-D", subgraph["nodes"])
        self.assertTrue(len(subgraph["edges"]) >= 4)

    def test_note_dataclass_contract_and_attributes(self):
        note = Note(
            note_id="topic-quantum-error-correction",
            note_type="topics",
            content="# Quantum Error Correction\nSurface codes suppress physical errors.",
            frontmatter={"confidence": 0.98, "created": "2026-10-13T00:00:00Z"},
            file_path="/vault/topics/topic-quantum-error-correction.md"
        )
        self.assertEqual(note.note_id, "topic-quantum-error-correction")
        self.assertEqual(note.note_type, "topics")
        self.assertIn("Surface codes", note.content)
        self.assertEqual(note.frontmatter["confidence"], 0.98)
        self.assertEqual(note.file_path, "/vault/topics/topic-quantum-error-correction.md")

        self.assertFalse(hasattr(note, "get"))

        d = note.to_dict()
        self.assertEqual(d["note_id"], "topic-quantum-error-correction")
        self.assertEqual(d["type"], "topics")
        self.assertEqual(d["content"], note.content)
        self.assertEqual(d["frontmatter"], note.frontmatter)

    def test_format_vault_context_with_typed_note_instances(self):
        note1 = Note(
            note_id="note-theory",
            note_type="topics",
            content="Theoretical analysis of fault tolerance thresholds.",
            frontmatter={"confidence": 0.9}
        )
        note2 = Note(
            note_id="note-experiment",
            note_type="topics",
            content="Experimental validation on superconducting transmon processors.",
            frontmatter={"confidence": 0.95}
        )
        context_text, contradictions = format_vault_context_with_contradictions(
            [note1, note2],
            db_path=self.db_path
        )
        self.assertIn("--- Vault Note [note-theory]:", context_text)
        self.assertIn("Theoretical analysis of fault tolerance", context_text)
        self.assertIn("--- Vault Note [note-experiment]:", context_text)
        self.assertIn("Experimental validation on superconducting", context_text)
        self.assertEqual(contradictions, [])

    def test_format_vault_context_with_dictionaries_and_mixed_list(self):
        dict_note = {
            "note_id": "note-dict-only",
            "content": "Grounded findings from semantic hybrid search.",
            "type": "topics"
        }
        typed_note = Note(
            note_id="note-typed-only",
            note_type="topics",
            content="Grounded findings from direct vault retrieval.",
            frontmatter={"confidence": 1.0}
        )

        context_text, _ = format_vault_context_with_contradictions(
            [dict_note, typed_note],
            db_path=self.db_path
        )
        self.assertIn("--- Vault Note [note-dict-only]:", context_text)
        self.assertIn("--- Vault Note [note-typed-only]:", context_text)

        partial_dict = {"note_id": "note-partial", "content": None}
        context_text_partial, _ = format_vault_context_with_contradictions(
            [partial_dict],
            db_path=self.db_path
        )
        self.assertIn("--- Vault Note [note-partial]:", context_text_partial)

    def test_format_vault_context_contradiction_detection_with_typed_notes(self):
        note_alpha = Note(note_id="note-alpha", note_type="topics", content="Alpha assertion.")
        note_beta = Note(note_id="note-beta", note_type="topics", content="Beta assertion.")

        add_edge("note-alpha", "contradicts", "note-beta", confidence=0.88, db_path=self.db_path)

        context_text, contradictions = format_vault_context_with_contradictions(
            [note_alpha, note_beta],
            db_path=self.db_path
        )
        self.assertTrue(len(contradictions) >= 1)
        self.assertIn("[KNOWLEDGE GRAPH CONTRADICTION ALERT]", context_text)
        self.assertIn("Note [note-alpha] CONTRADICTS Note [note-beta]", context_text)

if __name__ == "__main__":
    unittest.main()
