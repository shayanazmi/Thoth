import unittest
from unittest.mock import MagicMock, patch
import json

from backend.intellectual_rigour.models import (
    ReviewRequest,
    ReviewTarget,
    CritiqueFinding,
    ThinkerOutput,
    ReviewArtifact,
)
from backend.intellectual_rigour.registry import (
    resolve_thinker_command,
    get_framework,
    list_registered_thinkers,
)
from backend.intellectual_rigour.frameworks.popper.framework import (
    PopperFramework,
    popper_chain,
)
from backend.intellectual_rigour import execute_thinker_review
from backend.reports.patch import patch_report_section
from backend.reports.sections import find_markdown_sections

SAMPLE_RESEARCH_REPORT = """---
type: research_report
title: Quantum Error Correction Breakthroughs 2026
---

# Deep Research Synthesis: Quantum Error Correction

## Executive Summary
Surface codes have demonstrated fault-tolerant logical qubit operations below the physical threshold error rate.

## Key Findings
- Distance-5 surface codes achieved logical error suppression per round [[src-nature_2024]].
- Real-time syndrome decoding latency was reduced to 250ns using custom FPGA pipelines [[src-arxiv_2402]].

## Methodology & Verification
Benchmarking was conducted across 72 superconducting transmon qubits with randomized benchmarking.

## Open Challenges
Cosmic ray burst events induce correlated multi-qubit error events.
"""

class TestPopperVerticalSlice(unittest.TestCase):
    def test_registry_resolves_popper_command(self):
        resolved = resolve_thinker_command("/popper")
        self.assertIsNotNone(resolved)
        framework, req = resolved
        self.assertEqual(framework.id, "popper")
        self.assertEqual(framework.name, "Karl Popper")
        self.assertEqual(req.target.scope, "WHOLE_REPORT")

    def test_registry_resolves_targeted_command(self):
        resolved = resolve_thinker_command("/popper review the methodology")
        self.assertIsNotNone(resolved)
        framework, req = resolved
        self.assertEqual(req.target.scope, "SECTION")
        self.assertEqual(req.target.section_title, "Methodology")

    def test_registry_lists_registered_thinkers(self):
        thinkers = list_registered_thinkers()
        ids = [t["id"] for t in thinkers]
        self.assertIn("popper", ids)

    def test_critique_finding_schema_validation(self):
        finding = CritiqueFinding(
            target_claim_or_method="Distance-5 surface codes eliminate all logical errors",
            critique_type="UNFALSIFIABLE_SHIELD",
            severity="CRITICAL",
            blocking=True,
            problem="Absolute elimination claim without specifying bounding conditions.",
            why_it_matters="Overstates empirical confidence.",
            evidence_or_counterexample="Correlated cosmic ray events still cause logical leakage.",
            required_context="",
            recommendation="State bounded error suppression rates under specified noise thresholds.",
            provenance_rule="Popper: Falsifiability & Demarcation"
        )
        self.assertEqual(finding.critique_type, "UNFALSIFIABLE_SHIELD")
        self.assertTrue(finding.blocking)
        self.assertEqual(finding.severity, "CRITICAL")

    def test_invalid_llm_output_does_not_crash(self):
        framework = PopperFramework()
        req = ReviewRequest(query="/popper")

        with patch.object(framework, "_invoke_chain", return_value="Malformed non-JSON output"):
            artifact = framework.review(req, SAMPLE_RESEARCH_REPORT, topic="Quantum Computing")
            self.assertIsInstance(artifact, ReviewArtifact)
            self.assertEqual(artifact.framework_id, "popper")
            self.assertIn(framework.section_heading, artifact.formatted_markdown)

    def test_material_objection_generation(self):
        framework = PopperFramework()
        req = ReviewRequest(query="/popper")

        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Identified critical unfalsifiable claims regarding error elimination.",
            "critiques": [{
                "target_claim_or_method": "Surface codes eliminate all errors",
                "critique_type": "UNFALSIFIABLE_SHIELD",
                "severity": "CRITICAL",
                "blocking": True,
                "problem": "Claim is shielded against empirical counterexamples.",
                "why_it_matters": "Violates falsifiability criterion.",
                "evidence_or_counterexample": "Cosmic rays induce correlated failure.",
                "required_context": "",
                "recommendation": "Bound the claim to independent single-qubit Pauli channels.",
                "confidence": 0.95,
                "provenance_rule": "Popper: Demarcation"
            }],
            "unresolved_questions": ["What is the threshold beyond which the decoder fails?"],
            "potential_falsifying_experiments": ["Expose array to radioactive source to measure correlated bursts."]
        })

        with patch.object(framework, "_invoke_chain", return_value=mock_output):
            artifact = framework.review(req, SAMPLE_RESEARCH_REPORT, topic="Quantum Computing")
            self.assertEqual(artifact.metadata.get("verdict"), "MATERIAL_OBJECTION")
            self.assertTrue(artifact.metadata.get("has_material_objections"))
            self.assertIn("MATERIAL OBJECTION", artifact.formatted_markdown)
            self.assertIn("Surface codes eliminate all errors", artifact.formatted_markdown)

    def test_no_material_objection_generation(self):
        framework = PopperFramework()
        req = ReviewRequest(query="/popper")

        mock_output = json.dumps({
            "verdict": "NO_MATERIAL_OBJECTION",
            "has_material_objections": False,
            "executive_summary": "All empirical claims are sharply testable and corroborated under specified transmon thresholds.",
            "critiques": [],
            "unresolved_questions": [],
            "potential_falsifying_experiments": ["Test under 100ns decoding latency."]
        })

        with patch.object(framework, "_invoke_chain", return_value=mock_output):
            artifact = framework.review(req, SAMPLE_RESEARCH_REPORT, topic="Quantum Computing")
            self.assertEqual(artifact.metadata.get("verdict"), "NO_MATERIAL_OBJECTION")
            self.assertFalse(artifact.metadata.get("has_material_objections"))
            self.assertIn("NO MATERIAL OBJECTION", artifact.formatted_markdown)

    def test_insufficient_context_withholding(self):
        framework = PopperFramework()
        req = ReviewRequest(query="/popper")

        mock_output = json.dumps({
            "verdict": "INSUFFICIENT_CONTEXT",
            "has_material_objections": False,
            "executive_summary": "Empirical threshold cannot be evaluated without physical gate fidelity data.",
            "critiques": [{
                "target_claim_or_method": "Threshold error rate achieved",
                "critique_type": "BOUNDARY_LIMIT",
                "severity": "MAJOR",
                "blocking": False,
                "problem": "Raw gate infidelity numbers are omitted from report text.",
                "why_it_matters": "Cannot verify whether physical error rate is below 0.5% threshold.",
                "evidence_or_counterexample": "",
                "required_context": "Two-qubit CZ gate fidelity matrices across all 72 transmons.",
                "recommendation": "WITHHELD_PENDING_CONTEXT",
                "confidence": 0.85,
                "provenance_rule": "Popper: Severe Testing"
            }],
            "unresolved_questions": ["What was the average 2-qubit randomized benchmarking fidelity?"]
        })

        with patch.object(framework, "_invoke_chain", return_value=mock_output):
            artifact = framework.review(req, SAMPLE_RESEARCH_REPORT, topic="Quantum Computing")
            self.assertEqual(artifact.metadata.get("verdict"), "INSUFFICIENT_CONTEXT")
            self.assertIn("INSUFFICIENT CONTEXT", artifact.formatted_markdown)
            self.assertIn("WITHHELD_PENDING_CONTEXT", artifact.formatted_markdown)
            self.assertIn("Two-qubit CZ gate fidelity matrices", artifact.formatted_markdown)

    def test_first_insertion_appends_cleanly(self):
        res1 = execute_thinker_review(
            query="/popper",
            report_text=SAMPLE_RESEARCH_REPORT,
            topic="Quantum Error Correction"
        )
        self.assertTrue(res1["success"])
        updated_report_1 = res1["updated_report"]
        self.assertFalse(res1["was_in_place_replacement"])
        self.assertIn("### 🏛️ Philosophical Review: Karl Popper", updated_report_1)
        self.assertIn("## Open Challenges", updated_report_1)

        res2 = execute_thinker_review(
            query="/popper",
            report_text=updated_report_1,
            topic="Quantum Error Correction"
        )
        self.assertTrue(res2["success"])
        updated_report_2 = res2["updated_report"]
        self.assertTrue(res2["was_in_place_replacement"])

        sections = find_markdown_sections(updated_report_2)
        popper_headings = [s for s in sections if "Karl Popper" in s.title]
        self.assertEqual(len(popper_headings), 1)

    def test_unrelated_sections_preserved_exactly(self):
        res = execute_thinker_review(
            query="/popper",
            report_text=SAMPLE_RESEARCH_REPORT,
            topic="Quantum Error Correction"
        )
        updated = res["updated_report"]

        self.assertTrue("## Executive Summary\nSolid state batteries" not in updated)
        self.assertIn("Surface codes have demonstrated fault-tolerant logical qubit operations", updated)
        self.assertIn("Distance-5 surface codes achieved logical error suppression per round", updated)
        self.assertIn("Real-time syndrome decoding latency was reduced to 250ns", updated)
        self.assertIn("Cosmic ray burst events induce correlated multi-qubit error events.", updated)
        self.assertIn("Surface codes have demonstrated fault-tolerant logical qubit operations", updated)
        self.assertIn("Distance-5 surface codes achieved logical error suppression per round", updated)
        self.assertIn("Real-time syndrome decoding latency was reduced to 250ns", updated)
        self.assertIn("Cosmic ray burst events induce correlated multi-qubit error events.", updated)

    def test_source_hash_calculation_and_stability(self):
        framework = PopperFramework()
        hash1 = framework.compute_source_hash(SAMPLE_RESEARCH_REPORT)
        self.assertEqual(len(hash1), 12)

        report_with_review = f"{SAMPLE_RESEARCH_REPORT}\n\n<!-- intellectual-rigour:start framework=\"popper\" -->\n### 🏛️ Philosophical Review: Karl Popper\nTest review\n<!-- intellectual-rigour:end -->"
        hash2 = framework.compute_source_hash(report_with_review)
        self.assertEqual(hash1, hash2)

        mutated_report = SAMPLE_RESEARCH_REPORT + "\n## New Breakthroughs\nCat qubits."
        hash3 = framework.compute_source_hash(mutated_report)
        self.assertNotEqual(hash1, hash3)

    def test_core_patcher_still_works_for_general_sections(self):
        patched, replaced = patch_report_section(
            original_markdown=SAMPLE_RESEARCH_REPORT,
            section_title="Open Challenges",
            new_content="## Open Challenges\nUpdated challenge: Cosmic ray mitigation and quasiparticle poisoning."
        )
        self.assertTrue(replaced)
        self.assertIn("quasiparticle poisoning", patched)
        self.assertIn("## Executive Summary", patched)

if __name__ == "__main__":
    unittest.main()
