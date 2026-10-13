import unittest
from unittest.mock import patch
import json

from backend.intellectual_rigour.models import ReviewRequest, ReviewTarget, CritiqueFinding, ReviewArtifact
from backend.intellectual_rigour.registry import (
    load_registry,
    get_framework,
    resolve_thinker_command,
    list_registered_thinkers,
)
from backend.intellectual_rigour.frameworks.aristotle.framework import AristotleFramework
from backend.intellectual_rigour.frameworks.bacon.framework import BaconFramework
from backend.intellectual_rigour.frameworks.descartes.framework import DescartesFramework
from backend.intellectual_rigour.frameworks.hume.framework import HumeFramework
from backend.intellectual_rigour.frameworks.darwin.framework import DarwinFramework
from backend.intellectual_rigour.frameworks.popper.framework import PopperFramework
from backend.intellectual_rigour.frameworks.kuhn.framework import KuhnFramework
from backend.intellectual_rigour.frameworks.box.framework import BoxFramework
from backend.intellectual_rigour.frameworks.turing.framework import TuringFramework
from backend.intellectual_rigour.frameworks.simon.framework import SimonFramework

from backend.intellectual_rigour.attack_surface import detect_attack_surfaces, AttackSurfaceProfile
from backend.intellectual_rigour.synthesis import run_multi_framework_synthesis, execute_intellectual_rigour_synthesis
from backend.intellectual_rigour import execute_thinker_review

SAMPLE_RESEARCH_REPORT = """# Deep Research Synthesis: Multimodal Reasoning & World Models

## Executive Summary
We introduce Chronos-1, a 70B parameter world model combining autoregressive sequence prediction with latent diffusion for robotic manipulation.

## Core Hypotheses & Definitions
Reasoning in Chronos-1 is defined as the latent interpolation between future video state embeddings. We prove that scaling token compute linearly causes proportional reasoning gain.

## Empirical Benchmarks & Ablations
Chronos-1 achieves 92.4% success on Robosuite manipulation tasks across 100 positive trials.

## Model Architecture & Complexity
The model runs an unconstrained planning loop over continuous action space with an infinite search horizon.
"""

class TestAllTenFrameworks(unittest.TestCase):
    def setUp(self):
        load_registry()

    def test_all_ten_thinkers_registered(self):
        thinkers = list_registered_thinkers()
        registered_ids = {t["id"] for t in thinkers}
        expected_ids = {
            "aristotle", "bacon", "descartes", "hume", "darwin",
            "popper", "kuhn", "box", "turing", "simon"
        }
        self.assertTrue(expected_ids.issubset(registered_ids))

    def test_generic_slash_command_resolution_for_all_ten(self):
        aliases = [
            ("/aristotle", "aristotle"),
            ("/bacon", "bacon"),
            ("/descartes", "descartes"),
            ("/hume", "hume"),
            ("/darwin", "darwin"),
            ("/popper", "popper"),
            ("/kuhn", "kuhn"),
            ("/box", "box"),
            ("/turing", "turing"),
            ("/simon", "simon"),
            ("/rigour", "rigour_synthesis"),
            ("/rigor", "rigour_synthesis"),
        ]
        for cmd, expected_id in aliases:
            resolved = resolve_thinker_command(cmd)
            self.assertIsNotNone(resolved, f"Failed to resolve {cmd}")
            target_obj, _ = resolved
            if isinstance(target_obj, str):
                self.assertEqual(target_obj, expected_id)
            else:
                self.assertEqual(target_obj.id, expected_id)

    def test_ordinary_words_do_not_trigger_thinker_review(self):
        isolated_words = [
            "phenomenological",
            "methodological",
            "technological",
            "chronological",
        ]
        for word in isolated_words:
            self.assertIsNone(
                resolve_thinker_command(word),
                f"Isolated word '{word}' should not resolve to a thinker command"
            )

        natural_queries = [
            "Under a standard phenomenological error model, what is the maximum allowable physical gate infidelity for fault tolerance in surface codes?",
            "What is the methodological foundation of quantum error correction?",
            "Explain the technological breakthroughs in superconducting transmon qubits.",
            "Provide a chronological timeline of world model discoveries.",
            "What is the logic behind this mathematical derivation?",
            "Categories of quantum algorithms include variational and fault-tolerant types.",
            "The evolutionary mechanism of biological adaptation.",
            "Model residual diagnostics after statistical training.",
        ]
        for q in natural_queries:
            self.assertIsNone(
                resolve_thinker_command(q),
                f"Natural language query '{q}' should not resolve to a thinker command"
            )

    def test_explicit_commands_and_arguments_resolution(self):
        resolved_logic = resolve_thinker_command("/logic")
        self.assertIsNotNone(resolved_logic)
        framework, req = resolved_logic
        self.assertEqual(framework.id, "aristotle")
        self.assertEqual(req.target.scope, "WHOLE_REPORT")
        self.assertFalse(req.force_reevaluation)

        resolved_target = resolve_thinker_command('/logic --target="Methodology & Verification"')
        self.assertIsNotNone(resolved_target)
        _, req = resolved_target
        self.assertEqual(req.target.scope, "SECTION")
        self.assertEqual(req.target.section_title, "Methodology & Verification")

        resolved_kw = resolve_thinker_command("/logic audit the methodology")
        self.assertIsNotNone(resolved_kw)
        _, req = resolved_kw
        self.assertEqual(req.target.scope, "SECTION")
        self.assertEqual(req.target.section_title, "Methodology")

        resolved_force = resolve_thinker_command("/logic --force")
        self.assertIsNotNone(resolved_force)
        _, req = resolved_force
        self.assertTrue(req.force_reevaluation)

        resolved_embedded = resolve_thinker_command("Please run /logic on the methodology")
        self.assertIsNotNone(resolved_embedded)
        fw, req = resolved_embedded
        self.assertEqual(fw.id, "aristotle")
        self.assertEqual(req.target.scope, "SECTION")
        self.assertEqual(req.target.section_title, "Methodology")

        resolved_rigour = resolve_thinker_command("/rigour --force")
        self.assertIsNotNone(resolved_rigour)
        target_mode, req = resolved_rigour
        self.assertEqual(target_mode, "rigour_synthesis")
        self.assertTrue(req.force_reevaluation)

    def test_aristotle_identifies_definitional_ambiguity(self):
        fw = AristotleFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Category error: defining reasoning merely as latent video interpolation.",
            "critiques": [{
                "target_claim_or_method": "Reasoning defined as latent video interpolation",
                "critique_type": "CONCEPTUAL_AMBIGUITY",
                "severity": "CRITICAL",
                "blocking": True,
                "problem": "Equivocates between statistical pattern continuation and formal logical deduction.",
                "why_it_matters": "Category error conflating predictive association with valid inference.",
                "evidence_or_counterexample": "Video interpolation produces plausible hallucination without logical necessity.",
                "required_context": "",
                "recommendation": "Define reasoning with genus (cognitive inference) and differentia (logical truth preservation).",
                "confidence": 0.95,
                "provenance_rule": "Aristotle: Genus-Differentia"
            }],
            "clarified_definitions": ["Reasoning: Deductive truth-preserving transition across propositional states."]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/aristotle"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Genus & Differentia", art.formatted_markdown)
            self.assertIn("Category error", art.formatted_markdown)

    def test_bacon_identifies_selective_evidence_and_idols(self):
        fw = BaconFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Selective observation: only 100 positive trials reported without negative control cases.",
            "critiques": [{
                "target_claim_or_method": "92.4% success across 100 positive trials",
                "critique_type": "UNSUPPORTED_INFERENCE",
                "severity": "MAJOR",
                "blocking": True,
                "problem": "Table of Absence omitted: failure modes under perturbed lighting or novel objects not tested.",
                "why_it_matters": "Idols of the Cave / selective reporting invalidates induction.",
                "evidence_or_counterexample": "Positive instances alone cannot establish robust manipulation reliability.",
                "required_context": "Negative control trials and failure breakdown table.",
                "recommendation": "Conduct Table of Absence in Proximity test with out-of-distribution object textures.",
                "confidence": 0.9,
                "provenance_rule": "Bacon: Tables of Absence & Four Idols"
            }],
            "discriminating_tests": ["Run 100 trials with adversarial object perturbations."]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/bacon"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Crucial Discriminating Experiments", art.formatted_markdown)

    def test_descartes_identifies_hidden_dependencies(self):
        fw = DescartesFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Foundational assumption flaw: linear compute scaling assumes infinite memory bandwidth.",
            "critiques": [{
                "target_claim_or_method": "Linear compute scaling causes proportional reasoning gain",
                "critique_type": "FATAL_FLAW",
                "severity": "CRITICAL",
                "blocking": True,
                "problem": "Compound proposition conceals unproven assumption of zero-latency memory retrieval.",
                "why_it_matters": "If memory bandwidth saturates, the entire scaling deduction collapses.",
                "evidence_or_counterexample": "Amdahl's law demonstrates memory-bound bottlenecking.",
                "required_context": "",
                "recommendation": "Decompose into atomic compute vs. memory bandwidth primitives.",
                "confidence": 0.9,
                "provenance_rule": "Descartes: Assumption Subtraction"
            }],
            "primitive_foundations": ["Atomic Primitive 1: FLOP count", "Atomic Primitive 2: Memory access latency"]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/descartes"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Isolated Atomic Primitives", art.formatted_markdown)

    def test_hume_identifies_correlation_to_causation_leap(self):
        fw = HumeFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Inferential leap from observed token scaling correlation to claimed causal reasoning power.",
            "critiques": [{
                "target_claim_or_method": "Scaling token compute causes proportional reasoning gain",
                "critique_type": "UNSUPPORTED_INFERENCE",
                "severity": "CRITICAL",
                "blocking": True,
                "problem": "Constant conjunction of compute and benchmark score mistaken for demonstrated causal necessity.",
                "why_it_matters": "Omitted confounder: dataset contamination may account for observed score gains.",
                "evidence_or_counterexample": "Benchmark data leakage induces correlation without causal reasoning.",
                "required_context": "Interventional test on novel synthetic tasks.",
                "recommendation": "Downgrade certainty language to observed correlation under benchmark distribution.",
                "confidence": 0.95,
                "provenance_rule": "Hume: Inferential Jump & Confounder Attack"
            }],
            "alternative_causal_hypotheses": ["Confounder: Pre-training data memorization rather than causal reasoning."]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/hume"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Competing Causal Explanations", art.formatted_markdown)

    def test_darwin_identifies_missing_generative_mechanism(self):
        fw = DarwinFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Lacks generative mechanism explaining how latent diffusion produces stable continuous actions.",
            "critiques": [{
                "target_claim_or_method": "Latent diffusion produces robotic continuous action trajectory",
                "critique_type": "UNSUPPORTED_INFERENCE",
                "severity": "MAJOR",
                "blocking": True,
                "problem": "Fails to specify how physical environmental constraints filter out chaotic intermediate states.",
                "why_it_matters": "Without a viable selection filter, cumulative trajectory drift causes physical crashes.",
                "evidence_or_counterexample": "Compounding error drift in open-loop diffusion trajectories.",
                "required_context": "Closed-loop feedback filter specifications.",
                "recommendation": "Model cumulative trajectory selection with closed-loop tactile feedback filters.",
                "confidence": 0.9,
                "provenance_rule": "Darwin: Selection Pressures & Generative Intermediates"
            }],
            "competing_mechanisms": ["Closed-loop MPC trajectory optimization vs Open-loop diffusion."]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/darwin"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Competing Generative Hypotheses", art.formatted_markdown)

    def test_kuhn_identifies_normal_science_vs_revolution(self):
        fw = KuhnFramework()
        mock_output = json.dumps({
            "verdict": "NO_MATERIAL_OBJECTION",
            "has_material_objections": False,
            "executive_summary": "Accurately positioned as normal puzzle-solving extending standard latent diffusion paradigms.",
            "critiques": [],
            "paradigm_anomalies": ["Catastrophic physical interpenetration in video generation models."]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/kuhn"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "NO_MATERIAL_OBJECTION")
            self.assertIn("Highlighted Domain Anomalies", art.formatted_markdown)

    def test_box_identifies_structured_residuals_and_boundaries(self):
        fw = BoxFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Model sensitivity breakdown: trajectory errors exhibit structured autocorrelation over time.",
            "critiques": [{
                "target_claim_or_method": "Latent action prediction estimator",
                "critique_type": "BOUNDARY_LIMIT",
                "severity": "CRITICAL",
                "blocking": True,
                "problem": "Autocorrelated residual errors accumulate after time-step t=15, causing failure boundary breach.",
                "why_it_matters": "Model is not useful for horizon > 15 steps without re-planning.",
                "evidence_or_counterexample": "Residual drift plots show non-Gaussian exponential divergence.",
                "required_context": "",
                "recommendation": "Explicitly bound model utility to short-horizon execution (t <= 15).",
                "confidence": 0.95,
                "provenance_rule": "Box: Residual Diagnostics & Boundary Delineation"
            }],
            "model_stress_diagnostics": ["Inject Gaussian sensor noise and evaluate residual autocorrelation."]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/box"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Model Stress-Tests", art.formatted_markdown)

    def test_turing_identifies_infinite_horizon_uncomputability(self):
        fw = TuringFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Unbounded planning loop over continuous action space violates effective computability.",
            "critiques": [{
                "target_claim_or_method": "Unconstrained planning loop with infinite search horizon",
                "critique_type": "FATAL_FLAW",
                "severity": "CRITICAL",
                "blocking": True,
                "problem": "Infinite horizon over continuous space is non-terminating and uncomputable.",
                "why_it_matters": "Violates effective calculability and lacks halting guarantee.",
                "evidence_or_counterexample": "Continuous search without discretisation or bound does not terminate.",
                "required_context": "",
                "recommendation": "Formulate discrete state space Q with finite horizon depth d_max.",
                "confidence": 0.95,
                "provenance_rule": "Turing: Termination Guarantees & Effective Calculability"
            }],
            "formal_state_specifications": ["(q_plan, input_obs) -> (q_execute, action_vector) with depth limit d=20"]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/turing"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Formalized State Transitions", art.formatted_markdown)

    def test_simon_identifies_unbounded_search_explosion(self):
        fw = SimonFramework()
        mock_output = json.dumps({
            "verdict": "MATERIAL_OBJECTION",
            "has_material_objections": True,
            "executive_summary": "Combinatorial search explosion: continuous planning ignores latency budget and resource bounds.",
            "critiques": [{
                "target_claim_or_method": "Unconstrained planning loop over continuous space",
                "critique_type": "BOUNDARY_LIMIT",
                "severity": "CRITICAL",
                "blocking": True,
                "problem": "Assumes unbounded compute; fails to define satisficing aspiration stopping rule.",
                "why_it_matters": "Search cost exceeds 500ms robot control latency SLA.",
                "evidence_or_counterexample": "Branching factor b=infinity renders exhaustive planning physically impossible.",
                "required_context": "Real-time latency budget SLA.",
                "recommendation": "Implement heuristic beam search with satisficing stopping criterion epsilon=0.05.",
                "confidence": 0.9,
                "provenance_rule": "Simon: Bounded Rationality & Satisficing Stopping Rules"
            }],
            "satisficing_alternatives": ["Greedy Model Predictive Control with 5-step horizon."]
        })
        with patch.object(fw, "_invoke_chain", return_value=mock_output):
            art = fw.review(ReviewRequest(query="/simon"), SAMPLE_RESEARCH_REPORT)
            self.assertEqual(art.metadata["verdict"], "MATERIAL_OBJECTION")
            self.assertIn("Lower-Cost Satisficing Alternatives", art.formatted_markdown)

    def test_multi_framework_synthesis_preserves_tensions(self):
        mock_synth_output = json.dumps({
            "agreements": ["High benchmark manipulation score on standard training setup."],
            "shared_objections": ["Unbounded planning horizon violates real-time physical latency constraints."],
            "disagreements_and_conflicts": [{
                "conflict_summary": "Formal Deductive Truth vs Heuristic Satisficing Utility",
                "frameworks_involved": "Aristotle vs Simon",
                "underlying_cause": "Aristotle rejects video interpolation as non-deductive; Simon accepts it if it satisfices robot control goals.",
                "material_impact": "Method is valid for heuristic task completion but invalid as a formal reasoning theory."
            }],
            "blind_spots_surfaced": ["Continuous trajectory execution assumes zero-latency sensor feedback."],
            "contribution_dimensions": {
                "conceptual_clarity": "Moderate - conflates prediction with deduction",
                "falsifiability": "High - testable on real transmon/robot hardware",
                "satisficing_efficiency": "Low - unbounded search cost"
            },
            "executive_verdict": "Chronos-1 provides useful robotic heuristics but overclaims theoretical reasoning and violates real-time compute bounds."
        })

        with patch("backend.intellectual_rigour.synthesis.llm.invoke", return_value=mock_synth_output):
            res = execute_intellectual_rigour_synthesis(
                report_text=SAMPLE_RESEARCH_REPORT,
                topic="Robotics",
                framework_ids=["aristotle", "simon", "turing"]
            )
            self.assertTrue(res["success"])
            self.assertIn("Multi-Framework Synthesis", res["updated_report"])
            self.assertIn("Foundational Tensions & Disagreements", res["new_section"])
            self.assertIn("Aristotle vs Simon", res["new_section"])

    def test_intellectual_rigour_detachability(self):
        res = execute_thinker_review(
            query="/nonexistent_framework",
            report_text=SAMPLE_RESEARCH_REPORT,
            topic="Test"
        )
        self.assertFalse(res["success"])
        self.assertIn("No reasoning framework recognized", res["error"])

if __name__ == "__main__":
    unittest.main()
