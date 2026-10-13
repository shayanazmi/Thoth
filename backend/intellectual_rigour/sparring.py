import os
import re
import yaml
import logging
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.agents import llm, safe_extract_json, strip_chain_of_thought
from backend.intellectual_rigour.registry import get_framework, list_registered_thinkers
from backend.intellectual_rigour.matcher import ARCHETYPE_DEFINITIONS, match_ideation_archetype

logger = logging.getLogger("ThothIntellectualRigour.Sparring")

_FRAMEWORKS_BASE_DIR = os.path.join(os.path.dirname(__file__), "frameworks")
_PROMPT_CACHE: Dict[str, Dict[str, str]] = {}

class EscalationProposal(BaseModel):
    is_ready_for_research: bool = Field(default=False, description="True if dialectic has forged a testable hypothesis.")
    readiness_score: float = Field(default=0.0, description="Readiness score from 0.0 to 1.0.")
    crystallized_topic: str = Field(default="", description="Refined, rigorous academic research topic.")
    testable_hypothesis: str = Field(default="", description="The specific core hypothesis forged.")
    identified_constraints: List[str] = Field(default_factory=list, description="Methodological boundaries, axioms, or controls.")
    falsification_or_test_criteria: str = Field(default="", description="Empirical or operational criteria required for verification.")
    action_pill_label: str = Field(default="", description="UI button label for launching research.")
    escalation_reason: str = Field(default="", description="Why this conversation is now ripe for deep scholarly research.")

class SparringTurnOutput(BaseModel):
    thinker_id: str
    thinker_name: str
    archetype: str
    reply: str
    turn_count: int
    escalation_proposal: Optional[EscalationProposal] = None

def _load_thinker_knowledge(thinker_id: str) -> Dict[str, str]:
    if thinker_id in _PROMPT_CACHE:
        return _PROMPT_CACHE[thinker_id]

    tid_dir = os.path.join(_FRAMEWORKS_BASE_DIR, thinker_id)
    out = {
        "historical_basis": "",
        "modern_adaptation": "",
        "operational_algo": "",
    }

    if os.path.exists(tid_dir):
        for key in ["historical_basis", "modern_adaptation", "operational_algo"]:
            p = os.path.join(tid_dir, f"{key}.md")
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        out[key] = f.read().strip()
                except Exception as e:
                    logger.warning(f"[SPARRING] Failed to read {p}: {e}")

    _PROMPT_CACHE[thinker_id] = out
    return out

SPARRING_SYSTEM_PROMPT_TEMPLATE = """You are {thinker_name}, operating as an incisive, Socratic sparring partner in the Thoth Epistemic Research Engine.
Your tradition is {tradition}, and your core ideation archetype is "{archetype}".

YOUR CORE EPISTEMIC IDENTITY & METHOD:
{modern_adaptation}

OPERATIONAL DECISION RULES:
{operational_algo}

YOUR MISSION DURING BRAINSTORMING:
1. DO NOT ACT AS A FLAT, FLATTERING ASSISTANT. Never say "Great idea!" or "That sounds fascinating!".
2. SOCRATIC RIGOUR: Immediately hunt the weakest link, vague buzzword, unexamined axiom, or missing control in the researcher's idea.
3. IN-CHARACTER TONE: Embody your historical intellect translated into modern scientific and computational thinking. Speak with authority, incisiveness, and philosophical gravity.
4. PUSH FORWARD: Guide the researcher through three distinct phases across the conversation:
   - Phase 1: Diagnostic Challenge (Exposing the fatal vulnerability or ambiguity).
   - Phase 2: Constructive Operationalization (Demanding precise type boundaries, counterfactuals, negative controls, or state transitions).
   - Phase 3: Hypothesis Convergence (When the user provides rigorous answers, synthesize their idea into a formal, testable hypothesis).
5. CONCISENESS: Keep your responses sharp, punchy, and under 3-4 paragraphs. Never ramble. Always end with 1 or 2 penetrating diagnostic questions that the user must answer next.
"""

CONVERGENCE_EVAL_PROMPT = """You are the Epistemic Convergence Gatekeeper for Thoth.
You are evaluating a dialogue between a researcher and the philosopher {thinker_name} ({archetype}).

Your goal is to determine if their brainstorming dialectic has progressed from a vague preliminary curiosity into a CONCRETE, TESTABLE RESEARCH HYPOTHESIS that is ready for autonomous deep academic literature research.

Readiness Criteria:
1. Has the core concept been clearly defined or bounded?
2. Has the user articulated a specific mechanism, causal relationship, or testable prediction?
3. Are there identifiable methodological constraints (scope, variables, controls)?
4. Is it ready for scholarly paper discovery across arXiv, Semantic Scholar, PubMed, and OpenAlex?

Dialogue Transcript:
{transcript}

Evaluate readiness now. Output strictly valid JSON:
{{
  "is_ready_for_research": true,
  "readiness_score": 0.90,
  "crystallized_topic": "Concise 6-12 word scholarly topic for literature retrieval",
  "testable_hypothesis": "The exact synthesized hypothesis to be investigated",
  "identified_constraints": ["Constraint 1", "Constraint 2"],
  "falsification_or_test_criteria": "How empirical papers can corroborate or refute this",
  "action_pill_label": "🚀 Launch Deep Research with {thinker_name}",
  "escalation_reason": "Clear explanation of why this idea has achieved academic readiness"
}}
If NOT ready (readiness_score < 0.75), set "is_ready_for_research": false, "action_pill_label": "", and leave other fields concise.
"""

def evaluate_ideation_convergence(
    thinker_id: str,
    chat_turns: List[Dict[str, Any]],
) -> Optional[EscalationProposal]:
    if len(chat_turns) < 2:
        return None

    meta = ARCHETYPE_DEFINITIONS.get(thinker_id, ARCHETYPE_DEFINITIONS["popper"])
    thinker_name = meta["name"]
    archetype = meta["archetype"]

    transcript_lines = []
    for t in chat_turns:
        user_msg = t.get("user") or t.get("user_query") or ""
        asst_msg = t.get("assistant") or t.get("assistant_response") or ""
        if user_msg:
            transcript_lines.append(f"Researcher: {user_msg}")
        if asst_msg:
            transcript_lines.append(f"{thinker_name}: {asst_msg[:400]}")

    transcript_text = "\n".join(transcript_lines[-6:])

    try:
        raw = llm.invoke(
            f"{CONVERGENCE_EVAL_PROMPT.format(thinker_name=thinker_name, archetype=archetype, transcript=transcript_text)}"
        )
        cleaned = strip_chain_of_thought(getattr(raw, "content", str(raw)))
        parsed = safe_extract_json(cleaned, default={})

        score = float(parsed.get("readiness_score", 0.0))
        is_ready = bool(parsed.get("is_ready_for_research", False)) and score >= 0.75

        if is_ready:
            return EscalationProposal(
                is_ready_for_research=True,
                readiness_score=score,
                crystallized_topic=parsed.get("crystallized_topic", "").strip(),
                testable_hypothesis=parsed.get("testable_hypothesis", "").strip(),
                identified_constraints=parsed.get("identified_constraints", []),
                falsification_or_test_criteria=parsed.get("falsification_or_test_criteria", "").strip(),
                action_pill_label=parsed.get("action_pill_label") or f"🚀 Launch Deep Research with {thinker_name}",
                escalation_reason=parsed.get("escalation_reason", "Hypothesis achieved methodological clarity.")
            )
    except Exception as e:
        logger.error(f"[SPARRING CONVERGENCE ERROR] {e}")

    return None

def spar_with_thinker(
    thinker_id: str,
    user_message: str,
    chat_turns: Optional[List[Dict[str, Any]]] = None,
) -> SparringTurnOutput:
    clean_tid = thinker_id.lower().strip()
    if clean_tid not in ARCHETYPE_DEFINITIONS:
        clean_tid = "popper"

    meta = ARCHETYPE_DEFINITIONS[clean_tid]
    docs = _load_thinker_knowledge(clean_tid)

    system_prompt = SPARRING_SYSTEM_PROMPT_TEMPLATE.format(
        thinker_name=meta["name"],
        tradition=meta["tradition"],
        archetype=meta["archetype"],
        modern_adaptation=docs.get("modern_adaptation") or meta["description"],
        operational_algo=docs.get("operational_algo") or "Apply your primary methodological principles to expose errors and refine the hypothesis."
    )

    history_formatted = []
    turns = chat_turns or []
    for turn in turns[-5:]:
        u = turn.get("user") or turn.get("user_query") or ""
        a = turn.get("assistant") or turn.get("assistant_response") or ""
        if u:
            history_formatted.append(f"Researcher: {u}")
        if a:
            history_formatted.append(f"{meta['name']}: {a}")

    dialogue_str = "\n".join(history_formatted) if history_formatted else "This is the opening turn of our dialogue."

    user_prompt = f"""Conversation History:
{dialogue_str}

Researcher's Latest Statement:
"{user_message}"

Respond directly as {meta['name']} now, adhering to your epistemic rules."""

    try:
        raw_res = llm.invoke(f"{system_prompt}\n\nHuman: {user_prompt}")
        reply_text = strip_chain_of_thought(getattr(raw_res, "content", str(raw_res))).strip()
    except Exception as e:
        logger.error(f"[SPARRING INVOCATION ERROR] {e}")
        reply_text = f"As {meta['name']}, I demand that we examine your fundamental premises. What evidence or counter-instance supports this assertion?"

    updated_turns = list(turns)
    updated_turns.append({"user": user_message, "assistant": reply_text})

    escalation_proposal = None
    if len(updated_turns) >= 2:
        escalation_proposal = evaluate_ideation_convergence(clean_tid, updated_turns)

    return SparringTurnOutput(
        thinker_id=clean_tid,
        thinker_name=meta["name"],
        archetype=meta["archetype"],
        reply=reply_text,
        turn_count=len(updated_turns),
        escalation_proposal=escalation_proposal
    )
