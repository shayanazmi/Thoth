import unittest
import tempfile
import os
import datetime
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage
from backend.agents import verifier_chain, FactVerificationReport, VerificationResult, safe_extract_json
from backend.orchestrator import extract_atomic_claims
from backend.memory.vault import write_note, audit_vault_notes_citations
from langchain_core.runnables import RunnableSequence


class TestVerifierChain(unittest.TestCase):
    @patch.object(RunnableSequence, "invoke")
    def test_verifier_chain_mocked(self, mock_invoke):
        # Fake JSON response from LLM matching FactVerificationReport schema with supporting_source_id
        fake_json_response = """{
  "results": [
    {
      "claim": "Quantum computing utilizes superposition.",
      "is_valid": true,
      "reason_if_failed": "",
      "supporting_source_id": "src-quantum_foundations"
    },
    {
      "claim": "Quantum computers were invented in 1820.",
      "is_valid": false,
      "reason_if_failed": "Quantum computing concepts emerged in the 1980s, not 1820.",
      "supporting_source_id": ""
    }
  ]
}"""
        mock_invoke.return_value = fake_json_response

        fake_sources = "Source material: Quantum computing developed in late 20th century."
        fake_report = "Report: Quantum computing utilizes superposition. Quantum computers were invented in 1820."

        # Execute chain with fake inputs
        raw_output = verifier_chain.invoke({
            "sources": fake_sources,
            "report": fake_report,
            "current_date": "August 17, 2026"
        })

        mock_invoke.assert_called_once()

        parsed = safe_extract_json(raw_output)
        self.assertIsNotNone(parsed, "Extracted JSON should not be None")
        self.assertIn("results", parsed)

        report_obj = FactVerificationReport(**parsed)
        self.assertEqual(len(report_obj.results), 2)
        self.assertTrue(report_obj.results[0].is_valid)
        self.assertEqual(report_obj.results[0].supporting_source_id, "src-quantum_foundations")
        self.assertFalse(report_obj.results[1].is_valid)
        self.assertEqual(report_obj.results[1].claim, "Quantum computers were invented in 1820.")
        self.assertEqual(report_obj.results[1].supporting_source_id, "")

    def test_extract_atomic_claims_direct_attribution_no_round_robin(self):
        """
        Verify that claims are mapped strictly to their verified supporting_source_id,
        and not assigned via index rotation. Unattributed or invalid claims are dropped.
        """
        source_ids = ["src-neutral_atom_tweezer", "src-superconducting_transmon"]

        # Claim 1 is supported by Source 2 (transmon), NOT Source 1
        # Claim 2 is supported by Source 1 (neutral atom), NOT Source 2
        # Claim 3 is valid but has no supporting_source_id (should be dropped)
        # Claim 4 is invalid (should be dropped)
        verification_results = [
            {
                "claim": "Transmon qubits utilize superconducting Josephson junctions.",
                "is_valid": True,
                "reason_if_failed": "",
                "supporting_source_id": "src-superconducting_transmon"
            },
            {
                "claim": "Neutral atom qubits are trapped and shuttled using optical tweezers.",
                "is_valid": True,
                "reason_if_failed": "",
                "supporting_source_id": "src-neutral_atom_tweezer"
            },
            {
                "claim": "Silicon spin qubits operate at cryogenic temperatures.",
                "is_valid": True,
                "reason_if_failed": "",
                "supporting_source_id": ""  # Missing attribution
            },
            {
                "claim": "Quantum computers were invented in 1820.",
                "is_valid": False,
                "reason_if_failed": "Historically incorrect.",
                "supporting_source_id": ""
            }
        ]

        draft_text = "Sample draft text..."
        claims = extract_atomic_claims(
            draft=draft_text,
            source_ids=source_ids,
            verification_results=verification_results
        )

        # 1. Exactly 2 claims should be written (Claim 1 and Claim 2)
        self.assertEqual(len(claims), 2)

        # 2. Claim 1 points to Source 2 (superconducting_transmon), NOT Source 1
        self.assertIn("[[src-superconducting_transmon]]", claims[0])
        self.assertNotIn("[[src-neutral_atom_tweezer]]", claims[0])

        # 3. Claim 2 points to Source 1 (neutral_atom_tweezer), NOT Source 2
        self.assertIn("[[src-neutral_atom_tweezer]]", claims[1])
        self.assertNotIn("[[src-superconducting_transmon]]", claims[1])

        # 4. Unattributed Claim 3 and Invalid Claim 4 are completely omitted
        joined = " ".join(claims)
        self.assertNotIn("Silicon spin qubits", joined)
        self.assertNotIn("1820", joined)

    def test_audit_vault_notes_flags_legacy_notes(self):
        """
        Verify that audit_vault_notes_citations flags notes created before the fix timestamp.
        """
        temp_dir = tempfile.mkdtemp(prefix="thoth_test_audit_vault_")
        try:
            # 1. Write a legacy note created in the past with round-robin claims
            old_time = "2026-08-17T12:00:00.000000+00:00"
            legacy_content = """# Topic: Old Legacy Topic

## Claims
- An old claim from earlier [[src-old_source]]

## Synthesis Report
Old report text
"""
            write_note(
                note_id="topic-old_legacy",
                note_type="topics",
                content=legacy_content,
                frontmatter={"type": "topics", "created": old_time, "confidence": 0.8, "sources": ["src-old_source"]},
                vault_dir=temp_dir
            )

            # 2. Write a new note created after the cutoff
            new_time = "2026-08-17T20:00:00.000000+00:00"
            new_content = """# Topic: New Verified Topic

## Claims
- A verified claim [[src-new_source]]

## Synthesis Report
New report text
"""
            write_note(
                note_id="topic-new_verified",
                note_type="topics",
                content=new_content,
                frontmatter={"type": "topics", "created": new_time, "confidence": 0.9, "sources": ["src-new_source"]},
                vault_dir=temp_dir
            )

            # Audit with cutoff set to 2026-08-17T19:22:00
            flagged = audit_vault_notes_citations(cutoff_iso="2026-08-17T19:22:00", vault_dir=temp_dir)

            flagged_ids = [f["note_id"] for f in flagged]
            self.assertIn("topic-old_legacy", flagged_ids)
            self.assertNotIn("topic-new_verified", flagged_ids)
            self.assertTrue(flagged[0]["flagged_for_review"])
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
