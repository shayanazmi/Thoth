"""Judge (docs/features/06 § verdicts and originality; prompt in 09 § Judge).

Weighs the witnesses before a neutral court. Guardrails enforced in code, whatever the model says:
- likely_novel is impossible without an adjacent-field search that ran;
- if most witnesses are abstract-only, already_established is not allowed (it becomes supported_within_limits
  with the reason recorded);
- a gap must name witnesses that exist in this trial, or it is dropped;
- likely_novel is impossible when this run's citation search (papers citing or cited by the strongest
  witnesses) did not run; closest prior work is named by witness (W#) or citation-neighbour (C#) id;
- certainty cannot stay high or moderate when every supporting witness is at high risk of bias (or could not be
  appraised) by its design-specific checklist (backend/research/appraisal.py).
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional

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
6. Originality from the adjacent-field results, the citation neighbours (papers citing or cited by the
   strongest witnesses; read at abstract level only) and the matrix:
   likely_novel | partial_overlap | substantially_covered | insufficiently_assessed
   Name the closest prior work by id (W# or C#) in closest_prior_work_ids.
7. Gaps: only gaps that specific witnesses reveal (cite their ids). These witnesses are a sample of the
   literature, not all of it: phrase every gap as what THESE witnesses do not cover ("None of the N witnesses
   measured…"), never as a gap in the literature. Name missing hypothesis markers (falsifier, comparison,
   scope) that weaken the verdict.

OUTPUT (JSON)
{"per_subclaim": [{"id": int, "certainty": "high"|"moderate"|"low"|"very_low", "rated_down_for": [str],
   "case_for": str, "case_against": str, "conflicts": str, "verdict": str,
   "witness_ids_for": [str], "witness_ids_against": [str]}],
 "overall": {"verdict": str, "reason": str},
 "originality": {"label": str, "reason": str, "closest_prior_work": [str], "closest_prior_work_ids": [str]},
 "gaps": [{"gap": str, "revealed_by": [str]}],
 "hypothesis_weaknesses": [str]}

RULES
- likely_novel is forbidden unless an adjacent-field search ran and found no substantive overlap, and the
  citation neighbours show none either.
- If most witnesses are abstract-only or low weight, certainty is low or very_low; already_established is then forbidden.
- Rate certainty down for risk of bias using each witness's appraisal (overall, critical_concerns). A claim listed
  under beyond_evidence is the authors' over-reach, not evidence for a sub-claim.
- The evidence base says how the witnesses were found. Never describe the search as exhaustive or complete.
- Never invent a gap to keep the project going. "No clear gap" is a valid finding.
- Refer to witnesses only by the ids given (e.g. W3)."""


APPRAISED = ("low", "some_concerns", "high", "not_assessable", "core_only")


def appraisal_summary(a: Dict[str, Any]) -> Dict[str, Any]:
    """What the Judge (and later the Designer and Writer) needs from a structured appraisal."""
    a = a or {}
    if a.get("overall") not in APPRAISED:
        return {"overall": "older method (not appraised)" if not a else "not appraised", "checklist": None}
    return {"checklist": a.get("checklist_name") or "core questions only", "overall": a["overall"],
            "critical_concerns": [i["q"] for i in a.get("items") or [] if i.get("critical") and i.get("answer") in ("no", "unclear", "not_assessable")][:4],
            "beyond_evidence": [c["claim"] for c in (a.get("core") or {}).get("conclusions_beyond_evidence") or []][:3],
            "design_uncertain": bool(a.get("design_uncertain"))}


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
            "appraisal": appraisal_summary(p.get("appraisal") or {}),
            "blind_spots": row.get("blind_spots"), "i_say": p.get("i_say_user") or row.get("i_say_draft"),
        })
    return out


def citation_neighbours(adjacent: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{k: c.get(k) for k in ("id", "title", "year", "relation", "abstract")}
            for c in ((adjacent or {}).get("citation") or {}).get("papers") or []]


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

    appraisals = {f"W{i}": (p.get("appraisal") or {}).get("overall") for i, p in enumerate(papers, 1)}
    per_by_id = {int(p.get("id", 0)): p for p in verdict.get("per_subclaim") or [] if isinstance(p, dict) and str(p.get("id", "")).isdigit()}
    per = []
    for s in subs:
        p = per_by_id.get(s["id"], {})
        item = {**{k: p.get(k) for k in ("certainty", "rated_down_for", "case_for", "case_against", "conflicts")},
                "id": s["id"], "claim": s["claim"], "verdict": guard(p.get("verdict")),
                "witness_ids_for": [w for w in p.get("witness_ids_for") or [] if w in ids],
                "witness_ids_against": [w for w in p.get("witness_ids_against") or [] if w in ids]}
        # Risk of bias, from the design-specific appraisals. Witnesses appraised with the older method (no
        # structured appraisal) don't count either way, so older trials are judged as before.
        apps = [appraisals[w] for w in item["witness_ids_for"] if appraisals.get(w) in APPRAISED]
        if apps and all(a in ("high", "not_assessable") for a in apps) and item.get("certainty") in ("high", "moderate"):
            item["certainty"] = "low"
            item["rated_down_for"] = list(item.get("rated_down_for") or []) + [
                "risk of bias: every supporting witness is at high risk or couldn't be appraised"]
            notes.append(f"Sub-claim {s['id']}: certainty lowered to low because every supporting witness is at high risk of bias "
                         "or couldn't be appraised.")
        per.append(item)
    overall = verdict.get("overall") if isinstance(verdict.get("overall"), dict) else {}
    orig = verdict.get("originality") if isinstance(verdict.get("originality"), dict) else {}
    label = orig.get("label") if orig.get("label") in ORIGINALITY else "insufficiently_assessed"
    if label == "likely_novel" and not adjacent.get("ran"):
        label = "insufficiently_assessed"
        notes.append("No adjacent-field search ran, so originality cannot be 'likely novel'.")
    citation = adjacent.get("citation")
    if citation is None:
        notes.append("Citation search was not part of this (older) run.")
    elif not citation.get("ran") and label == "likely_novel":
        label = "insufficiently_assessed"
        notes.append("The citation search did not run, so originality cannot be 'likely novel'.")
    known = ids | {c.get("id") for c in (citation or {}).get("papers") or []}
    prior_ids = [x for x in orig.get("closest_prior_work_ids") or [] if x in known]
    gaps = [g for g in verdict.get("gaps") or [] if isinstance(g, dict) and set(g.get("revealed_by") or []) & ids]
    dropped = len(verdict.get("gaps") or []) - len(gaps)
    if dropped > 0:
        notes.append(f"{dropped} gap(s) dropped because they did not name a witness from this trial.")
    return {
        "per_subclaim": per,
        "overall": {"verdict": guard(overall.get("verdict")), "reason": str(overall.get("reason") or "")},
        "originality": {"label": label, "reason": str(orig.get("reason") or ""), "closest_prior_work": orig.get("closest_prior_work") or [],
                        "closest_prior_work_ids": prior_ids},
        "gaps": gaps,
        "hypothesis_weaknesses": [str(x) for x in verdict.get("hypothesis_weaknesses") or []][:5],
        "witnesses": len(papers), "full_text_witnesses": len(papers) - weak_access,
        "appraisal_summary": dict(Counter(a or "older method" for a in appraisals.values())),
        "guardrail_notes": list(dict.fromkeys(notes)),
        "judged_by": str(verdict.get("_served_by") or ""),
    }


async def judge(hypothesis: str, subs: List[Dict[str, Any]], papers: List[Dict[str, Any]], adjacent: Dict[str, Any],
                coverage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    adj = {k: v for k, v in (adjacent or {}).items() if k != "citation"}
    human = (f"<hypothesis>{hypothesis}</hypothesis>\n<subclaims>{json.dumps(subs)}</subclaims>\n"
             f"<matrix>\n{json.dumps(_witness_summary(papers))}\n</matrix>\n"
             f"<adjacent_search>{json.dumps(adj)}</adjacent_search>\n"
             f"<citation_neighbours>{json.dumps(citation_neighbours(adjacent))}</citation_neighbours>")
    if coverage:
        human += f"\n<evidence_base>{json.dumps(coverage)}</evidence_base>"
    raw = await call_json("judge", PROMPT, human, default={}) or {}
    return enforce(raw if isinstance(raw, dict) else {}, papers, adjacent or {}, subs)
