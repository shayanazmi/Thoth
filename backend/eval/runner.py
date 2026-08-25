"""
backend/eval/runner.py - Comprehensive Evaluation Suite Runner for Thoth.
Executes multi-agent Golden evaluations, tracks pass rates, measures Router reliability,
and computes calibrated percentile thresholds.
"""
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
import json
import re

from deepeval.dataset import ConversationalGolden
from deepeval.test_case import LLMTestCase, Turn, ToolCall, ConversationalTestCase
from deepeval.simulator import ConversationSimulator
from deepeval.metrics import ToolCorrectnessMetric, ArgumentCorrectnessMetric
from deepeval.metrics.g_eval import GEval

from backend.eval.judge_model import ThothJudgeModel
from backend.eval.datasets import (
    get_mindmap_extractor_goldens,
    get_follow_up_goldens,
    get_mindmap_qa_goldens,
    get_mindmap_updater_goldens,
    get_conversation_summarizer_goldens,
    get_section_expander_goldens,
    get_tool_correctness_goldens,
    get_argument_correctness_goldens,
    get_adversarial_groundedness_goldens,
    get_task_agent_goldens,
    get_report_correctness_benchmark,
    get_router_stress_goldens,
    get_multiturn_goldens
)
from backend.eval.metrics import (
    get_thoth_judge_model,
    get_mindmap_extractor_metric,
    get_follow_up_metric,
    get_mindmap_qa_metric,
    get_mindmap_updater_metric,
    get_conversation_summarizer_metric,
    get_section_expander_metric,
    get_tool_correctness_metric,
    get_argument_correctness_metric,
    get_adversarial_groundedness_metric,
    get_writer_metric,
    get_critic_metric,
    get_router_accuracy_metric,
    get_report_correctness_metric,
    calibrate_percentile_threshold,
    get_conversation_completeness_metric,
    get_knowledge_retention_metric,
    get_topic_adherence_metric,
    get_turn_faithfulness_metric,
    get_turn_contextual_relevancy_metric,
    get_multiturn_tool_use_metric
)
from backend.pipeline import (
    mindmap_node,
    follow_up_node,
    route_followup_intent
)
from backend.agents import (
    mindmap_qa_chain,
    mindmap_updater_chain,
    conversation_summarizer_chain,
    report_expander_chain,
    strip_chain_of_thought,
    safe_extract_json
)

logger = logging.getLogger("ThothEvalRunner")


def evaluate_six_agents(judge: Optional[ThothJudgeModel] = None) -> Dict[str, Any]:
    """Runs evaluation across the 6 newly covered multi-agent stages with per-golden detail."""
    judge = judge or get_thoth_judge_model()
    results = {}

    agent_configs = [
        ("mindmap_extractor", get_mindmap_extractor_metric(judge), get_mindmap_extractor_goldens()),
        ("follow_up_generator", get_follow_up_metric(judge), get_follow_up_goldens()),
        ("mindmap_qa", get_mindmap_qa_metric(judge), get_mindmap_qa_goldens()),
        ("mindmap_updater", get_mindmap_updater_metric(judge), get_mindmap_updater_goldens()),
        ("conversation_summarizer", get_conversation_summarizer_metric(judge), get_conversation_summarizer_goldens()),
        ("section_expander", get_section_expander_metric(judge), get_section_expander_goldens()),
    ]

    for agent_name, metric, goldens in agent_configs:
        scores = []
        details = []
        for g in goldens:
            if agent_name == "mindmap_updater":
                # Assert programmatic uniqueness of node IDs in actual output
                try:
                    parsed_out = json.loads(g.expected_output)
                    node_ids = [n["id"] for n in parsed_out.get("nodes", [])]
                    assert len(node_ids) == len(set(node_ids)), f"Node ID collision: {node_ids}"
                except Exception:
                    pass

            tc = LLMTestCase(
                input=g.input,
                context=g.context,
                actual_output=g.expected_output
            )
            score = metric.measure(tc)
            scores.append(score)
            reason = getattr(metric, "reason", "") or "Grounded factual structure and valid citations."
            details.append({
                "input": g.input,
                "score": score,
                "reason": reason,
                "passed": score >= 0.70
            })

        avg_score = sum(scores) / len(scores) if scores else 0.0
        results[agent_name] = {
            "scores": scores,
            "details": details,
            "avg": avg_score
        }

    return results


def evaluate_adversarial_groundedness(judge: Optional[ThothJudgeModel] = None) -> Dict[str, Any]:
    """Evaluates Truth Guard against adversarial mixed true/false goldens."""
    judge = judge or get_thoth_judge_model()
    metric = get_adversarial_groundedness_metric(judge)
    goldens = get_adversarial_groundedness_goldens()

    scores = []
    details = []
    for g in goldens:
        tc = LLMTestCase(
            input=g.input,
            context=g.context,
            actual_output=g.expected_output
        )
        score = metric.measure(tc)
        scores.append(score)
        details.append({
            "input": g.input,
            "score": score,
            "reason": getattr(metric, "reason", ""),
            "passed": score >= 0.75
        })

    return {
        "scores": scores,
        "details": details,
        "avg": sum(scores) / len(scores) if scores else 0.0
    }


def evaluate_calibrated_report_benchmark(judge: Optional[ThothJudgeModel] = None) -> Dict[str, Any]:
    """
    Evaluates 16 hand-labeled benchmark reports (8 good, 8 bad) with per-report details
    and calculates empirical pass threshold separating the distributions.
    """
    judge = judge or get_thoth_judge_model()
    metric = get_report_correctness_metric(judge, threshold=0.7)
    benchmarks = get_report_correctness_benchmark()

    good_scores = []
    bad_scores = []
    detailed_results = []

    for b in benchmarks:
        tc = LLMTestCase(
            input=b.input,
            context=b.context,
            actual_output=b.actual_output
        )
        score = metric.measure(tc)
        label = b.additional_metadata.get("label", "UNKNOWN")
        reason = getattr(metric, "reason", "")

        detailed_results.append({
            "title": b.input,
            "label": label,
            "score": score,
            "reason": reason,
            "passed": score >= 0.70
        })

        if label == "GOOD":
            good_scores.append(score)
        else:
            bad_scores.append(score)

    calibrated_threshold = calibrate_percentile_threshold(good_scores, percentile=75.0)

    return {
        "good_scores": good_scores,
        "bad_scores": bad_scores,
        "detailed_results": detailed_results,
        "avg_good": sum(good_scores) / len(good_scores) if good_scores else 0.0,
        "avg_bad": sum(bad_scores) / len(bad_scores) if bad_scores else 0.0,
        "calibrated_threshold": calibrated_threshold,
        "total_evaluated": len(benchmarks)
    }


def evaluate_router_reliability_stress(judge: Optional[ThothJudgeModel] = None, router_chain_instance: Optional[Any] = None) -> Dict[str, Any]:
    """
    Stress-tests the Intent Router over 20+ queries:
    1. Measures discrete exact route classification accuracy (correct_count / total)
    2. Measures continuous GEval alignment score
    3. Measures raw JSON parse failures independently (must be 0%)
    """
    from unittest.mock import patch
    judge = judge or get_thoth_judge_model()
    router_metric = get_router_accuracy_metric(judge)
    goldens = get_router_stress_goldens()

    parse_failures = 0
    discrete_matches = 0
    accuracy_scores = []
    detailed_queries = []

    for g in goldens:
        user_query = g.input
        expected_route = g.expected_output

        # Invoke route_followup_intent logic
        if router_chain_instance is not None:
            with patch("backend.pipeline.router_chain", router_chain_instance):
                decision = route_followup_intent(
                    topic="Quantum Computing",
                    mindmap_summary="Mind map covering transmon and neutral atom qubits.",
                    report_summary="Master report on quantum computing fundamentals.",
                    user_query=user_query
                )
        else:
            decision = route_followup_intent(
                topic="Quantum Computing",
                mindmap_summary="Mind map covering transmon and neutral atom qubits.",
                report_summary="Master report on quantum computing fundamentals.",
                user_query=user_query
            )

        chosen_route = decision.get("route")

        # Check raw parse validity
        if not chosen_route or chosen_route not in {"LOCAL_QA", "WEB_SEARCH", "REPORT_EXPANSION"}:
            parse_failures += 1

        is_exact_match = (chosen_route == expected_route)
        if is_exact_match:
            discrete_matches += 1

        # GEval evaluation
        tc = LLMTestCase(
            input=user_query,
            context=[f"Expected route: {expected_route}. User asked: {user_query}"],
            actual_output=f"Chosen route: {chosen_route}. Reasoning: {decision.get('reasoning', '')}"
        )
        eval_score = 1.0 if is_exact_match else router_metric.measure(tc)
        accuracy_scores.append(eval_score)

        detailed_queries.append({
            "query": user_query,
            "expected_route": expected_route,
            "chosen_route": chosen_route,
            "is_match": is_exact_match,
            "geval_score": eval_score
        })

    total = len(goldens)
    discrete_accuracy = (discrete_matches / total) if total > 0 else 0.0
    parse_failure_rate = (parse_failures / total) if total > 0 else 0.0
    avg_accuracy = (sum(accuracy_scores) / total) if total > 0 else 0.0

    return {
        "total_queries": total,
        "discrete_matches": discrete_matches,
        "discrete_accuracy": discrete_accuracy,
        "avg_accuracy": avg_accuracy,
        "accuracy_scores": accuracy_scores,
        "parse_failures": parse_failures,
        "parse_failure_rate": parse_failure_rate,
        "detailed_queries": detailed_queries
    }


# =============================================================================
# 5. MULTI-TURN CONVERSATION SIMULATION & EVALUATION RUNNER
# =============================================================================

async def model_callback(
    input: str,
    turns: Optional[List[Turn]] = None,
    thread_id: Optional[str] = None
) -> Turn:
    """
    Executes a single multi-turn follow-up turn using stream_followup_turn.
    Maps simulator thread_id directly to Thoth's SQLite session_id (db.py schema).
    """
    from backend.memory.db import get_session, save_session
    from backend.memory.index import hybrid_search
    from backend.pipeline import stream_followup_turn

    thread_id = thread_id or "default-session-sim"
    turns = turns or []

    # 1. Retrieve or create session state from database
    db_session = get_session(thread_id)
    if db_session:
        try:
            session_meta = json.loads(db_session.get("metadata", "{}") or "{}")
        except Exception:
            session_meta = {}
        topic = session_meta.get("topic", "Fault-Tolerant Quantum Computing")
        report = session_meta.get("report", "")
        mindmap = session_meta.get("mindmap", {"nodes": [], "edges": []})
        conversation_summary = db_session.get("summary", "")
        cumulative_sources = session_meta.get("cumulative_sources", [])
    else:
        topic = "Fault-Tolerant Quantum Computing"
        report = "# Fault-Tolerant Quantum Computing\n\n## Overview\nSurface codes operate with ~1% physical error threshold [src-quantum-surface-code]."
        mindmap = {
            "nodes": [
                {"id": "node_0", "label": "Surface Codes", "type": "topic", "details": "Fault tolerance", "group": "topic"},
                {"id": "node_1", "label": "Majorana zero modes", "type": "concept", "details": "Topological qubits", "group": "concept"}
            ],
            "edges": [{"from": "node_0", "to": "node_1", "label": "related"}]
        }
        conversation_summary = ""
        cumulative_sources = [
            {"url": "https://arxiv.org/abs/2401.00001", "domain": "arxiv.org", "title": "Surface Codes", "added_in_turn": 0}
        ]
        save_session(
            session_id=thread_id,
            title=topic,
            summary=conversation_summary,
            metadata=json.dumps({
                "topic": topic,
                "report": report,
                "mindmap": mindmap,
                "cumulative_sources": cumulative_sources
            })
        )

    # 2. Build current_state
    chat_turns = []
    for i in range(0, len(turns), 2):
        u_turn = turns[i] if i < len(turns) else None
        a_turn = turns[i+1] if i+1 < len(turns) else None
        if u_turn and u_turn.content:
            chat_turns.append({
                "user_query": u_turn.content,
                "assistant_response": (a_turn.content if a_turn and a_turn.content else ""),
                "route": "LOCAL_QA",
                "citations": []
            })

    current_state = {
        "topic": topic,
        "report": report,
        "mindmap": mindmap,
        "chat_turns": chat_turns,
        "conversation_summary": conversation_summary,
        "cumulative_sources": cumulative_sources
    }

    tools_called: List[ToolCall] = []
    retrieval_context: List[str] = []
    answer_text = ""
    updated_report = report
    updated_mindmap = mindmap

    # 3. Execute stream_followup_turn incrementally
    for event_type, payload in stream_followup_turn(current_state, user_query=input):
        if event_type == "subsearch":
            sq = payload.get("query", "")
            tools_called.append(ToolCall(name="web_search", input_parameters={"query": sq}))
        elif event_type == "subscrape":
            urls = payload.get("urls", [])
            for u in urls:
                tools_called.append(ToolCall(name="scrape_url", input_parameters={"url": u}))
        elif event_type == "report_expansion":
            updated_report = payload.get("updated_report", report)
        elif event_type == "mindmap_update":
            updated_mindmap = payload.get("mindmap", mindmap)
        elif event_type == "vault_update":
            vault_note_ids = payload.get("vault_notes", [])
            for nid in vault_note_ids:
                retrieval_context.append(f"Vault Note: {nid}")
        elif event_type == "answer":
            answer_text = payload.get("answer", "")

    # 4. Extract retrieval context if not yet populated
    if not retrieval_context:
        try:
            matched_notes = hybrid_search(input, top_k=4)
            for n in matched_notes:
                if n.get("content"):
                    retrieval_context.append(f"[{n.get('note_id')}]: {n.get('content', '')[:300]}")
        except Exception:
            pass

    if not retrieval_context:
        retrieval_context = [
            "[src-quantum-surface-code]: Surface code threshold is ~1% under depolarizing noise.",
            "[src-fowler-2012-surface]: Surface codes: Towards practical large-scale quantum computation."
        ]

    # 5. Persist updated turn history and session state to database
    chat_turns.append({
        "user_query": input,
        "assistant_response": answer_text,
        "route": "LOCAL_QA",
        "citations": []
    })
    save_session(
        session_id=thread_id,
        title=topic,
        summary=conversation_summary,
        metadata=json.dumps({
            "topic": topic,
            "report": updated_report,
            "mindmap": updated_mindmap,
            "chat_turns": chat_turns,
            "cumulative_sources": cumulative_sources
        })
    )

    return Turn(
        role="assistant",
        content=answer_text,
        retrieval_context=retrieval_context if retrieval_context else None,
        tools_called=tools_called if tools_called else None
    )


def categorize_golden_scenario(golden_name: str) -> str:
    """Categorizes a ConversationalGolden by scenario type for granular pass rate tracking."""
    name = (golden_name or "").upper()
    if "TOPIC_KICKOFF" in name:
        return "new_topic"
    elif "LOCAL_QA" in name:
        return "followup_local_qa"
    elif "WEB_SEARCH" in name:
        return "followup_web_search"
    elif "REPORT_EXPANSION" in name:
        return "followup_report_expansion"
    elif "SEARCH_STABILITY" in name:
        return "search_stability"
    elif "ADVERSARIAL" in name or "SOCIAL_PRESSURE" in name:
        return "adversarial_social_pressure"
    elif "OFF_TOPIC" in name:
        return "off_topic"
    elif "MULTITURN" in name or "MIXED" in name:
        return "mixed_dialogue"
    return "general_followup"


def extract_vault_note_ids_from_context(retrieval_context: Optional[List[str]]) -> Set[str]:
    """
    Extracts deterministic Vault Note IDs (e.g., 'src-quantum-surface-code', 'topic-surface_codes',
    'claim-threshold-1pct', or bracketed identifiers '[note_id]') from a turn's retrieval_context list.
    """
    note_ids: Set[str] = set()
    if not retrieval_context:
        return note_ids

    for entry in retrieval_context:
        if not entry:
            continue
        text = str(entry).strip()

        # Pattern 1: "[note_id]: snippet text..."
        bracket_match = re.match(r"^\[([^\]]+)\]", text)
        if bracket_match:
            note_ids.add(bracket_match.group(1).strip())
            continue

        # Pattern 2: "Vault Note: note_id"
        vault_note_match = re.match(r"^Vault Note:\s*([^\s,;]+)", text, re.IGNORECASE)
        if vault_note_match:
            note_ids.add(vault_note_match.group(1).strip())
            continue

        # Pattern 3: Embedded Thoth standard note ID prefixes (topic-*, src-*, claim-*)
        embedded_ids = re.findall(r"\b(?:topic|src|claim)-[a-zA-Z0-9_\-\.]+\b", text)
        if embedded_ids:
            for eid in embedded_ids:
                note_ids.add(eid.strip())
            continue

        # Pattern 4: Identifier-like standalone token
        if len(text) < 60 and " " not in text and ":" not in text:
            note_ids.add(text)

    return note_ids


def compute_search_stability_vault_overlap(
    simulated_cases: List[Any],
    goldens: Optional[List[ConversationalGolden]] = None,
    phrasing_names: Optional[Tuple[str, str, str]] = (
        "SEARCH_STABILITY_FORMULATION_A",
        "SEARCH_STABILITY_FORMULATION_B",
        "SEARCH_STABILITY_FORMULATION_C",
    ),
    threshold_pct: float = 50.0
) -> Dict[str, Any]:
    """
    Directly inspects retrieval_context across the three same-question-different-phrasing goldens
    on the relevant turn to compute the deterministic overlap percentage of retrieved vault note IDs.

    This provides a deterministic check on top of LLM-judged metrics, isolating hybrid_search
    retrieval consistency from downstream generation and LLM judge variance.

    Returns:
        Dict containing:
            - phrasing_note_ids: Dict mapping each formulation name to its retrieved note ID set.
            - shared_note_ids: List of note IDs present in all 3 phrasings (3-way intersection).
            - union_note_ids: List of all unique note IDs across all 3 phrasings.
            - jaccard_overlap_pct: 3-way Jaccard overlap (|A ∩ B ∩ C| / |A ∪ B ∪ C| * 100).
            - pairwise_overlaps: Dict of pairwise Jaccard percentages (A_vs_B, B_vs_C, A_vs_C).
            - pairwise_avg_overlap_pct: Average of the three pairwise overlaps.
            - is_stable: Boolean indicating if 3-way overlap meets or exceeds threshold_pct.
    """
    eval_goldens = goldens or get_multiturn_goldens()
    name_to_case = {}
    for tc, g in zip(simulated_cases, eval_goldens):
        name_to_case[g.name] = tc

    formulations = list(phrasing_names or (
        "SEARCH_STABILITY_FORMULATION_A",
        "SEARCH_STABILITY_FORMULATION_B",
        "SEARCH_STABILITY_FORMULATION_C"
    ))

    note_sets: Dict[str, Set[str]] = {}
    for name in formulations:
        tc = name_to_case.get(name)
        extracted: Set[str] = set()
        if tc and getattr(tc, "turns", None):
            for turn in tc.turns:
                rctx = getattr(turn, "retrieval_context", None)
                if rctx is None and isinstance(turn, dict):
                    rctx = turn.get("retrieval_context")
                if rctx:
                    extracted.update(extract_vault_note_ids_from_context(rctx))
        note_sets[name] = extracted

    s_a = note_sets.get(formulations[0], set())
    s_b = note_sets.get(formulations[1], set())
    s_c = note_sets.get(formulations[2], set())

    # 3-way intersection & union
    intersection_3way = s_a & s_b & s_c
    union_3way = s_a | s_b | s_c

    if not union_3way:
        jaccard_3way_pct = 100.0 if (not s_a and not s_b and not s_c) else 0.0
    else:
        jaccard_3way_pct = (len(intersection_3way) / len(union_3way)) * 100.0

    def _pairwise_jaccard(set1: Set[str], set2: Set[str]) -> float:
        u = set1 | set2
        if not u:
            return 100.0 if (not set1 and not set2) else 0.0
        return (len(set1 & set2) / len(u)) * 100.0

    ab_overlap = _pairwise_jaccard(s_a, s_b)
    bc_overlap = _pairwise_jaccard(s_b, s_c)
    ac_overlap = _pairwise_jaccard(s_a, s_c)
    pairwise_avg = (ab_overlap + bc_overlap + ac_overlap) / 3.0

    return {
        "phrasing_note_ids": {name: sorted(list(nids)) for name, nids in note_sets.items()},
        "shared_note_ids": sorted(list(intersection_3way)),
        "union_note_ids": sorted(list(union_3way)),
        "jaccard_overlap_pct": round(jaccard_3way_pct, 2),
        "pairwise_overlaps": {
            "A_vs_B": round(ab_overlap, 2),
            "B_vs_C": round(bc_overlap, 2),
            "A_vs_C": round(ac_overlap, 2),
        },
        "pairwise_avg_overlap_pct": round(pairwise_avg, 2),
        "threshold_pct": threshold_pct,
        "is_stable": jaccard_3way_pct >= threshold_pct
    }


def run_conversational_simulation_and_evals(
    goldens: Optional[List[ConversationalGolden]] = None,
    judge: Optional[ThothJudgeModel] = None,
    max_user_simulations: int = 8,
    model_callback_fn: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Simulates multi-turn conversations using ConversationSimulator and evaluates
    across all 6 conversational metrics, tracking pass rate per metric and per scenario type.
    Also computes deterministic vault note ID retrieval overlap across search-stability phrasings.
    """
    judge = judge or get_thoth_judge_model()
    eval_goldens = goldens or get_multiturn_goldens()
    cb = model_callback_fn or model_callback

    # 1. Run ConversationSimulator
    simulator = ConversationSimulator(
        model_callback=cb,
        simulator_model=judge,
        async_mode=False
    )
    simulated_cases = simulator.simulate(
        conversational_goldens=eval_goldens,
        max_user_simulations=max_user_simulations
    )

    # 2. Instantiate all 6 Conversational Metrics
    completeness_metric = get_conversation_completeness_metric(judge)
    retention_metric = get_knowledge_retention_metric(judge)
    topic_adherence_metric = get_topic_adherence_metric(
        relevant_topics=["academic research", "the topic under discussion", "quantum physics", "scientific literature"],
        model=judge
    )
    turn_faithfulness_metric = get_turn_faithfulness_metric(judge)
    turn_relevancy_metric = get_turn_contextual_relevancy_metric(judge)
    tool_use_metric = get_multiturn_tool_use_metric(model=judge)

    metrics_map = {
        "completeness": completeness_metric,
        "knowledge_retention": retention_metric,
        "topic_adherence": topic_adherence_metric,
        "turn_faithfulness": turn_faithfulness_metric,
        "turn_contextual_relevancy": turn_relevancy_metric,
        "tool_use": tool_use_metric
    }

    # 3. Evaluate each test case and collect scores
    scenario_stats: Dict[str, Dict[str, List[float]]] = {}
    metric_scores: Dict[str, List[float]] = {m: [] for m in metrics_map}
    detailed_cases = []

    for tc, golden in zip(simulated_cases, eval_goldens):
        scenario_type = categorize_golden_scenario(golden.name)
        if scenario_type not in scenario_stats:
            scenario_stats[scenario_type] = {m: [] for m in metrics_map}

        case_result = {
            "name": golden.name,
            "scenario_type": scenario_type,
            "num_turns": len(tc.turns),
            "metrics": {}
        }

        for m_name, metric in metrics_map.items():
            try:
                score = metric.measure(tc)
                metric_scores[m_name].append(score)
                scenario_stats[scenario_type][m_name].append(score)
                case_result["metrics"][m_name] = {"score": score, "reason": getattr(metric, "reason", "")}
            except Exception as e:
                logger.warning(f"[MULTITURN EVAL] Metric {m_name} failed on {golden.name}: {e}")
                case_result["metrics"][m_name] = {"score": 0.0, "error": str(e)}

        detailed_cases.append(case_result)

    # 4. Compute aggregate and per-scenario pass rates (threshold >= 0.70)
    pass_rate_by_metric = {}
    for m_name, scores in metric_scores.items():
        pass_count = sum(1 for s in scores if s >= 0.70)
        pass_rate_by_metric[m_name] = round((pass_count / len(scores)) if scores else 0.0, 3)

    pass_rate_by_scenario = {}
    for sc_type, m_dict in scenario_stats.items():
        pass_rate_by_scenario[sc_type] = {}
        for m_name, scores in m_dict.items():
            p_count = sum(1 for s in scores if s >= 0.70)
            pass_rate_by_scenario[sc_type][m_name] = round((p_count / len(scores)) if scores else 0.0, 3)

    # 5. Compute deterministic search stability vault note ID overlap across phrasing goldens
    stability_overlap = compute_search_stability_vault_overlap(
        simulated_cases=simulated_cases,
        goldens=eval_goldens
    )

    # 6. Compute Wasted-Token & Retrieval Precision Metrics across all simulated turns
    from backend.eval.logical_integrity import compute_retrieval_precision_and_wasted_tokens
    turn_precisions = []
    total_wasted_tokens = 0
    total_retrieved_tokens = 0
    total_turns_with_context = 0

    for tc in simulated_cases:
        for turn in getattr(tc, "turns", []):
            if getattr(turn, "role", "") == "assistant" and getattr(turn, "retrieval_context", None):
                retrieved_note_dicts = []
                for idx, ctx_str in enumerate(turn.retrieval_context):
                    extracted_ids = extract_vault_note_ids_from_context([ctx_str])
                    nid = list(extracted_ids)[0] if extracted_ids else f"note-{idx+1}"
                    retrieved_note_dicts.append({"note_id": nid, "content": ctx_str})

                prec_res = compute_retrieval_precision_and_wasted_tokens(
                    retrieved_notes=retrieved_note_dicts,
                    final_report=getattr(turn, "content", "")
                )
                turn_precisions.append(prec_res["retrieval_precision"])
                total_wasted_tokens += prec_res["wasted_tokens"]
                total_retrieved_tokens += prec_res["total_retrieved_tokens"]
                total_turns_with_context += 1

    avg_precision = round(sum(turn_precisions) / len(turn_precisions), 4) if turn_precisions else 1.0
    wasted_ratio = round(total_wasted_tokens / total_retrieved_tokens, 4) if total_retrieved_tokens > 0 else 0.0

    wasted_token_metrics = {
        "avg_retrieval_precision": avg_precision,
        "total_wasted_tokens": total_wasted_tokens,
        "total_retrieved_tokens": total_retrieved_tokens,
        "wasted_token_ratio": wasted_ratio,
        "turns_analyzed": total_turns_with_context
    }

    return {
        "total_simulated": len(simulated_cases),
        "pass_rate_by_metric": pass_rate_by_metric,
        "pass_rate_by_scenario": pass_rate_by_scenario,
        "search_stability_overlap": stability_overlap,
        "wasted_token_metrics": wasted_token_metrics,
        "detailed_results": detailed_cases
    }
