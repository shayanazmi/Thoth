"""Analyst (docs/features/04 sub-claims, 06 synthesis matrix; prompts in 09 § Analyst).

Job A splits the hypothesis into sub-claims. Job B reads one neutral paper record against them and fills
its matrix row. Guardrails enforced in code: a direction needs a locator; "pivoting" needs a located result
in this paper; abstract-only rows are flagged. Witness weight is computed, not asked of the model.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from backend.research.llm import call_json

SUBCLAIMS_PROMPT = """ROLE
Split the hypothesis into the claims it is made of, so each can be tested against papers.

METHOD
1. Identify the constructs (things that vary) and the relationships between them.
2. Write 2-5 sub-claims. Each states ONE relationship, names its constructs, and could be supported or
   contradicted by a single study.
3. Order them as the story runs (cause → mechanism → outcome → comparison).

OUTPUT (JSON)
{"subclaims": [{"id": 1, "claim": str, "constructs": [str], "relation": "causes"|"associated_with"|"greater_than"|"mediates"|"moderates"}],
 "ambiguities": [str]}

RULES
- Do not add claims the person did not make. If a link is ambiguous, put it in "ambiguities" instead."""

ROW_PROMPT = """ROLE
You are Thoth's Analyst. The hypothesis is on trial. This paper is one witness. Record what it says about each
sub-claim, neutrally: a divergent witness is as valuable as a convergent one.

METHOD
1. Construct match: for each construct in the hypothesis, compare how this paper measured it.
   same = the same concept and an accepted measure of it; proxy = related but not the same; different = a
   different concept under the same word.
2. Direction per sub-claim, using only results with locators: convergent = goes the way the sub-claim
   predicts; divergent = goes the other way; null = tested, no meaningful relationship; not_addressed = not tested.
3. Boundary conditions: where (population, setting, measure, time) the effect held or failed.
4. Appraise with the CASP checklist for this design. List strengths and risks of bias.
5. Blind spots: what the authors left open that the hypothesis could target, and premises assumed untested.
6. Floor or ceiling: ground the hypothesis stands on (floor), or a limit it pushes past (ceiling)?
7. Draft the "I say" in 1-2 sentences and pick a stance: advancement (builds past this paper),
   reconciliation (explains a conflict between witnesses), pivoting (turns on a specific anomaly in this
   paper's own results).

OUTPUT (JSON)
{"construct_match": [{"construct": str, "match": "same"|"proxy"|"different", "why": str}],
 "per_subclaim": [{"id": int, "direction": "convergent"|"divergent"|"null"|"not_addressed", "locator": str, "note": str}],
 "boundary_conditions": [str],
 "appraisal": {"design": str, "checklist": str, "strengths": [str], "risks_of_bias": [str]},
 "blind_spots": [str], "untested_premises": [str],
 "floor_or_ceiling": "floor"|"ceiling"|"neither", "floor_or_ceiling_why": str,
 "i_say_draft": str, "stance": "advancement"|"reconciliation"|"pivoting"}

RULES
- A direction needs a locator from the record. No locator → not_addressed.
- "pivoting" must name the specific result in this record that justifies it. If you cannot, choose another stance.
- A proxy measure weakens convergence; say so in the note.
- Fields marked from_abstract or not_reported limit what you can say; note it."""

DIRECTIONS = {"convergent", "divergent", "null", "not_addressed"}

DESIGN_TIER = {"meta_analysis": 1.0, "systematic_review": 0.95, "rct": 0.9, "quasi_experimental": 0.7,
               "cohort_prospective": 0.7, "cohort_retrospective": 0.6, "case_control": 0.55, "cross_sectional": 0.45,
               "mixed_methods": 0.45, "qualitative": 0.4, "modelling": 0.35, "narrative_review": 0.3}
ACCESS_FACTOR = {"full_text": 1.0, "partial": 0.85, "abstract_only": 0.55, "metadata_only": 0.2}


def weight(record: Dict[str, Any]) -> float:
    """Witness weight = design tier × access factor (docs/features/06). Unknown design counts as weak."""
    design = str((record.get("design") or {}).get("value") or "")
    return round(DESIGN_TIER.get(design, 0.3) * ACCESS_FACTOR.get(record.get("access", ""), 0.2), 2)


async def subclaims(hypothesis: str) -> Dict[str, Any]:
    data = await call_json("analyst", SUBCLAIMS_PROMPT, f"<hypothesis>{hypothesis}</hypothesis>", default={}) or {}
    items = [s for s in (data.get("subclaims") or []) if isinstance(s, dict) and s.get("claim")][:5]
    for i, s in enumerate(items, 1):
        s["id"] = i
    return {"subclaims": items, "ambiguities": [str(a) for a in data.get("ambiguities") or []][:4]}


def enforce_row(row: Dict[str, Any], subs: List[Dict[str, Any]], record: Dict[str, Any]) -> Dict[str, Any]:
    by_id = {int(p.get("id", 0)): p for p in row.get("per_subclaim") or [] if isinstance(p, dict) and str(p.get("id", "")).isdigit()}
    per = []
    for s in subs:
        p = by_id.get(s["id"], {})
        direction = p.get("direction") if p.get("direction") in DIRECTIONS else "not_addressed"
        locator = str(p.get("locator") or "").strip()
        if direction != "not_addressed" and not locator:
            direction = "not_addressed"
        per.append({"id": s["id"], "direction": direction, "locator": locator, "note": str(p.get("note") or "")})
    located = any(p["direction"] != "not_addressed" for p in per)
    stance = row.get("stance") if row.get("stance") in ("advancement", "reconciliation", "pivoting") else "advancement"
    if stance == "pivoting" and not located:
        stance = "advancement"
    abstract_only = record.get("access") != "full_text"
    return {
        "construct_match": [c for c in row.get("construct_match") or [] if isinstance(c, dict)][:6],
        "per_subclaim": per,
        "boundary_conditions": [str(x) for x in row.get("boundary_conditions") or []][:5],
        "appraisal": row.get("appraisal") if isinstance(row.get("appraisal"), dict) else {},
        "blind_spots": [str(x) for x in row.get("blind_spots") or []][:4],
        "untested_premises": [str(x) for x in row.get("untested_premises") or []][:3],
        "floor_or_ceiling": row.get("floor_or_ceiling") if row.get("floor_or_ceiling") in ("floor", "ceiling", "neither") else "neither",
        "floor_or_ceiling_why": str(row.get("floor_or_ceiling_why") or ""),
        "i_say_draft": str(row.get("i_say_draft") or ""),
        "stance": stance,
        "uses_abstract_only_fields": abstract_only,
        "analysed_by": str(row.get("_served_by") or ""),
    }


async def row(hypothesis: str, subs: List[Dict[str, Any]], record: Dict[str, Any]) -> Dict[str, Any]:
    human = (f"<hypothesis>{hypothesis}</hypothesis>\n<subclaims>{json.dumps(subs)}</subclaims>\n"
             f"<untrusted>\n{json.dumps(record)}\n</untrusted>")
    raw = await call_json("analyst", ROW_PROMPT, human, default={}) or {}
    return enforce_row(raw if isinstance(raw, dict) else {}, subs, record)
