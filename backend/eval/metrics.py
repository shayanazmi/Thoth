from typing import List, Optional, Dict, Any
import numpy as np

from deepeval.test_case import SingleTurnParams, ToolCall
from deepeval.metrics.g_eval import GEval
from deepeval.metrics import (
    ToolCorrectnessMetric,
    ArgumentCorrectnessMetric,
    TaskCompletionMetric,
    StepEfficiencyMetric,
    PlanAdherenceMetric,
    ConversationCompletenessMetric,
    KnowledgeRetentionMetric,
    TopicAdherenceMetric,
    TurnFaithfulnessMetric,
    TurnContextualRelevancyMetric,
    ToolUseMetric
)

from backend.eval.judge_model import ThothJudgeModel

def get_thoth_judge_model() -> ThothJudgeModel:
    return ThothJudgeModel(model_name="Thoth-Judge-LLM")

def get_mindmap_extractor_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="MindMapGraphCorrectness",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify the output contains valid 'nodes' and 'edges' lists.",
            "Check that node_0 is present and represents the core research topic.",
            "Confirm subtopic and finding nodes capture verified facts from the context.",
            "Verify all edges connect valid, existing node IDs without dangling links.",
            "Confirm all node IDs are distinct and unique without collisions."
        ],
        threshold=0.75,
        async_mode=False
    )

def get_follow_up_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="FollowUpQuestionQuality",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Check that output contains 2-3 concise, forward-looking research questions.",
            "Verify questions probe open problems, bottlenecks, or next research steps from the context.",
            "Confirm questions are technically specific to the topic rather than generic filler."
        ],
        threshold=0.75,
        async_mode=False
    )

def get_mindmap_qa_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="MindMapQAGrounding",
        model=judge,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify the answer directly answers the user's specific inquiry.",
            "Confirm all claims are strictly grounded in the provided mindmap context.",
            "Ensure citations format properly as clickable markdown links [Source](URL) when present in context."
        ],
        threshold=0.8,
        async_mode=False
    )

def get_mindmap_updater_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="MindMapUpdaterIntegrity",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Check that existing nodes and edges from the prior mindmap are preserved.",
            "Verify that newly added nodes have distinct unique IDs (e.g. with 'fu_node_' prefix) that do not collide with existing node IDs.",
            "Confirm newly added edges connect valid source and target nodes.",
            "Verify output is well-structured JSON with 'nodes' and 'edges'."
        ],
        threshold=0.8,
        async_mode=False
    )

def get_conversation_summarizer_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="ConversationSummarizerCompression",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify the summary retains key facts and inquiries from recent turns.",
            "Confirm core domain entities, metrics, and source URLs are preserved.",
            "Ensure the summary is dense, factual, and strictly under 200 words."
        ],
        threshold=0.75,
        async_mode=False
    )

def get_section_expander_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="ReportSectionExpanderQuality",
        model=judge,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify output begins immediately with a markdown section heading (e.g. '### Heading').",
            "Check that new research evidence is seamlessly and factually woven into the section text.",
            "Confirm the tone is academic and consistent without regenerating the entire master report.",
            "Confirm no chain-of-thought preamble or internal monologue is present in the output."
        ],
        threshold=0.8,
        async_mode=False
    )

def get_default_available_tools() -> List[ToolCall]:
    return [
        ToolCall(name="search_scholarly_sources", description="Academic discovery across arXiv, Semantic Scholar, OpenAlex"),
        ToolCall(name="search_tavily", description="Web search fallback when scholarly sources < 3"),
        ToolCall(name="concurrent_scrape_urls", description="Concurrently scrapes and extracts text from candidate URLs"),
        ToolCall(name="writer_node", description="Drafts synthesis report"),
        ToolCall(name="verifier_node", description="Truth Guard factual verification"),
        ToolCall(name="critic_node", description="Multi-dimensional quality critique"),
        ToolCall(name="mindmap_node", description="Extracts hierarchical concept mindmap"),
        ToolCall(name="follow_up_node", description="Generates dynamic follow-up research questions")
    ]

def get_tool_correctness_metric(
    model: Optional[ThothJudgeModel] = None,
    available_tools: Optional[List[ToolCall]] = None,
    threshold: float = 0.8
) -> ToolCorrectnessMetric:
    judge = model or get_thoth_judge_model()
    tools = available_tools if available_tools is not None else get_default_available_tools()
    return ToolCorrectnessMetric(
        threshold=threshold,
        model=judge,
        available_tools=tools,
        include_reason=True,
        async_mode=False
    )

def get_argument_correctness_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> ArgumentCorrectnessMetric:
    judge = model or get_thoth_judge_model()
    return ArgumentCorrectnessMetric(
        threshold=threshold,
        model=judge,
        include_reason=True,
        async_mode=False
    )

def get_adversarial_groundedness_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="ThothAdversarialGroundedness",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Check that every verified claim (is_valid: true) specifies a real matching supporting_source_id from the context.",
            "Verify that ungrounded, contradicted, or fabricated claims are strictly marked is_valid: false.",
            "Confirm that false claims provide a clear explanation in reason_if_failed.",
            "Ensure that no false or fabricated claim is given a manufactured source citation."
        ],
        threshold=0.85,
        async_mode=False
    )

def get_writer_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="WriterSynthesisQuality",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify the report has clear markdown headings (Executive Summary, Findings, etc.).",
            "Check that all factual assertions are backed by explicit source citations [src-...].",
            "Confirm the prose is rigorous, academic, and free from unsupported generalizations."
        ],
        threshold=0.8,
        async_mode=False
    )

def get_critic_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="CriticEvaluationQuality",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify the critique provides scores for all 5 dimensions plus overall_score.",
            "Confirm scores accurately reflect the depth and grounding of the evaluated draft.",
            "Check that actionable improvement suggestions and strengths are clearly articulated."
        ],
        threshold=0.8,
        async_mode=False
    )

def get_router_accuracy_metric(model: Optional[ThothJudgeModel] = None) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="IntentRouterDecisionQuality",
        model=judge,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify the routing choice (LOCAL_QA, WEB_SEARCH, REPORT_EXPANSION) is optimal for the query.",
            "Confirm queries answerable from existing report are assigned to LOCAL_QA.",
            "Confirm queries asking for new external facts are assigned to WEB_SEARCH.",
            "Confirm queries requesting report updates/sections are assigned to REPORT_EXPANSION."
        ],
        threshold=0.8,
        async_mode=False
    )

def get_report_correctness_metric(model: Optional[ThothJudgeModel] = None, threshold: float = 0.7) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="ThothReportCorrectness",
        model=judge,
        evaluation_params=[SingleTurnParams.CONTEXT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Verify every factual claim is strictly traceable to the provided source context.",
            "Flag and penalize any claim that is exaggerated, fabricated, or contradicted by source facts.",
            "Check that citations correspond to real verified sources rather than placeholder labels.",
            "Confirm the overall report follows structured, professional academic formatting."
        ],
        threshold=threshold,
        async_mode=False
    )

def calibrate_percentile_threshold(scores: List[float], percentile: float = 75.0) -> float:
    if not scores:
        return 0.7
    arr = np.array(scores)

    val = float(np.percentile(arr, 100.0 - percentile))

    return max(0.50, min(0.95, round(val, 2)))

def get_task_completion_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7,
    task: Optional[str] = None
) -> TaskCompletionMetric:
    judge = model or get_thoth_judge_model()
    return TaskCompletionMetric(
        model=judge,
        threshold=threshold,
        task=task,
        include_reason=True,
        async_mode=False
    )

def get_step_efficiency_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> StepEfficiencyMetric:
    judge = model or get_thoth_judge_model()
    return StepEfficiencyMetric(
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_plan_adherence_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> PlanAdherenceMetric:
    judge = model or get_thoth_judge_model()
    return PlanAdherenceMetric(
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_conversation_completeness_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> ConversationCompletenessMetric:
    judge = model or get_thoth_judge_model()
    return ConversationCompletenessMetric(
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_knowledge_retention_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> KnowledgeRetentionMetric:
    judge = model or get_thoth_judge_model()
    return KnowledgeRetentionMetric(
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_topic_adherence_metric(
    relevant_topics: Optional[List[str]] = None,
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> TopicAdherenceMetric:
    judge = model or get_thoth_judge_model()
    topics = relevant_topics or ["academic research", "the topic under discussion", "quantum physics", "scientific literature"]
    return TopicAdherenceMetric(
        relevant_topics=topics,
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_turn_faithfulness_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> TurnFaithfulnessMetric:
    judge = model or get_thoth_judge_model()
    return TurnFaithfulnessMetric(
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_turn_contextual_relevancy_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> TurnContextualRelevancyMetric:
    judge = model or get_thoth_judge_model()
    return TurnContextualRelevancyMetric(
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_multiturn_tool_use_metric(
    available_tools: Optional[List[ToolCall]] = None,
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.7
) -> ToolUseMetric:
    judge = model or get_thoth_judge_model()
    tools = available_tools or [
        ToolCall(name="web_search", input_parameters={"query": "str"}),
        ToolCall(name="scrape_url", input_parameters={"url": "str"})
    ]
    return ToolUseMetric(
        available_tools=tools,
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False
    )

def get_causal_comparative_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.70
) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="Causal & Comparative Modality Integrity",
        criteria="Evaluate whether output claims strictly preserve epistemic modality without unjustified causal or superlative promotion.",
        evaluation_steps=[
            "Check if statistical correlation in retrieval context is falsely stated as direct, unmediated causation.",
            "Check if specific benchmark points are promoted to absolute superlatives (e.g. 'always superior', 'flawless in every metric').",
            "Verify that nuances, limitations, and trade-offs presented in the source context are accurately maintained.",
            "Penalize any unjustified inflation of certainty or strength relative to the evidence."
        ],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT
        ],
        model=judge,
        threshold=threshold,
        async_mode=False
    )

def get_non_sequitur_conclusion_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.70
) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="Non-Sequitur & Conclusion Groundedness",
        criteria="Evaluate whether the report conclusion logically derives from cited body claims without ungrounded leaps.",
        evaluation_steps=[
            "Identify all claims and predictions made in the report's conclusion or summary section.",
            "Verify that every conclusion claim has direct precursor evidence cited in the body of the report.",
            "Check for non-sequitur leaps, unsupported future predictions, or exaggerated claims not grounded in body evidence.",
            "Heavily penalize conclusions that introduce new factual assertions without supporting citations."
        ],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT
        ],
        model=judge,
        threshold=threshold,
        async_mode=False
    )

def get_truth_guard_faithfulness_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.80
) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="TruthGuardFaithfulness",
        criteria="Evaluate whether drafted claims strictly entail from the retrieved and snowballed evidence without hallucinations.",
        evaluation_steps=[
            "Extract all atomic factual statements and numerical/methodological claims from the output.",
            "Cross-examine each claim against the provided retrieval context and full-text snippets.",
            "Verify that citations specifically link each claim to an indexed source note ([[src-...]]).",
            "Score 1.0 if all claims are fully supported; penalize proportionally for unsupported or exaggerated assertions."
        ],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT
        ],
        model=judge,
        threshold=threshold,
        async_mode=False
    )

def get_multi_corpus_retrieval_metric(
    model: Optional[ThothJudgeModel] = None,
    threshold: float = 0.75
) -> GEval:
    judge = model or get_thoth_judge_model()
    return GEval(
        name="MultiCorpusRetrievalDiversity",
        criteria="Evaluate the diversity, relevance, and academic credibility of retrieved federated candidates.",
        evaluation_steps=[
            "Confirm retrieved sources span relevant peer-reviewed literature or authoritative preprints.",
            "Verify the search results correctly capture key papers, landmark studies, and recent breakthroughs for the inquiry.",
            "Check that sources contain valid titles, URLs, abstracts, and author attributions without placeholder data."
        ],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT
        ],
        model=judge,
        threshold=threshold,
        async_mode=False
    )

def calculate_mrr_and_hit_rate(
    retrieved_candidates: List[Any],
    relevant_keys: List[str],
    k: int = 5
) -> Dict[str, float]:
    if not relevant_keys:
        return {"mrr@k": 0.0, "hit_rate@k": 0.0}

    norm_targets = {k.lower().strip() for k in relevant_keys}
    top_k = retrieved_candidates[:k]

    reciprocal_rank = 0.0
    hit = 0.0

    for rank, cand in enumerate(top_k, start=1):
        cand_keys = set()
        if hasattr(cand, "doi") and cand.doi:
            cand_keys.add(cand.doi.lower().strip())
        if hasattr(cand, "arxiv_id") and cand.arxiv_id:
            cand_keys.add(cand.arxiv_id.lower().strip())
        if hasattr(cand, "title") and cand.title:
            cand_keys.add(cand.title.lower().strip())
        elif isinstance(cand, dict):
            for field in ("doi", "arxiv_id", "title", "url"):
                if cand.get(field):
                    cand_keys.add(str(cand[field]).lower().strip())

        if any(tk in cand_keys or any(tk in ck for ck in cand_keys) for tk in norm_targets):
            reciprocal_rank = 1.0 / rank
            hit = 1.0
            break

    return {
        f"mrr@{k}": round(reciprocal_rank, 4),
        f"hit_rate@{k}": round(hit, 4)
    }

