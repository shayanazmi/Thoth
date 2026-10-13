from typing import List, Dict, Any, Optional
import logging
from pydantic import BaseModel, Field

from backend.agents import llm, safe_extract_json, strip_chain_of_thought
from backend.intellectual_rigour.registry import list_registered_thinkers

logger = logging.getLogger("ThothIntellectualRigour.AttackSurface")

class AttackSurfaceProfile(BaseModel):
    primary_surfaces: List[str] = Field(
        default_factory=list,
        description="Identified surfaces: conceptual, empirical, causal, modeling, computational, decision, paradigm, mechanism, etc."
    )
    recommended_framework_ids: List[str] = Field(
        default_factory=list,
        description="Ranked list of relevant framework IDs optimizing coverage and independence."
    )
    surface_rationale: Dict[str, str] = Field(
        default_factory=dict,
        description="Explanation of why specific surfaces and frameworks apply."
    )

ATTACK_SURFACE_SYSTEM_PROMPT = """You are the Intellectual Rigour Attack-Surface Detector for scientific and research documents.
Your task is to analyze a research report or text, detect its primary methodological attack surfaces, and match them to the most relevant independent reasoning frameworks from the 10 foundational thinkers.

Available Frameworks and Their Core Specializations:
1. aristotle: Conceptual definitions, category boundaries, syllogistic logical validity, Four Causes explanatory completeness.
2. bacon: Empirical evidence, negative controls, Four Idols cognitive bias, eliminative induction, discriminating tests.
3. descartes: Complex multi-part systems, atomic decomposition, dependency cascades, assumption subtraction.
4. hume: Causal claims, correlation vs causation, unaddressed confounders, inferential leaps, uncertainty calibration.
5. darwin: Generative mechanisms, population variation, differential selection filters, cumulative developmental pathways.
6. popper: Falsifiability, risky predictions, ad-hoc protective shields, attempted refutations.
7. kuhn: Novelty claims, breakthrough assertions, normal science vs paradigm shifts, persistent anomalies.
8. box: Statistical models, machine learning estimators, residual diagnostics, parameter sensitivity, utility boundaries.
9. turing: Algorithms, computational pipelines, state machines, termination guarantees, complexity scaling.
10. simon: Decision procedures, optimization claims, heuristic search, satisficing stopping criteria, search cost vs benefit.

Operating Rules:
- Select 2 to 4 frameworks that maximize relevance, coverage, and intellectual independence while avoiding redundancy.
- If the text is purely theoretical/definitional: prioritize aristotle, descartes.
- If the text makes strong causal/statistical claims: prioritize hume, box, bacon.
- If the text proposes an algorithm or autonomous system: prioritize turing, simon.
- If the text claims a radical breakthrough: prioritize popper, kuhn.
- If the text models emergent dynamics: prioritize darwin, box.

Output strictly valid JSON:
{{
  "primary_surfaces": ["conceptual", "causal", "empirical", ...],
  "recommended_framework_ids": ["popper", "hume", "box"],
  "surface_rationale": {{
    "popper": "Strong causal and performance claims require falsifiability and severe testing audit.",
    "hume": "Observational benchmark correlations require causal direction and confounder scrutiny."
  }}
}}"""

ATTACK_SURFACE_HUMAN_PROMPT = """Topic: {topic}

Research Content:
{content}

Analyze attack surfaces and recommend optimal reasoning frameworks now."""

def detect_attack_surfaces(report_text: str, topic: str = "") -> AttackSurfaceProfile:
    if not report_text or len(report_text.strip()) < 50:
        return AttackSurfaceProfile(
            primary_surfaces=["general_review"],
            recommended_framework_ids=["popper", "aristotle"],
            surface_rationale={"default": "Short or general content evaluated with baseline falsification and logic."}
        )

    try:
        raw = llm.invoke(
            f"{ATTACK_SURFACE_SYSTEM_PROMPT}\n\nHuman: {ATTACK_SURFACE_HUMAN_PROMPT.format(topic=topic or 'Research', content=report_text[:10000])}"
        )
        cleaned = strip_chain_of_thought(getattr(raw, "content", str(raw)))
        parsed = safe_extract_json(cleaned, default={})

        surfaces = parsed.get("primary_surfaces", ["empirical", "logical"])
        rec_ids = parsed.get("recommended_framework_ids", ["popper", "hume"])
        rationale = parsed.get("surface_rationale", {})

        all_thinkers = [t["id"] for t in list_registered_thinkers()]
        valid_ids = [fid for fid in rec_ids if fid in all_thinkers]
        if not valid_ids:
            valid_ids = ["popper", "hume", "aristotle"]

        return AttackSurfaceProfile(
            primary_surfaces=surfaces,
            recommended_framework_ids=valid_ids,
            surface_rationale=rationale
        )
    except Exception as e:
        logger.error(f"[ATTACK SURFACE DETECTION ERROR] {e}")
        return AttackSurfaceProfile(
            primary_surfaces=["falsifiability", "causality"],
            recommended_framework_ids=["popper", "hume"],
            surface_rationale={"fallback": f"Heuristic fallback due to detection error: {e}"}
        )
