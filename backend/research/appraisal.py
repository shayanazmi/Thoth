"""Appraiser (vision §5.6, §6.1 methodological critic).

A hypothesis-blind critical appraisal of ONE paper against a checklist chosen IN CODE from the Reader's design
classification. Different designs get different instruments (Cochrane RoB 2 domains for trials; JBI checklists
for quasi-experimental, cohort, case-control, cross-sectional, qualitative and systematic reviews; MMAT for mixed
methods; SANRA for narrative reviews); anything else gets the core questions only, and says so. Item wording is a
paraphrase: the UI says "adapted from", never "scored with".

Code, not the model, decides what an answer may claim: an answer without a locator is "unclear"; an item that
needs the full text is "not_assessable" when only the abstract was read; the overall judgement and the weight
factor are computed here from the item answers, so they are explained by them.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.agents import sanitize_log_message
from backend.research.llm import call_json

logger = logging.getLogger("ThothAppraiser")

ANSWERS = ("yes", "no", "unclear", "not_applicable")


def _items(spec: List[Tuple[str, str, bool]], abstract_visible: Tuple[str, ...] = ()) -> List[Dict[str, Any]]:
    return [{"id": i, "q": q, "critical": c, "needs_full_text": i not in abstract_visible} for i, q, c in spec]


CHECKLISTS: Dict[str, Dict[str, Any]] = {
    "rob2": {"name": "Risk of bias in randomised trials", "adapted_from": "Cochrane RoB 2 (domains)", "designs": {"rct"},
             "items": _items([
                 ("d1", "Was the allocation sequence random and concealed, with baseline groups balanced?", True),
                 ("d2", "Were deviations from the intended interventions avoided or handled (blinding, intention-to-treat)?", True),
                 ("d3", "Were outcome data complete, or was missing data handled appropriately?", True),
                 ("d4", "Was the outcome measured appropriately, with assessors blinded where it matters?", True),
                 ("d5", "Was the reported result chosen according to a pre-specified analysis plan?", True)])},
    "jbi_quasi": {"name": "Quasi-experimental studies", "adapted_from": "JBI checklist for quasi-experimental studies",
                  "designs": {"quasi_experimental"},
                  "items": _items([
                      ("q1", "Is it clear which variable is the cause and which the effect?", False),
                      ("q2", "Were participants in the comparisons similar?", False),
                      ("q3", "Did the groups receive similar treatment apart from the intervention?", False),
                      ("q4", "Was there a control group?", True),
                      ("q5", "Were there multiple measurements before and after the intervention?", False),
                      ("q6", "Was follow-up complete, or were losses described and analysed?", True),
                      ("q7", "Were outcomes measured the same way in every group?", True),
                      ("q8", "Were outcomes measured reliably?", False),
                      ("q9", "Was the statistical analysis appropriate?", False)], ("q4",))},
    "jbi_cohort": {"name": "Cohort studies", "adapted_from": "JBI checklist for cohort studies",
                   "designs": {"cohort_prospective", "cohort_retrospective"},
                   "items": _items([
                       ("k1", "Were the groups similar and recruited from the same population?", False),
                       ("k2", "Were exposures measured the same way to assign people to groups?", False),
                       ("k3", "Was the exposure measured validly and reliably?", True),
                       ("k4", "Were confounding factors identified?", True),
                       ("k5", "Were strategies used to deal with confounding?", True),
                       ("k6", "Were participants free of the outcome at the start?", False),
                       ("k7", "Were outcomes measured validly and reliably?", True),
                       ("k8", "Was follow-up long enough for outcomes to occur?", False),
                       ("k9", "Was follow-up complete, or were losses described and explored?", True),
                       ("k10", "Were strategies used to address incomplete follow-up?", False),
                       ("k11", "Was the statistical analysis appropriate?", False)])},
    "jbi_case_control": {"name": "Case-control studies", "adapted_from": "JBI checklist for case-control studies",
                         "designs": {"case_control"},
                         "items": _items([
                             ("c1", "Were the groups comparable apart from the condition?", False),
                             ("c2", "Were cases and controls matched appropriately?", False),
                             ("c3", "Were the same criteria used to identify cases and controls?", False),
                             ("c4", "Was the exposure measured in a standard, valid and reliable way?", True),
                             ("c5", "Was the exposure measured the same way for cases and controls?", False),
                             ("c6", "Were confounding factors identified?", True),
                             ("c7", "Were strategies used to deal with confounding?", True),
                             ("c8", "Were outcomes assessed validly and reliably?", False),
                             ("c9", "Was the exposure period long enough to be meaningful?", False),
                             ("c10", "Was the statistical analysis appropriate?", False)])},
    "jbi_cross_sectional": {"name": "Analytical cross-sectional studies", "adapted_from": "JBI checklist for analytical cross-sectional studies",
                            "designs": {"cross_sectional"},
                            "items": _items([
                                ("x1", "Were the inclusion criteria clearly defined?", False),
                                ("x2", "Were the participants and the setting described in detail?", False),
                                ("x3", "Was the exposure measured validly and reliably?", True),
                                ("x4", "Were objective, standard criteria used to measure the condition?", False),
                                ("x5", "Were confounding factors identified?", True),
                                ("x6", "Were strategies used to deal with confounding?", True),
                                ("x7", "Were outcomes measured validly and reliably?", True),
                                ("x8", "Was the statistical analysis appropriate?", False)])},
    "jbi_qualitative": {"name": "Qualitative research", "adapted_from": "JBI checklist for qualitative research",
                        "designs": {"qualitative"},
                        "items": _items([
                            ("l1", "Is the philosophical perspective congruent with the methodology?", False),
                            ("l2", "Is the methodology congruent with the research question?", True),
                            ("l3", "Is the methodology congruent with how data were collected?", True),
                            ("l4", "Is the methodology congruent with how data were analysed?", False),
                            ("l5", "Is the methodology congruent with how results were interpreted?", False),
                            ("l6", "Is the researcher located culturally or theoretically?", False),
                            ("l7", "Is the researcher's influence on the research addressed?", False),
                            ("l8", "Are participants and their voices adequately represented?", True),
                            ("l9", "Is ethical approval reported?", False),
                            ("l10", "Do the conclusions flow from the analysis and interpretation?", True)])},
    "jbi_sr": {"name": "Systematic reviews", "adapted_from": "JBI checklist for systematic reviews",
               "designs": {"systematic_review", "meta_analysis"},
               "items": _items([
                   ("s1", "Is the review question clearly stated?", False),
                   ("s2", "Were the inclusion criteria appropriate for the question?", False),
                   ("s3", "Was the search strategy appropriate?", True),
                   ("s4", "Were the sources and resources searched adequate?", True),
                   ("s5", "Were the criteria for appraising studies appropriate?", True),
                   ("s6", "Was appraisal done by two or more reviewers independently?", False),
                   ("s7", "Were there methods to minimise errors in data extraction?", False),
                   ("s8", "Were the methods used to combine studies appropriate?", False),
                   ("s9", "Was the likelihood of publication bias assessed?", False),
                   ("s10", "Are the recommendations supported by the reported data?", False),
                   ("s11", "Are the directions for new research appropriate?", False)], ("s1",))},
    "mmat_mixed": {"name": "Mixed-methods studies", "adapted_from": "MMAT (mixed-methods category)", "designs": {"mixed_methods"},
                   "items": _items([
                       ("m1", "Is there an adequate rationale for using mixed methods?", True),
                       ("m2", "Are the components effectively integrated?", False),
                       ("m3", "Are the outputs of the integration adequately interpreted?", False),
                       ("m4", "Are divergences between the components addressed?", False),
                       ("m5", "Does each component meet the quality criteria of its own tradition?", True)])},
    "sanra": {"name": "Narrative reviews", "adapted_from": "SANRA", "designs": {"narrative_review"},
              "items": _items([
                  ("n1", "Is the importance of the review justified?", False),
                  ("n2", "Are the aims or questions stated?", False),
                  ("n3", "Is the literature search described?", True),
                  ("n4", "Is the referencing adequate?", False),
                  ("n5", "Is the reasoning backed by appropriate evidence?", True),
                  ("n6", "Are the data presented appropriately?", False)], ("n1", "n2"))},
}

_BY_DESIGN = {d: cid for cid, c in CHECKLISTS.items() for d in c["designs"]}

FACTOR = {"low": 1.0, "some_concerns": 0.85, "high": 0.6, "not_assessable": 0.8, "core_only": 0.9}
NO_CHECKLIST = "No recognised checklist is applied to this design; only the core questions were used."

PROMPT = """ROLE
You are Thoth's Appraiser. You judge the methodological quality of ONE paper against the checklist given. You are
not told any hypothesis, on purpose: judge the study, not whether it helps anyone's argument.

METHOD
1. Check what text you have (access level below). If you only have the abstract, most items cannot be judged.
2. Answer every checklist item with "yes", "no", "unclear" or "not_applicable".
   - "unclear" when the paper does not report it. Never infer methods the text does not show.
   - Give a short quote (at most 25 words) as evidence and a locator a reader could find (section, table,
     page or paragraph). An answer you cannot locate is "unclear".
3. Answer the core questions: do the methods fit the question; does the analysis support the findings; which
   biases matter most; which conclusions go beyond the evidence. A study's stated limitation is not the same as
   a conclusion that goes beyond its data; list only the second under conclusions_beyond_evidence.

OUTPUT (JSON)
{"items": [{"id": str, "answer": "yes"|"no"|"unclear"|"not_applicable", "evidence": str, "locator": str}],
 "core": {"methods_fit": {"answer": "yes"|"no"|"unclear", "why": str, "locator": str},
          "analysis_supports_findings": {"answer": "yes"|"no"|"unclear", "why": str, "locator": str},
          "key_biases": [{"bias": str, "why": str, "locator": str}],
          "conclusions_beyond_evidence": [{"claim": str, "why": str, "locator": str}]}}"""


def checklist_for(design_value: Optional[str], design_provenance: str = "") -> Tuple[Optional[str], bool]:
    """(checklist id or None, design_uncertain). The design comes from the Reader; when it is unreported or
    unrecognised the paper still gets the core questions, and the uncertainty is flagged."""
    value = str(design_value or "").strip().lower()
    uncertain = design_provenance in ("not_reported", "not_accessible") or not value or value.startswith("other:")
    return _BY_DESIGN.get(value), uncertain


def prompt_items(checklist_id: Optional[str]) -> List[Dict[str, str]]:
    return [{"id": i["id"], "q": i["q"]} for i in (CHECKLISTS.get(checklist_id or "") or {}).get("items", [])]


def overall(items: List[Dict[str, Any]], checklist_id: Optional[str]) -> Tuple[str, str]:
    if not checklist_id:
        return "core_only", NO_CHECKLIST
    spec = {i["id"]: i for i in CHECKLISTS[checklist_id]["items"]}
    na = [i for i in items if i["answer"] == "not_assessable"]
    if len(na) / max(1, len(items)) >= 0.5:
        return "not_assessable", "Most items need text that wasn't accessible."
    crit_no = [i for i in items if spec[i["id"]]["critical"] and i["answer"] == "no"]
    if crit_no:
        return "high", "Critical item(s) failed: " + "; ".join(spec[i["id"]]["q"] for i in crit_no)
    crit_open = [i for i in items if spec[i["id"]]["critical"] and i["answer"] in ("unclear", "not_assessable")]
    other_no = [i for i in items if not spec[i["id"]]["critical"] and i["answer"] == "no"]
    if crit_open or len(other_no) >= 2:
        parts = []
        if crit_open:
            parts.append("critical item(s) unclear: " + "; ".join(spec[i["id"]]["q"] for i in crit_open))
        if len(other_no) >= 2:
            parts.append(f"{len(other_no)} other items failed")
        return "some_concerns", "; ".join(parts).capitalize()
    return "low", "Every critical item is met."


def factor(appraisal: Optional[Dict[str, Any]]) -> float:
    """Weight factor. A paper with no appraisal (an older run, or the Appraiser unavailable) keeps factor 1.0."""
    return FACTOR.get((appraisal or {}).get("overall") or "", 1.0)


def _core_item(v: Any) -> Dict[str, Any]:
    v = v if isinstance(v, dict) else {}
    ans = v.get("answer") if v.get("answer") in ("yes", "no", "unclear") else "unclear"
    loc = str(v.get("locator") or "").strip()
    return {"answer": ans if (loc or ans == "unclear") else "unclear", "why": str(v.get("why") or "")[:400], "locator": loc[:120]}


def _core_list(v: Any, key: str, cap: int) -> List[Dict[str, Any]]:
    out = []
    for x in (v if isinstance(v, list) else [])[:cap]:
        if isinstance(x, dict) and str(x.get(key) or "").strip():
            loc = str(x.get("locator") or "").strip()
            out.append({key: str(x[key])[:300], "why": str(x.get("why") or "")[:400], "locator": loc[:120], "unlocated": not loc})
    return out


def enforce(raw: Dict[str, Any], checklist_id: Optional[str], access: str, design_used: Optional[str],
            design_uncertain: bool, appraised_by: str = "") -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    spec = (CHECKLISTS.get(checklist_id or "") or {}).get("items", [])
    given = {str(x.get("id")): x for x in raw.get("items") or [] if isinstance(x, dict)}
    prov = "from_full_text" if access == "full_text" else "from_abstract"
    items = []
    for s in spec:
        g = given.get(s["id"])
        item = {"id": s["id"], "q": s["q"], "critical": s["critical"], "evidence": "", "locator": "", "provenance": prov}
        if access != "full_text" and s["needs_full_text"]:
            item.update(answer="not_assessable", why="full text not accessible")
        elif not g:
            item.update(answer="not_assessable", why="not answered")
        else:
            ans = g.get("answer") if g.get("answer") in ANSWERS else "unclear"
            loc = str(g.get("locator") or "").strip()[:120]
            item.update(answer=ans, evidence=str(g.get("evidence") or "")[:300], locator=loc)
            if ans in ("yes", "no") and not loc:
                item.update(answer="unclear", note="no locator")
        items.append(item)
    core_raw = raw.get("core") if isinstance(raw.get("core"), dict) else {}
    core = {"methods_fit": _core_item(core_raw.get("methods_fit")),
            "analysis_supports_findings": _core_item(core_raw.get("analysis_supports_findings")),
            "key_biases": _core_list(core_raw.get("key_biases"), "bias", 5),
            "conclusions_beyond_evidence": _core_list(core_raw.get("conclusions_beyond_evidence"), "claim", 4)}
    label, why = overall(items, checklist_id)
    counts = {a: sum(1 for i in items if i["answer"] == a) for a in (*ANSWERS, "not_assessable")}
    c = CHECKLISTS.get(checklist_id or "") or {}
    return {"checklist_id": checklist_id, "checklist_name": c.get("name"), "adapted_from": c.get("adapted_from"), "version": 1,
            "design_used": design_used, "design_uncertain": design_uncertain,
            "selection_note": "" if checklist_id else NO_CHECKLIST,
            "items": items, "core": core, "counts": counts, "overall": label, "overall_why": why,
            "appraised_by": appraised_by, "access": access}


async def appraise(meta: Dict[str, Any], text: str, access: str, design_field: Dict[str, Any],
                   primary_only: bool = False) -> Dict[str, Any]:
    """One Appraiser call. Never raises: if the model is unavailable the paper is marked "not appraised" and
    keeps its weight (factor 1.0), rather than failing the paper."""
    from backend.research.reader import focus
    design_field = design_field if isinstance(design_field, dict) else {}
    cid, uncertain = checklist_for(design_field.get("value"), str(design_field.get("provenance") or ""))
    human = (f"<access_level>{access}</access_level>\n"
             f"<design>{json.dumps({'value': design_field.get('value'), 'provenance': design_field.get('provenance')})}</design>\n"
             f"<checklist>{json.dumps(prompt_items(cid))}</checklist>\n"
             f"<metadata>{json.dumps({k: meta.get(k) for k in ('title', 'year', 'venue')})}</metadata>\n"
             f"<untrusted>{focus(text or '', 16000)}</untrusted>")
    try:
        raw = await call_json("appraiser:primary" if primary_only else "appraiser", PROMPT, human, default={}) or {}
    except Exception as exc:
        logger.warning("[appraiser] unavailable: %s", sanitize_log_message(str(exc)))
        return not_appraised(cid, design_field.get("value"), uncertain, access, "appraiser unavailable")
    if not isinstance(raw, dict) or not (raw.get("items") or raw.get("core")):
        # An empty answer is no appraisal, not a paper whose every item failed.
        return not_appraised(cid, design_field.get("value"), uncertain, access, "the appraiser returned nothing usable")
    return enforce(raw, cid, access, design_field.get("value"), uncertain, appraised_by=str(raw.get("_served_by") or ""))


def not_appraised(checklist_id: Optional[str], design_used: Optional[str], uncertain: bool, access: str, why: str) -> Dict[str, Any]:
    c = CHECKLISTS.get(checklist_id or "") or {}
    return {"checklist_id": checklist_id, "checklist_name": c.get("name"), "adapted_from": c.get("adapted_from"),
            "overall": "not_appraised", "overall_why": why, "error": why, "items": [], "core": {}, "counts": {},
            "design_used": design_used, "design_uncertain": uncertain, "access": access}
