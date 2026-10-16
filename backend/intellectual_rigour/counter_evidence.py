import re
import uuid
import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.intellectual_rigour.matcher import ARCHETYPE_DEFINITIONS


class CounterEvidenceQuery(BaseModel):
    query: str = Field(..., description="Scholarly search query designed to retrieve counter-evidence or negative results")
    target_aspect: str = Field(..., description="The specific assumption, causal link, or boundary condition targeted")
    thinker_framework: str = Field(..., description="The thinker perspective motivating this challenge (e.g., popper, hume, box)")
    expected_falsification_signal: str = Field(..., description="What findings in retrieved literature would contradict the hypothesis")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class CounterEvidencePlan(BaseModel):
    hypothesis: str = Field(..., description="The hypothesis subjected to adversarial falsification planning")
    thinker_id: Optional[str] = Field(default=None, description="Primary thinker framework guiding the critique")
    target_bias: Optional[str] = Field(default=None, description="Primary cognitive or epistemic bias being countered")
    objections: List[str] = Field(default_factory=list, description="Unresolved objections or sparring challenges")
    queries: List[CounterEvidenceQuery] = Field(default_factory=list, description="Targeted counter-evidence search queries")
    falsification_criteria: List[str] = Field(default_factory=list, description="Explicit conditions under which hypothesis would be disproven")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class HypothesisRevisionProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: f"prop-{uuid.uuid4().hex[:10]}")
    idea_id: str = Field(..., description="ID of the research idea this proposal refines")
    current_hypothesis: str = Field(..., description="The original persisted hypothesis (preserved unchanged)")
    proposed_refined_hypothesis: str = Field(..., description="Recommended refinement accounting for counter-evidence")
    motivating_thinker_id: Optional[str] = Field(default=None, description="Thinker whose objection surfaced the counter-evidence")
    motivating_objection: str = Field(..., description="The specific critique or objection addressed")
    discovered_counter_evidence_summary: str = Field(..., description="Summary of retrieved contradictory evidence")
    relevant_source_ids: List[str] = Field(default_factory=list, description="Source IDs of literature containing counter-evidence")
    rationale: str = Field(..., description="Epistemic rationale explaining why this refinement preserves validity")
    candidate_revisions: List[Dict[str, str]] = Field(default_factory=list, description="Structured candidate revisions (e.g. boundary-conditioned, mechanistic, scoped)")
    boundary_conditions: List[str] = Field(default_factory=list, description="Explicit conditions under which the hypothesis holds")
    created_at: str = Field(default_factory=lambda: datetime.timezone.utc and datetime.datetime.now(datetime.timezone.utc).isoformat())

    @property
    def counter_evidence_summary(self) -> str:
        return self.discovered_counter_evidence_summary

    def to_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["counter_evidence_summary"] = self.discovered_counter_evidence_summary
        return d


# Framework-specific counter-evidence search templates and falsification heuristics
FRAMEWORK_COUNTER_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "popper": {
        "aspect": "Empirical Falsifiability & Failed Replications",
        "target_bias": "Confirmation bias & verificationism",
        "query_suffixes": [
            "failure to replicate OR null effect",
            "refutation OR contradictory evidence",
            "falsification OR negative result"
        ],
        "signal": "Empirical benchmarks reporting null effects or failed replications under identical experimental conditions.",
        "default_criteria": [
            "Observing a null effect or failed replication under identical controlled conditions.",
            "Demonstrating that the predicted outcome fails to occur when boundary conditions are satisfied.",
            "Experimental evidence that directly falsifies the primary hypothesized effect."
        ]
    },
    "hume": {
        "aspect": "Causal Directionality & Confounding Variables",
        "target_bias": "Spurious correlation & confounding bias",
        "query_suffixes": [
            "confounding variables OR spurious correlation",
            "reverse causality OR common cause",
            "observational bias OR unmeasured confounder"
        ],
        "signal": "Studies demonstrating that the observed relationship vanishes once controlling for third-variable confounders.",
        "default_criteria": [
            "Demonstrating that the association disappears when adjusting for confounding covariates.",
            "Showing that reverse causality accounts for the empirical correlation."
        ]
    },
    "box": {
        "aspect": "Model Misspecification & Boundary Utility",
        "target_bias": "Overfitting & model misspecification",
        "query_suffixes": [
            "model misspecification OR parameter sensitivity",
            "out of distribution failure OR domain breakdown",
            "overfitting OR residual pathology"
        ],
        "signal": "Evidence that model performance collapses outside narrowly tuned hyperparameter regimes.",
        "default_criteria": [
            "Demonstrating severe performance degradation under realistic distributional shift.",
            "Showing that parameter sensitivity and domain breakdown occur outside calibrated thresholds.",
            "Showing that parameter perturbations beyond epsilon destabilize predictive utility."
        ]
    },
    "kuhn": {
        "aspect": "Paradigm Anomalies & Incommensurability",
        "target_bias": "Normal science dogmatism & paradigm blindness",
        "query_suffixes": [
            "anomalies OR paradigm limitations",
            "incommensurable results OR theoretical conflict",
            "unresolved anomalies in literature"
        ],
        "signal": "Systematic experimental anomalies accumulated across studies that cannot be accommodated by the standard framework.",
        "default_criteria": [
            "Replication of known anomalies that standard theoretical models cannot explain.",
            "Evidence that contradictory findings persist across independent laboratories."
        ]
    },
    "simon": {
        "aspect": "Bounded Rationality & Computational Intractability",
        "target_bias": "Unbounded rationality & computational intractability",
        "query_suffixes": [
            "computational intractability OR search cost",
            "heuristic failure OR satisficing limits",
            "exponential complexity OR resource exhaustion"
        ],
        "signal": "Evidence that the proposed decision mechanism exceeds realistic computational or informational budgets.",
        "default_criteria": [
            "Demonstrating that computational complexity scales exponentially with input dimension.",
            "Showing that heuristic search fails to converge within bounded resource budgets."
        ]
    },
    "bacon": {
        "aspect": "Observational Artifacts & Negative Instances",
        "target_bias": "Observational selection & measurement artifact",
        "query_suffixes": [
            "sampling bias OR measurement bias",
            "negative instances OR observation artifact",
            "systematic error in measurement"
        ],
        "signal": "Empirical tables documenting negative instances systematically omitted in initial reports.",
        "default_criteria": [
            "Documentation of negative instances where the expected causal factor operates without the expected effect.",
            "Discovery that positive findings were artifacts of experimental instrument calibration."
        ]
    },
    "aristotle": {
        "aspect": "Category Equivocation & Teleological Confusion",
        "target_bias": "Teleological bias & essentialist assumptions",
        "query_suffixes": [
            "efficient cause OR counter-examples",
            "category error OR conceptual equivocation",
            "teleological fallacy in explanation"
        ],
        "signal": "Methodological critiques proving that distinct phenomena were conflated under an ambiguous umbrella term.",
        "default_criteria": [
            "Proof that the operational definition conflates two functionally distinct constructs.",
            "Demonstration that the primary causal claim relies on a circular or teleological definition."
        ]
    },
    "descartes": {
        "aspect": "Foundational Axiom & Dependency Breakdown",
        "target_bias": "Uncritical presupposition & unwarranted certainty",
        "query_suffixes": [
            "unstated assumption OR boundary condition",
            "foundational assumption failure",
            "dependency cascade failure"
        ],
        "signal": "Analyses showing that the foundational premise upon which the multi-layer pipeline rests is empirically invalid.",
        "default_criteria": [
            "Falsification of the foundational baseline axiom underpinning the architecture.",
            "Demonstration that subtracting the unproven assumption collapses the downstream pipeline."
        ]
    },
    "darwin": {
        "aspect": "Non-Adaptive Drift & Selection Neutrality",
        "target_bias": "Static optimality & adaptationism",
        "query_suffixes": [
            "maladaptive OR evolutionary bottleneck",
            "neutral drift OR non-adaptive explanation",
            "random variation vs selection"
        ],
        "signal": "Genetic or developmental evidence showing that the trait arose through random drift rather than positive selection.",
        "default_criteria": [
            "Evidence that genetic or functional variation is consistent with neutral evolutionary drift.",
            "Showing that phenotypic differences do not confer measurable differential fitness."
        ]
    },
    "turing": {
        "aspect": "State Space Explosion & Halting Limits",
        "target_bias": "Functional mimicry & behavioral equivalence",
        "query_suffixes": [
            "adversarial perturbation OR behavioral failure",
            "undecidability OR halting problem",
            "algorithmic non-termination"
        ],
        "signal": "Formal proofs or simulations showing non-termination or algorithmic divergence in edge states.",
        "default_criteria": [
            "Identification of reachable degenerate states that induce non-termination.",
            "Proof of worst-case superpolynomial complexity on valid input sets."
        ]
    }
}


def _extract_core_entities(text: str) -> List[str]:
    """
    Extract meaningful topical noun phrases from a hypothesis or topic string.
    """
    # Remove common filler phrases
    clean = re.sub(
        r'\b(we hypothesize that|my hypothesis is that|our hypothesis is that|it is hypothesized that|the hypothesis that|does|can|will|should|could|would|that|this|with|from|into|about)\b',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Extract substantive words (len >= 4)
    words = [w for w in re.findall(r'[a-zA-Z0-9_\-]+', clean) if len(w) >= 4 and not w.lower().endswith("ing")]
    return words[:5]


def generate_counter_evidence_plan(
    hypothesis: str,
    thinker_id: Optional[str] = None,
    objections: Optional[List[str]] = None,
    topic: str = "",
) -> CounterEvidencePlan:
    """
    Translate substantive thinker critiques and open objections into explicit
    counter-evidence search queries and falsification criteria.
    """
    clean_hypo = (hypothesis or "").strip()
    tid = (thinker_id or "popper").strip().lower()
    if tid not in FRAMEWORK_COUNTER_TEMPLATES:
        tid = "popper"

    fw_info = FRAMEWORK_COUNTER_TEMPLATES[tid]
    active_objections = list(objections or [])

    # Identify topical terms
    topic_clean = (topic or "").strip()
    if not topic_clean or len(topic_clean) < 5:
        entities = _extract_core_entities(clean_hypo)
        topic_clean = " ".join(entities[:3]) if entities else "empirical investigation"

    queries: List[CounterEvidenceQuery] = []
    falsification_criteria: List[str] = list(fw_info.get("default_criteria", []))

    # 1. Generate framework-specific adversarial queries
    for suffix in fw_info["query_suffixes"]:
        q_str = f"{topic_clean} {suffix}"
        queries.append(
            CounterEvidenceQuery(
                query=q_str,
                target_aspect=fw_info["aspect"],
                thinker_framework=tid,
                expected_falsification_signal=fw_info["signal"],
            )
        )

    # 2. Translate explicit user or thinker objections into targeted queries
    stopwords = {
        "that", "this", "with", "from", "into", "during", "including", "until",
        "against", "among", "throughout", "despite", "towards", "upon", "concerning",
        "leads", "lead", "grows", "grow", "such", "been", "have", "were", "what",
        "which", "when", "where", "while", "data"
    }
    for obj in active_objections:
        obj_clean = obj.strip().rstrip("?.,;:")
        if len(obj_clean) > 10:
            obj_words = [w for w in re.findall(r'[a-zA-Z0-9_\-]+', obj_clean) if len(w) >= 4 and w.lower() not in stopwords]
            if obj_words:
                specific_q = f"{topic_clean} {' '.join(obj_words[:4])} counter-evidence"
                queries.append(
                    CounterEvidenceQuery(
                        query=specific_q,
                        target_aspect=f"Unresolved Objection: {obj_clean[:60]}...",
                        thinker_framework=tid,
                        expected_falsification_signal=f"Literature investigating whether {obj_clean}.",
                    )
                )
            falsification_criteria.append(f"Empirical confirmation that {obj_clean}.")

    return CounterEvidencePlan(
        hypothesis=clean_hypo,
        thinker_id=tid,
        target_bias=fw_info.get("target_bias"),
        objections=active_objections,
        queries=queries,
        falsification_criteria=falsification_criteria,
    )


def generate_hypothesis_revision_proposal(
    idea_id: str,
    current_hypothesis: str,
    counter_evidence_findings: List[Dict[str, Any]],
    thinker_id: Optional[str] = None,
    objection: str = "",
) -> HypothesisRevisionProposal:
    """
    Formulate an inspectable hypothesis revision recommendation grounded in discovered
    counter-evidence and thinker objections, strictly preserving user agency without
    silently overwriting the persisted hypothesis.
    """
    tid = (thinker_id or "popper").strip().lower()
    clean_hypo = (current_hypothesis or "").strip()

    # Summarize counter evidence
    evidence_snippets = []
    source_ids = []
    for f in counter_evidence_findings:
        sid = f.get("source_id") or f.get("id") or f.get("url")
        if sid:
            source_ids.append(str(sid))
        snippet = f.get("finding") or f.get("snippet") or f.get("summary") or f.get("claim") or ""
        if snippet:
            evidence_snippets.append(snippet.strip())

    counter_summary = (
        " ".join(evidence_snippets[:3])
        if evidence_snippets
        else "Discovered contradictory literature demonstrating boundary condition failures or unaddressed confounding variables."
    )

    clean_obj = (objection or "").strip()
    if not clean_obj:
        clean_obj = f"Substantive {tid.title()} critique identifying unconstrained boundary conditions or alternative mechanisms."

    # Formulate refined hypothesis grounded in thinker perspective
    if tid == "hume":
        refined = f"{clean_hypo} — restricted to settings where third-variable confounders are explicitly controlled."
        rationale = "Constrains causal assertion to isolated, confounder-controlled experimental designs as mandated by Humean skepticism."
    elif tid == "box":
        refined = f"{clean_hypo} — bounded within specified parameter ranges and domain distributions."
        rationale = "Explicitly bounds the domain of model applicability, preventing unwarranted out-of-distribution generalization."
    elif tid == "simon":
        refined = f"{clean_hypo} — under bounded computational and time-budget constraints."
        rationale = "Accounts for cognitive/computational budget bounds, avoiding unrealistic optimal-search assumptions."
    elif tid == "popper":
        refined = f"{clean_hypo} — specifying precise falsifiable boundary thresholds and operational negative controls."
        rationale = "Enhances empirical falsifiability by incorporating explicit operational negative controls."
    else:
        refined = f"{clean_hypo} — constrained by verified empirical boundary conditions."
        rationale = f"Refines the core hypothesis to reconcile observed contradictions highlighted by {tid.title()}."

    candidate_revisions = [
        {
            "type": "scoped_applicability",
            "revised_hypothesis": refined,
            "rationale": rationale,
        },
        {
            "type": "mechanistic_qualification",
            "revised_hypothesis": f"{clean_hypo} provided that the causal mechanism operates via verifiable intermediate pathways.",
            "rationale": f"Addresses {clean_obj[:50]} by qualifying the necessary operational mechanism.",
        },
        {
            "type": "falsifiable_boundary",
            "revised_hypothesis": f"{clean_hypo} under strict operational bounds, subject to falsification if baseline controls match performance.",
            "rationale": "Defines explicit empirical test limits and falsification criteria.",
        },
    ]

    boundary_conditions = [
        f"Applies when {clean_obj[:60]} is explicitly accounted for",
        "Requires controlled baseline comparisons against non-treated counterparts",
    ]

    return HypothesisRevisionProposal(
        idea_id=idea_id,
        current_hypothesis=clean_hypo,
        proposed_refined_hypothesis=refined,
        motivating_thinker_id=tid,
        motivating_objection=clean_obj,
        discovered_counter_evidence_summary=counter_summary,
        relevant_source_ids=source_ids,
        rationale=rationale,
        candidate_revisions=candidate_revisions,
        boundary_conditions=boundary_conditions,
    )

