import os
import shutil
import tempfile
import unittest

from backend.memory.db import init_db
from backend.memory.vault import Note
from backend.memory.graph import (
    add_edge,
    infer_edges_from_note,
    traverse,
    get_subgraph,
)


class TestMemoryGraph(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "graph_test.db")
        init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_edge_and_traverse_depth(self):
        # Build 5 notes graph with typed edges:
        # Note1 --cites--> Note2
        # Note1 --cites--> Note3
        # Note2 --contradicts--> Note4
        # Note3 --supports--> Note5
        add_edge("Note1", "cites", "Note2", confidence=0.95, db_path=self.db_path)
        add_edge("Note1", "cites", "Note3", confidence=0.90, db_path=self.db_path)
        add_edge("Note2", "contradicts", "Note4", confidence=0.80, db_path=self.db_path)
        add_edge("Note3", "supports", "Note5", confidence=0.85, db_path=self.db_path)

        # 1-hop traversal from Note1
        depth_1 = traverse("Note1", max_depth=1, db_path=self.db_path)
        self.assertEqual(sorted(depth_1), ["Note2", "Note3"])

        # 2-hop traversal from Note1
        depth_2 = traverse("Note1", max_depth=2, db_path=self.db_path)
        self.assertEqual(sorted(depth_2), ["Note2", "Note3", "Note4", "Note5"])

        # Filtered traversal: only cites
        cites_only = traverse("Note1", relation="cites", max_depth=2, db_path=self.db_path)
        self.assertEqual(sorted(cites_only), ["Note2", "Note3"])

        # Filtered traversal: contradicts from Note2
        contra_only = traverse("Note2", relation="contradicts", max_depth=1, db_path=self.db_path)
        self.assertEqual(contra_only, ["Note4"])

    def test_infer_edges_from_note(self):
        note = Note(
            note_id="quantum_core",
            note_type="topics",
            content="Mentions [[superconducting_circuits]] and [[error_syndromes]]."
        )
        inferred = infer_edges_from_note(note, default_relation="related", db_path=self.db_path)
        self.assertEqual(sorted(inferred), ["error_syndromes", "superconducting_circuits"])

        connected = traverse("quantum_core", max_depth=1, db_path=self.db_path)
        self.assertEqual(sorted(connected), ["error_syndromes", "superconducting_circuits"])

    def test_cycle_tolerance(self):
        # A -> B -> C -> A
        add_edge("A", "cites", "B", db_path=self.db_path)
        add_edge("B", "cites", "C", db_path=self.db_path)
        add_edge("C", "cites", "A", db_path=self.db_path)

        result = traverse("A", max_depth=5, db_path=self.db_path)
        self.assertEqual(sorted(result), ["B", "C"])


if __name__ == "__main__":
    unittest.main()
