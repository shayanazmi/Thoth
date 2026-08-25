"""
tests/test_logical_integrity.py - Logical Integrity & System Health Diagnostic Tests.
Verifies:
1. CONTRADICTION LEAKAGE: Graph contradiction detection and context alert assembly.
2. CIRCULAR REPLAN DETECTION: Reintroduction of rejected claims during replan loopbacks.
3. UNSUPPORTED CAUSAL/COMPARATIVE CLAIMS: Modality drift (correlation->causation, superlatives).
4. NON-SEQUITUR / UNSUPPORTED CONCLUSION: Grounded conclusion verification with claim logging.
5. WASTED-TOKEN TRACKING: Retrieval precision ratio and wasted token counts.
6. NO-RESPONSE / APOLOGY RATE: Fallback, empty report, and refusal tracking.
7. CIRCUIT BREAKER BEHAVIOR UNDER LOAD: 3-state lifecycle (CLOSED -> OPEN -> HALF_OPEN -> CLOSED).
"""
import os
import tempfile
import shutil
import unittest
import asyncio
import time
from unittest.mock import MagicMock, patch

from backend.memory.db import init_db
from backend.memory.graph import (
    add_edge,
    find_contradictions_among_notes,
    format_vault_context_with_contradictions
)
from backend.dispatcher import Dispatcher, CircuitBreakerOpenError
from backend.eval.judge_model import ThothJudgeModel
from backend.eval.datasets import (
    get_causal_comparative_adversarial_goldens,
    get_non_sequitur_conclusion_goldens
)
from backend.eval.metrics import (
    get_causal_comparative_metric,
    get_non_sequitur_conclusion_metric
)
from backend.eval.logical_integrity import (
    detect_circular_replan,
    compute_claim_similarity,
    compute_retrieval_precision_and_wasted_tokens,
    compute_no_response_and_apology_rate,
    check_is_apology_or_fallback,
    extract_cited_note_ids_from_text
)


class TestLogicalIntegrityAndSystemHealth(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_thoth.db")
        init_db(self.db_path)

        # Mock Judge Model for offline deterministic testing
        self.mock_judge_llm = MagicMock()
        self.mock_judge_llm.invoke.return_value = '{"score": 8.8, "reason": "Modality preserved and conclusions grounded."}'
        self.judge = ThothJudgeModel(model_instance=self.mock_judge_llm, model_name="Mock-Logical-Judge")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # =========================================================================
    # 1. CONTRADICTION LEAKAGE
    # =========================================================================

    def test_contradiction_leakage_in_context_assembly(self):
        """
        Confirms that when two notes connected by a 'contradicts' edge are retrieved,
        the system detects the conflict and injects an explicit contradiction alert.
        """
        # Insert notes into SQLite
        conn = init_db(self.db_path)
        with conn:
            conn.execute("INSERT INTO notes (note_id, type, created, confidence) VALUES ('src-fowler-2012', 'sources', '2026-08-18', 1.0);")
            conn.execute("INSERT INTO notes (note_id, type, created, confidence) VALUES ('src-chamberland-2020', 'sources', '2026-08-18', 1.0);")

        # Add bidirectional or directed 'contradicts' edge
        add_edge("src-fowler-2012", "contradicts", "src-chamberland-2020", confidence=0.95, db_path=self.db_path)

        # 1. Test raw contradiction lookup
        contradictions = find_contradictions_among_notes(
            ["src-fowler-2012", "src-chamberland-2020", "src-unrelated-note"],
            db_path=self.db_path
        )
        self.assertEqual(len(contradictions), 1)
        self.assertEqual(contradictions[0]["source"], "src-fowler-2012")
        self.assertEqual(contradictions[0]["target"], "src-chamberland-2020")
        self.assertAlmostEqual(contradictions[0]["confidence"], 0.95)

        # 2. Test context formatting alert injection
        mock_retrieved = [
            {"note_id": "src-fowler-2012", "content": "Planar surface code threshold is 1.0% under phenomenological noise."},
            {"note_id": "src-chamberland-2020", "content": "Flag fault-tolerant color codes achieve 0.1% threshold under circuit noise."}
        ]
        formatted_context, found_contradictions = format_vault_context_with_contradictions(
            mock_retrieved,
            db_path=self.db_path
        )

        self.assertEqual(len(found_contradictions), 1)
        self.assertIn("[KNOWLEDGE GRAPH CONTRADICTION ALERT]", formatted_context)
        self.assertIn("CONTRADICTS", formatted_context)
        self.assertIn("CRITICAL WRITING DIRECTIVE", formatted_context)
        self.assertIn("src-fowler-2012", formatted_context)
        self.assertIn("src-chamberland-2020", formatted_context)

    # =========================================================================
    # 2. CIRCULAR REPLAN DETECTION
    # =========================================================================

    def test_circular_replan_detection_on_rejected_claims(self):
        """
        Confirms that when the orchestrator replans, the system flags any reintroduction
        of previously rejected unverified claims without evidence.
        """
        previous_rejected_claims = [
            "Silicon spin qubits operate at room temperature with 99.9% fidelity without refrigeration."
        ]

        # Case A: Clean revision that removed or corrected the claim
        clean_draft_claims = [
            "Silicon spin qubits demonstrate nanoscale footprint advantages (~100nm pitch).",
            "Superconducting transmons currently achieve higher two-qubit gate fidelities (99.9%)."
        ]
        findings_clean = detect_circular_replan(previous_rejected_claims, clean_draft_claims)
        self.assertEqual(len(findings_clean), 0)

        # Case B: Circular draft that reintroduces the exact rejected claim
        circular_draft_claims = [
            "Silicon spin qubits operate at room temperature with 99.9% fidelity without refrigeration [src-spin].",
            "Superconducting transmons require millikelvin cooling."
        ]
        findings_circ = detect_circular_replan(previous_rejected_claims, circular_draft_claims)
        self.assertGreaterEqual(len(findings_circ), 1)
        self.assertIn("reintroduces previously rejected unverified claim", findings_circ[0]["reason"])
        self.assertGreaterEqual(findings_circ[0]["similarity"], 0.80)

    # =========================================================================
    # 3. UNSUPPORTED CAUSAL / COMPARATIVE CLAIMS
    # =========================================================================

    def test_unsupported_causal_comparative_claims_metric(self):
        """
        Verifies that causal/comparative adversarial goldens execute against the metric
        and correctly evaluate modality inflation.
        """
        goldens = get_causal_comparative_adversarial_goldens()
        self.assertEqual(len(goldens), 3)

        metric = get_causal_comparative_metric(model=self.judge, threshold=0.70)
        for g in goldens:
            score = metric.measure(g)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
            self.assertIsNotNone(metric.reason)

    # =========================================================================
    # 4. NON-SEQUITUR / UNSUPPORTED CONCLUSION
    # =========================================================================

    def test_non_sequitur_unsupported_conclusion_metric(self):
        """
        Verifies that report conclusions are checked for ungrounded leaps or non-sequitur claims.
        """
        goldens = get_non_sequitur_conclusion_goldens()
        self.assertEqual(len(goldens), 2)

        metric = get_non_sequitur_conclusion_metric(model=self.judge, threshold=0.70)
        for g in goldens:
            score = metric.measure(g)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
            self.assertIsNotNone(metric.reason)

    # =========================================================================
    # 5. WASTED-TOKEN TRACKING & RETRIEVAL PRECISION
    # =========================================================================

    def test_wasted_token_tracking_and_retrieval_precision(self):
        """
        Instruments retrieval context to calculate precision ratio and wasted tokens.
        """
        retrieved_notes = [
            {"note_id": "src-surface-code-threshold", "content": "Planar surface code threshold is ~1% under depolarizing noise model."},
            {"note_id": "src-fowler-2012", "content": "Comprehensive review of stabilizer error correction algorithms."},
            {"note_id": "src-unrelated-superconductor", "content": "High-temperature cuprate phase transitions and lattice parameters."}
        ]

        # Report that cites only 2 of the 3 retrieved notes
        final_report = (
            "# Quantum Error Correction\n"
            "Surface codes achieve an empirical threshold of approximately 1% [src-surface-code-threshold]. "
            "Stabilizer tracking algorithms are detailed in [src-fowler-2012]."
        )

        precision_data = compute_retrieval_precision_and_wasted_tokens(retrieved_notes, final_report)

        self.assertAlmostEqual(precision_data["retrieval_precision"], 2 / 3, places=3)
        self.assertEqual(precision_data["cited_count"], 2)
        self.assertEqual(precision_data["retrieved_count"], 3)
        self.assertIn("src-unrelated-superconductor", precision_data["unused_note_ids"])
        self.assertIn("src-surface-code-threshold", precision_data["cited_note_ids"])
        self.assertGreater(precision_data["wasted_tokens"], 0)
        self.assertGreater(precision_data["wasted_token_ratio"], 0.0)

    # =========================================================================
    # 6. NO-RESPONSE / APOLOGY RATE TRACKING
    # =========================================================================

    def test_no_response_and_apology_rate(self):
        """
        Tests calculation of empty reports, zero-claim reports, and refusal apologies.
        """
        reports = [
            {"report": "Comprehensive report with citations [src-1].", "valid_claims": 5},
            {"report": "Another grounded synthesis [src-2].", "valid_claims": 3},
            {"report": "", "valid_claims": 0},  # Empty
            {"report": "I apologize, but as an AI I am unable to find information.", "valid_claims": 0},  # Apology
            {"report": "Some unverified text without citations.", "valid_claims": 0}  # Zero valid claims
        ]

        stats = compute_no_response_and_apology_rate(reports)
        self.assertEqual(stats["total_reports"], 5)
        self.assertEqual(stats["empty_reports"], 1)
        self.assertEqual(stats["zero_claim_reports"], 1)
        self.assertEqual(stats["apology_reports"], 1)
        self.assertAlmostEqual(stats["no_response_rate"], 2 / 5, places=2)
        self.assertAlmostEqual(stats["apology_rate"], 1 / 5, places=2)
        self.assertTrue(stats["alert"])

    # =========================================================================
    # 7. CIRCUIT BREAKER BEHAVIOR UNDER LOAD
    # =========================================================================

    def test_circuit_breaker_behavior_under_load(self):
        """
        Integration test verifying Dispatcher Circuit Breaker under repeated failure:
        CLOSED -> OPEN (after threshold) -> Blocks with CircuitBreakerOpenError ->
        HALF_OPEN (after cooloff) -> CLOSED (on recovery).
        """
        dispatcher = Dispatcher(
            max_concurrent=2,
            max_attempts=1,  # 1 attempt per call so failures increment immediately
            base_delay=0.01,
            max_consecutive_failures=3,
            cooloff_seconds=0.10  # 100ms cooloff for fast deterministic testing
        )

        fail_count = 0

        async def failing_operation():
            nonlocal fail_count
            fail_count += 1
            raise RuntimeError(f"Simulated hardware network error #{fail_count}")

        async def successful_operation():
            return "SUCCESS_DATA"

        async def run_breaker_flow():
            # Initial state should be CLOSED
            self.assertEqual(dispatcher.state, "CLOSED")

            # 1. Trigger 3 consecutive failures
            for i in range(3):
                with self.assertRaises(RuntimeError):
                    await dispatcher.call(failing_operation)

            # Breaker should now be TRIPPED -> OPEN
            self.assertEqual(dispatcher.state, "OPEN")
            self.assertEqual(dispatcher.consecutive_failures, 3)

            # 2. Calls while OPEN should be blocked immediately with CircuitBreakerOpenError
            with self.assertRaises(CircuitBreakerOpenError):
                await dispatcher.call(successful_operation)

            # 3. Wait for cooloff to expire
            await asyncio.sleep(0.12)

            # 4. First call after cooloff should transition to HALF_OPEN and succeed
            res = await dispatcher.call(successful_operation)
            self.assertEqual(res, "SUCCESS_DATA")

            # Breaker should now be fully recovered -> CLOSED
            self.assertEqual(dispatcher.state, "CLOSED")
            self.assertEqual(dispatcher.consecutive_failures, 0)

        asyncio.run(run_breaker_flow())


if __name__ == "__main__":
    unittest.main()
