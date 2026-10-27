"""Judge (docs/features/06 § verdicts and originality; prompt in 09 § Judge).

Weighs the witnesses before a neutral court. Guardrails enforced in code, whatever the model says:
- likely_novel is impossible without an adjacent-field search that ran;
- if most witnesses are abstract-only, already_established is not allowed (it becomes supported_within_limits
  with the reason recorded);
- a gap must name witnesses that exist in this trial, or it is dropped.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from backend.research.llm import call_json

VERDICTS = ("already_established", "supported_within_limits", "contested", "contradicted", "insufficient_evidence")
ORIGINALITY = ("likely_novel", "partial_overlap", "substantially_covered", "insufficiently_assessed")

PROMPT = """ROLE
You are Thoth's Judge. The hypothesis is on trial before a neutral court. You weigh the witnesses and give a
verdict. A verdict against the hypothesis is as acceptable as one for it.

METHOD (in this order)
1. Certainty per sub-claim, GRADE-style: start from the strongest design present; rate down for risk of bias,
   inconsistency between witnesses, indirectness (proxy measures, other populations), imprecision (few or
   small studies), and abstract-only evidence. State each rating-down in a few words.
2. Strongest case FOR: the best convergent, highest-weight witnesses, and what they show.
3. Strongest case AGAINST: the best divergent or null witnesses, and what they show. Equal effort to step 2.
   If there are none, say so plainly and say whether that absence is itself informative.
4. Conflicts: explain splits by methodological asymmetry (design, sample, measure, setting) only if the
   records support it. Otherwise say "unexplained".
5. Verdict per sub-claim, then overall: already_established | supported_within_limits | contested |
   contradicted | insufficient_evidence
6. Originality from the adjacent-field results and the matrix:
   likely_novel | partial_overlap | substantially_covered | insufficiently_assessed
7. Gaps: only gaps that specific witnesses reveal (cite their ids). These witnesses are a sample of the
   literature, not all of it: phrase every gap as what THESE witnesses do not cover ("None of the N witnesses
   measured…"), never as a gap in the literature. Name missing hypothesis markers (falsifier, comparison,
   scope) that weaken the verdict.

OUTPUT (JSON)
{"per_subclaim": [{"id": int, "certainty": "high"|"moderate"|"low"|"very_low", "rated_down_for": [str],
   "case_for": str, "case_against": str, "conflicts": str, "verdict": str,
   "witness_ids_for": [str], "witness_ids_against": [str]}],
 "overall": {"verdict": str, "reason": str},
 "originality": {"label": str, "reason": str, "closest_prior_work": [str]},
 "gaps": [{"gap": str, "revealed_by": [str]}],
 "hypothesis_weaknesses": [str]}

RULES
- likely_novel is forbidden unless an adjacent-field search ran and found no substantive overlap.
- If most witnesses are abstract-only or low weight, certainty is low or very_low; already_established is then forbidden.
- Never invent a gap to keep the project going. "No clear gap" is a valid finding.
- Refer to witnesses only by the ids given (e.g. W3)."""


def _witness_summary(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, p in enumerate(papers, 1):
        rec, row = p.get("record") or {}, p.get("row") or {}
        out.append({
            "id": f"W{i}", "title": p["meta"].get("title"), "year": p["meta"].get("year"),
            "design": (rec.get("design") or {}).get("value"), "sample_size": (rec.get("sample_size") or {}).get("value"),
            "access": p.get("access"), "weight": p.get("weight"),
            "construct_match": row.get("construct_match"), "per_subclaim": row.get("per_subclaim"),
            "boundary_conditions": row.get("boundary_conditions"), "risks_of_bias": (row.get("appraisal") or {}).get("risks_of_bias"),
            "blind_spots": row.get("blind_spots"), "i_say": p.get("i_say_user") or row.get("i_say_draft"),
        })
    return out


def enforce(verdict: Dict[str, Any], papers: List[Dict[str, Any]], adjacent: Dict[str, Any], subs: List[Dict[str, Any]]) -> Dict[str, Any]:
    ids = {f"W{i}" for i in range(1, len(papers) + 1)}
    weak_access = sum(1 for p in papers if p.get("access") != "full_text")
    mostly_abstract = bool(papers) and weak_access > len(papers) / 2
    notes: List[str] = []

    def guard(v: Any) -> str:
        v = v if v in VERDICTS else "insufficient_evidence"
        if v == "already_established" and mostly_abstract:
            notes.append("Most witnesses were read from abstracts only, so 'already established' was lowered to 'supported within limits'.")
            return "supported_within_limits"
        return v

    per_by_id = {int(p.get("id", 0)): p for p in verdict.get("per_subclaim") or [] if isinstance(p, dict) and str(p.get("id", "")).isdigit()}
    per = []
    for s in subs:
        p = per_by_id.get(s["id"], {})
        per.append({**{k: p.get(k) for k in ("certainty", "rated_down_for", "case_for", "case_against", "conflicts")},
                    "id": s["id"], "claim": s["claim"], "verdict": guard(p.get("verdict")),
                    "witness_ids_for": [w for w in p.get("witness_ids_for") or [] if w in ids],
                    "witness_ids_against": [w for w in p.get("witness_ids_against") or [] if w in ids]})
    overall = verdict.get("overall") if isinstance(verdict.get("overall"), dict) else {}
    orig = verdict.get("originality") if isinstance(verdict.get("originality"), dict) else {}
    label = orig.get("label") if orig.get("label") in ORIGINALITY else "insufficiently_assessed"
    if label == "likely_novel" and not adjacent.get("ran"):
        label = "insufficiently_assessed"
        notes.append("No adjacent-field search ran, so originality cannot be 'likely novel'.")
    gaps = [g for g in verdict.get("gaps") or [] if isinstance(g, dict) and set(g.get("revealed_by") or []) & ids]
    dropped = len(verdict.get("gaps") or []) - len(gaps)
    if dropped > 0:
        notes.append(f"{dropped} gap(s) dropped because they did not name a witness from this trial.")
    return {
        "per_subclaim": per,
        "overall": {"verdict": guard(overall.get("verdict")), "reason": str(overall.get("reason") or "")},
        "originality": {"label": label, "reason": str(orig.get("reason") or ""), "closest_prior_work": orig.get("closest_prior_work") or []},
        "gaps": gaps,
        "hypothesis_weaknesses": [str(x) for x in verdict.get("hypothesis_weaknesses") or []][:5],
        "witnesses": len(papers), "full_text_witnesses": len(papers) - weak_access,
        "guardrail_notes": list(dict.fromkeys(notes)),
        "judged_by": str(verdict.get("_served_by") or ""),
    }


async def judge(hypothesis: str, subs: List[Dict[str, Any]], papers: List[Dict[str, Any]], adjacent: Dict[str, Any]) -> Dict[str, Any]:
    human = (f"<hypothesis>{hypothesis}</hypothesis>\n<subclaims>{json.dumps(subs)}</subclaims>\n"
             f"<matrix>\n{json.dumps(_witness_summary(papers))}\n</matrix>\n"
             f"<adjacent_search>{json.dumps(adjacent)}</adjacent_search>")
    raw = await call_json("judge", PROMPT, human, default={}) or {}
    return enforce(raw if isinstance(raw, dict) else {}, papers, adjacent, subs)
