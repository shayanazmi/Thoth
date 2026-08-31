"""
Integrity verification test suite for Protected Research Material:
'handling api limit like feynman/'
"""

import os
import unittest


class TestProtectedFeynmanDirectory(unittest.TestCase):
    """Verifies that the protected architectural reference material remains intact."""

    def setUp(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.protected_dir = os.path.join(
            self.project_root, "handling api limit like feynman"
        )

    def test_protected_directory_exists(self):
        self.assertTrue(
            os.path.exists(self.protected_dir),
            "Protected directory 'handling api limit like feynman/' was moved or deleted!",
        )
        self.assertTrue(
            os.path.isdir(self.protected_dir),
            "'handling api limit like feynman/' is not a directory!",
        )

    def test_all_five_reference_files_exist_and_non_empty(self):
        expected_files = [
            "launch.ts",
            "notes.md",
            "researcher.md",
            "runtime.ts",
            "verifier.md",
        ]
        actual_files = os.listdir(self.protected_dir)

        for filename in expected_files:
            self.assertIn(
                filename,
                actual_files,
                f"Missing protected file: {filename}",
            )
            file_path = os.path.join(self.protected_dir, filename)
            self.assertGreater(
                os.path.getsize(file_path),
                0,
                f"Protected file {filename} is empty!",
            )


if __name__ == "__main__":
    unittest.main()
