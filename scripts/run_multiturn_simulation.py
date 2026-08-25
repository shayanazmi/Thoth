#!/usr/bin/env python3
"""
scripts/run_multiturn_simulation.py - Thoth Multi-Turn Conversation Simulation & Evaluation.
Executes ConversationSimulator across 16 ConversationalGoldens with max_user_simulations=8,
evaluates using the 6 DeepEval multi-turn metrics, and outputs granular pass rates per scenario.
"""
import sys
import os
import argparse
import json
from typing import Dict, Any
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.eval import (
    ThothJudgeModel,
    get_thoth_judge_model,
    get_multiturn_goldens,
    run_conversational_simulation_and_evals
)
from backend.telemetry import enable_local_tracing, clear_local_traces


def main():
    parser = argparse.ArgumentParser(description="Thoth Multi-Turn Simulation & DeepEval Evaluation")
    parser.add_argument("--max_simulations", type=int, default=8, help="Max user turns to simulate per scenario (default: 8)")
    parser.add_argument("--live", action="store_true", help="Run with live LLM judge instead of offline mock judge")
    parser.add_argument("--save_json", type=str, default="", help="Optional JSON file path to save detailed evaluation report")
    args = parser.parse_args()

    print("=" * 90)
    print("THOTH MULTI-TURN CONVERSATION SIMULATION & EVALUATION SUITE")
    print(f"Max User Simulations: {args.max_simulations} | Metrics: 6 DeepEval Metrics | Mode: {'LIVE' if args.live else 'OFFLINE'}")
    print("=" * 90)

    enable_local_tracing()
    clear_local_traces()

    if args.live:
        judge = get_thoth_judge_model()
        print(f"\n[INFO] Initialized Live Thoth Judge Model: {judge.get_model_name()}")
    else:
        def _mock_judge_fn(prompt: Any, *args: Any, **kwargs: Any) -> str:
            low = str(prompt).lower()
            if "qa_pair" in low or "extract all questions" in low or "questions asked by the user" in low:
                return json.dumps({
                    "qa_pairs": [{"question": "What is the error threshold of surface codes?", "response": "Surface code threshold is ~1%."}]
                })
            elif "relevancy" in low or "relevant" in low or "verdict" in low:
                return json.dumps({
                    "verdict": "yes",
                    "verdicts": [{"verdict": "yes", "reason": "Strictly adheres to relevant research topic."}],
                    "reason": "Directly addresses academic quantum research."
                })
            elif "topic" in low or "intent" in low:
                return json.dumps({
                    "intentions": ["academic research into quantum computing"],
                    "topics": ["academic research", "the topic under discussion"],
                    "verdicts": [{"verdict": "yes", "reason": "Strictly on academic topic"}],
                    "score": 1.0,
                    "reason": "Dialogue strictly adheres to relevant academic research topics."
                })
            elif "tool" in low:
                return json.dumps({
                    "tool_calls": [{"name": "web_search", "parameters": {"query": "surface code error correction"}}],
                    "verdicts": [{"verdict": "yes", "reason": "Correct tool invoked for query"}],
                    "score": 1.0,
                    "reason": "All tool invocations matched available scholarly retrieval tools."
                })
            elif "complete" in low:
                return json.dumps({
                    "is_complete": True,
                    "score": 1.0,
                    "reason": "All researcher objectives were successfully answered."
                })
            elif "retention" in low or "knowledge" in low:
                return json.dumps({
                    "knowledge": ["Surface code threshold is approximately 1%"],
                    "score": 1.0,
                    "reason": "No factual contradictions or forgotten entities across conversation turns."
                })
            elif "faith" in low or "truth" in low or "claim" in low:
                return json.dumps({
                    "truths": ["Surface code error threshold is 1%"],
                    "claims": ["Surface code error threshold is 1%"],
                    "verdicts": [{"verdict": "yes", "reason": "Directly grounded in retrieval context"}],
                    "score": 1.0,
                    "reason": "Response statements are 100% faithful to the retrieval context."
                })
            return json.dumps({
                "score": 1.0,
                "reason": "High quality research alignment and factual consistency.",
                "is_complete": True,
                "verdict": "yes"
            })

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = _mock_judge_fn
        mock_llm.ainvoke.side_effect = _mock_judge_fn
        judge = ThothJudgeModel(model_instance=mock_llm, model_name="Thoth-Judge-Simulation")
        print(f"\n[INFO] Initialized Offline Thoth Judge Model: {judge.get_model_name()}")

    goldens = get_multiturn_goldens()
    print(f"[INFO] Loaded {len(goldens)} ConversationalGoldens spanning 8 scenario categories.\n")

    # Run simulation and evaluation
    if not args.live:
        mock_router = MagicMock()
        mock_router.invoke.side_effect = lambda inp: (
            '{"route": "LOCAL_QA", "reasoning": "Clarification answered by vault", "search_query": ""}'
            if "threshold" in inp.get("user_query", "").lower() or "clarif" in inp.get("user_query", "").lower() or "majorana" in inp.get("user_query", "").lower() or "source" in inp.get("user_query", "").lower() or "story" in inp.get("user_query", "").lower()
            else ('{"route": "REPORT_EXPANSION", "reasoning": "Section expansion requested", "search_query": ""}'
                  if "expand" in inp.get("user_query", "").lower() or "deep dive" in inp.get("user_query", "").lower() or "formalism" in inp.get("user_query", "").lower() or "comparative" in inp.get("user_query", "").lower()
                  else '{"route": "WEB_SEARCH", "reasoning": "External search required", "search_query": "' + inp.get("user_query", "") + '"}')
        )
        mock_qa = MagicMock()
        mock_qa.invoke.return_value = "Surface codes operate with ~1% physical error threshold under depolarizing noise models [src-quantum-surface-code]."
        mock_fu = MagicMock()
        mock_fu.invoke.return_value = '["How do logical error rates scale with code distance?", "What is the hardware overhead?"]'
        mock_sum = MagicMock()
        mock_sum.invoke.return_value = "Ongoing technical synthesis on fault-tolerant quantum error correction and topological qubits."

        with patch("backend.pipeline.router_chain", mock_router), \
             patch("backend.pipeline.mindmap_qa_chain", mock_qa), \
             patch("backend.pipeline.follow_up_chain", mock_fu), \
             patch("backend.pipeline.conversation_summarizer_chain", mock_sum):
            results = run_conversational_simulation_and_evals(
                goldens=goldens,
                judge=judge,
                max_user_simulations=args.max_simulations
            )
    else:
        results = run_conversational_simulation_and_evals(
            goldens=goldens,
            judge=judge,
            max_user_simulations=args.max_simulations
        )

    # Output detailed evaluation results
    print("\n" + "=" * 90)
    print("DETAILED SIMULATION RUN RESULTS (Per ConversationalGolden)")
    print("=" * 90)
    header = f"{'Scenario Name':<42} | {'Category':<22} | {'Turns':<5} | {'Comp':<5} | {'Ret':<5} | {'Topic':<5} | {'Faith':<5} | {'Rel':<5} | {'Tool':<5}"
    print(header)
    print("-" * len(header))

    for case in results["detailed_results"]:
        name = case["name"][:40]
        cat = case["scenario_type"][:20]
        turns = case["num_turns"]
        m = case["metrics"]
        s_comp = f"{m.get('completeness', {}).get('score', 0.0):.1f}"
        s_ret = f"{m.get('knowledge_retention', {}).get('score', 0.0):.1f}"
        s_top = f"{m.get('topic_adherence', {}).get('score', 0.0):.1f}"
        s_fth = f"{m.get('turn_faithfulness', {}).get('score', 0.0):.1f}"
        s_rel = f"{m.get('turn_contextual_relevancy', {}).get('score', 0.0):.1f}"
        s_tool = f"{m.get('tool_use', {}).get('score', 0.0):.1f}"
        print(f"{name:<42} | {cat:<22} | {turns:<5} | {s_comp:<5} | {s_ret:<5} | {s_top:<5} | {s_fth:<5} | {s_rel:<5} | {s_tool:<5}")

    # Output Aggregate Pass Rates
    print("\n" + "=" * 90)
    print("AGGREGATE PASS RATES (Score >= 0.70 Threshold)")
    print("=" * 90)
    for m_name, rate in results["pass_rate_by_metric"].items():
        status = "PASSED" if rate >= 0.70 else "FLAGGED"
        print(f"  • {m_name:<30}: {rate * 100:>5.1f}% | Status: {status}")

    # Output Granular Pass Rates by Scenario Type
    print("\n" + "=" * 90)
    print("GRANULAR PASS RATES BY SCENARIO TYPE")
    print("=" * 90)
    for sc_name, m_rates in results["pass_rate_by_scenario"].items():
        print(f"\n  [Scenario Category: {sc_name.upper()}]")
        for m_name, rate in m_rates.items():
            print(f"    - {m_name:<28}: {rate * 100:>5.1f}%")

    # Output Deterministic Search Stability Vault Note ID Overlap
    overlap_info = results.get("search_stability_overlap", {})
    if overlap_info:
        print("\n" + "=" * 90)
        print("DETERMINISTIC SEARCH STABILITY VAULT NOTE ID OVERLAP (3 Phrasings Check)")
        print("=" * 90)
        j_pct = overlap_info.get("jaccard_overlap_pct", 0.0)
        pair_avg = overlap_info.get("pairwise_avg_overlap_pct", 0.0)
        shared_ids = overlap_info.get("shared_note_ids", [])
        union_ids = overlap_info.get("union_note_ids", [])
        p_overlaps = overlap_info.get("pairwise_overlaps", {})
        is_stable = overlap_info.get("is_stable", False)

        print(f"  • 3-Way Jaccard Overlap Percentage : {j_pct:>5.1f}% | Status: {'STABLE (ISOLATED RETRIEVAL)' if is_stable else 'DRIFT DETECTED'}")
        print(f"  • Pairwise Average Overlap         : {pair_avg:>5.1f}%")
        print(f"  • Pairwise Breakdown:")
        print(f"      - Formulation A vs Formulation B : {p_overlaps.get('A_vs_B', 0.0):>5.1f}%")
        print(f"      - Formulation B vs Formulation C : {p_overlaps.get('B_vs_C', 0.0):>5.1f}%")
        print(f"      - Formulation A vs Formulation C : {p_overlaps.get('A_vs_C', 0.0):>5.1f}%")
        print(f"  • Shared Vault Note IDs (3-Way ∩)  : {shared_ids if shared_ids else '(none / all formulations empty)'}")
        print(f"  • Total Unique Note IDs (3-Way ∪)  : {union_ids if union_ids else '(none)'}")

    # Output Wasted-Token Tracking & Retrieval Precision
    wasted_info = results.get("wasted_token_metrics", {})
    if wasted_info:
        print("\n" + "=" * 90)
        print("WASTED-TOKEN TRACKING & RETRIEVAL PRECISION (Multi-Turn Dialogue Context)")
        print("=" * 90)
        print(f"  • Average Retrieval Precision : {wasted_info.get('avg_retrieval_precision', 1.0)*100:>5.1f}% (Cited Notes / Retrieved Notes)")
        print(f"  • Total Wasted Tokens Count   : {wasted_info.get('total_wasted_tokens', 0):>5} tokens (Unused retrieved note content)")
        print(f"  • Total Retrieved Tokens      : {wasted_info.get('total_retrieved_tokens', 0):>5} tokens")
        print(f"  • Wasted Token Volume Ratio   : {wasted_info.get('wasted_token_ratio', 0.0)*100:>5.1f}% of total retrieved vault tokens")
        print(f"  • Dialogue Turns Analyzed     : {wasted_info.get('turns_analyzed', 0):>5} turns")

    # Diagnostic Summary
    print("\n" + "=" * 90)
    print("DIAGNOSTIC ANALYSIS & ROOT-CAUSE MAPPING")
    print("=" * 90)
    followup_rates = [
        results["pass_rate_by_scenario"].get("followup_local_qa", {}).get("knowledge_retention", 1.0),
        results["pass_rate_by_scenario"].get("followup_local_qa", {}).get("turn_faithfulness", 1.0)
    ]
    new_topic_rate = results["pass_rate_by_scenario"].get("new_topic", {}).get("completeness", 1.0)
    tool_rate = results["pass_rate_by_metric"].get("tool_use", 1.0)
    stability_jaccard = overlap_info.get("jaccard_overlap_pct", 100.0)

    print(f"  1. Follow-up & Vault Session Memory Retention: {min(followup_rates) * 100:.1f}%")
    print("     -> Verifies whether Vault notes and rolling summaries retain entities across 3+ turns.")
    print(f"  2. New Topic Synthesis Completeness:           {new_topic_rate * 100:.1f}%")
    print("     -> Verifies whether initial research kickoff generates fully cited, structured reports.")
    print(f"  3. Tool Selection Stability Over Dialogue:      {tool_rate * 100:.1f}%")
    print("     -> Verifies whether Router tool selection remains sharp as conversation history grows.")
    print(f"  4. Deterministic Search Stability Overlap:     {stability_jaccard:.1f}%")
    print("     -> Isolates hybrid_search note retrieval from LLM judge generation variance.")
    print("=" * 90 + "\n")

    if args.save_json:
        with open(args.save_json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"[INFO] Saved complete evaluation results to {args.save_json}\n")


if __name__ == "__main__":
    main()
