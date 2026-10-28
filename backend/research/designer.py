"""Designer (docs/features/07-study-design.md; prompt in 09 § Designer).

Proposes 2-3 study designs for the hypothesis from the trial's methodological lessons and checks each against
the researcher's resources. Guardrails enforced in code, whatever the model returns:
- a measure must cite a trial witness that exists, or it is marked "new: needs validation";
- a design that cannot support causal conclusions may not claim them;
- a sample size with numbers must state its assumptions or call for a power analysis;
- an appeal to unnamed studies ("simulation studies suggest…") or an effect size with neither a witness id nor
  "assumed" is flagged as unsourced (seen 25 Oct: "approx. 80-100 completers suggested by simulation studies");
- feasibility is one of three labels, and a recommended design must be one of the candidates.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.research import store
from backend.research.llm import call_json

DESIGN_TYPES = ("rct", "quasi_experimental", "cohort_prospective", "cohort_retrospective", "case_control",
                "cross_sectional", "qualitative", "mixed_methods", "n_of_1", "other")
CAUSAL_CAPABLE = {"rct", "quasi_experimental", "cohort_prospective", "n_of_1"}
FEASIBILITY = ("feasible", "feasible_with_changes", "not_feasible")
VALIDITY = ("statistical", "internal", "construct", "external")
_CAUSAL_CLAIM = re.compile(r"\b(caus\w*|effect of|leads? to|results? in|because)\b", re.I)

RESOURCE_FIELDS = ("time", "population_access", "budget", "skills", "ethics_route", "tools")

PROMPT = """ROLE
You are Thoth's Designer. Propose 2-3 study designs that could test this hypothesis within the person's
resources.

METHOD
1. Read the trial lessons: which designs produced high-weight witnesses, which measures were used or contested,
   which boundary conditions and blind spots are worth targeting, and which sub-claims remain unsupported.
2. Match design to claim: causal claims need manipulation, longitudinal ordering or a credible quasi-experiment.
3. For each candidate design:
   - design_type: one of rct, quasi_experimental, cohort_prospective, cohort_retrospective, case_control,
     cross_sectional, qualitative, mixed_methods, n_of_1, other;
   - what it can conclude and what it cannot (causal? associational? descriptive?);
   - which sub-claims it tests (by id);
   - measures: for each construct, an instrument borrowed from a trial witness (give its id, e.g. W3) or
     "new" if none of the witnesses used a suitable one;
   - sampling and sample size: state assumptions, or write "needs power analysis with <inputs>";
   - threats under each validity type (statistical, internal, construct, external) and how each is handled;
   - feasibility against the resources: feasible | feasible_with_changes | not_feasible, with specific blockers
     and the changes that would make it feasible.
4. Recommend one, saying why, and say what the others would add.

OUTPUT (JSON)
{"designs": [{"name": str, "design_type": str, "summary": str, "can_conclude": str, "cannot_conclude": str,
   "tests_subclaims": [int],
   "measures": [{"construct": str, "instrument": str, "source_witness_id": "W3" | "new", "note": str}],
   "sampling": str, "sample_size": str,
   "threats": [{"validity": "statistical"|"internal"|"construct"|"external", "threat": str, "mitigation": str}],
   "feasibility": str, "blockers": [str], "changes_to_make_feasible": [str]}],
 "recommended": str, "why": str, "what_others_add": str}

RULES
- Never invent effect sizes, reliability coefficients or instrument properties.
- Never describe a cross-sectional or other non-causal design as able to show causation.
- Use only witness ids that appear in the trial lessons."""


def latest_trial(thread_id: str) -> Optional[Dict[str, Any]]:
    from backend.memory import db as _db
    _db.init_db(_db.DEFAULT_DB_PATH)
    row = _db.get_connection(_db.DEFAULT_DB_PATH).execute(
        "SELECT trial_id FROM trials WHERE thread_id = ? AND status = 'complete' ORDER BY created_at DESC LIMIT 1", (thread_id,)
    ).fetchone()
    return store.get_trial(row[0]) if row else None


def trial_for_design(thread_id: str, design: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The trial a design's witness ids (W3…) refer to. Ids only mean something relative to one trial, and a later
    trial renumbers them (seen live: a revision rejected W9 against the project's newest, 1-paper trial).
    Designs record it; for older designs it is inferred from the titles their measures cite."""
    if design and design.get("trial_id"):
        t = store.get_trial(design["trial_id"])
        if t:
            return t
    titles = {m.get("source_title") for m in (design or {}).get("measures") or [] if m.get("source_title")}
    if titles:
        from backend.memory import db as _db
        rows = _db.get_connection(_db.DEFAULT_DB_PATH).execute(
            "SELECT trial_id FROM trials WHERE thread_id = ? AND status = 'complete' ORDER BY created_at DESC", (thread_id,)).fetchall()
        for (tid,) in rows:
            t = store.get_trial(tid)
            done = {p["meta"].get("title") for p in t["papers"] if p["status"] == "done"}
            if titles <= done:
                return t
    return latest_trial(thread_id)


def trial_lessons(trial: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What a designer should learn from the trial. Witnesses are numbered W1.. exactly as the Judge numbered them."""
    if not trial:
        return {"available": False, "witnesses": [], "verdict": None}
    done = [p for p in trial["papers"] if p["status"] == "done"]
    witnesses = []
    for i, p in enumerate(done, 1):
        rec, row = p.get("record") or {}, p.get("row") or {}
        witnesses.append({
            "id": f"W{i}", "title": p["meta"].get("title"), "year": p["meta"].get("year"), "weight": p.get("weight"),
            "design": (rec.get("design") or {}).get("value"), "sample_size": (rec.get("sample_size") or {}).get("value"),
            "measures": [{"construct": m.get("construct"), "instrument": m.get("instrument")} for m in rec.get("measures") or []][:6],
            "boundary_conditions": row.get("boundary_conditions"), "blind_spots": row.get("blind_spots"),
            "risks_of_bias": (row.get("appraisal") or {}).get("risks_of_bias"), "access": p.get("access"),
        })
    v = trial.get("verdict") or {}
    return {"available": True, "trial_id": trial["trial_id"], "subclaims": trial["subclaims"], "witnesses": witnesses,
            "verdict": {"overall": v.get("overall"), "per_subclaim": [{"id": s.get("id"), "verdict": s.get("verdict")} for s in v.get("per_subclaim") or []],
                        "gaps": v.get("gaps"), "hypothesis_weaknesses": v.get("hypothesis_weaknesses")}}


_TOKEN = re.compile(r"[A-Za-z]{3,}|[A-Z]{2,}")
_GENERIC = {"scale", "questionnaire", "index", "inventory", "short", "form", "item", "items", "version", "subscale", "the", "and"}


def _instrument_used(instrument: str, witness_measures: List[Dict[str, Any]]) -> bool:
    """Did the witness itself report this instrument? (A shared distinctive word, e.g. 'MBI' or 'Maslach'.)"""
    want = {t.lower() for t in _TOKEN.findall(instrument or "")} - _GENERIC
    have = {t.lower() for m in witness_measures for t in _TOKEN.findall(str(m.get("instrument") or ""))} - _GENERIC
    return bool(want & have)


_UNNAMED = re.compile(r"\b(stud(y|ies)|literature|research|simulations?|evidence|prior work|previous work|meta-analys\w*|reviews?|trials?)\b"
                      r"[^.;]{0,60}?\b(suggest\w*|show\w*|indicat\w*|recommend\w*|report\w*|found|finds|demonstrat\w*)\b", re.I)
_EFFECT = re.compile(r"(f²|\bf2\b|cohen'?s? d|\bd\s*=|\br\s*=|odds ratio|\bOR\s*=|effect size|\bICC\b)", re.I)
_SOURCED = re.compile(r"\bW\d+\b|assum|to be (checked|estimated|confirmed)|placeholder|hypothetical", re.I)


def unsourced(d: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Sentences that lean on unnamed studies or state an effect size, with neither a witness id nor an explicit
    assumption. Returns (kind, sentence)."""
    texts = [d.get(k) for k in ("summary", "can_conclude", "cannot_conclude", "sampling", "sample_size")]
    texts += [f"{t.get('threat', '')}. {t.get('mitigation', '')}" for t in d.get("threats") or [] if isinstance(t, dict)]
    texts += [m.get("note", "") for m in d.get("measures") or [] if isinstance(m, dict)]
    texts += [str(x) for x in (d.get("blockers") or []) + (d.get("changes_to_make_feasible") or [])]
    out = []
    for text in texts:
        for sent in re.split(r"(?<=[.!?])\s+", str(text or "")):
            if not sent.strip() or _SOURCED.search(sent):
                continue
            if _UNNAMED.search(sent):
                out.append(("unnamed", sent.strip()))
            elif _EFFECT.search(sent) and re.search(r"\d", sent):
                out.append(("effect", sent.strip()))
    return list(dict.fromkeys(out))


def enforce(raw: Dict[str, Any], lessons: Dict[str, Any], subclaim_ids: List[int]) -> Dict[str, Any]:
    known = {w["id"]: w["title"] for w in lessons.get("witnesses") or []}
    used = {w["id"]: w.get("measures") or [] for w in lessons.get("witnesses") or []}
    designs, notes = [], []
    for d in (raw.get("designs") or [])[:3]:
        if not isinstance(d, dict) or not d.get("name"):
            continue
        dtype = d.get("design_type") if d.get("design_type") in DESIGN_TYPES else "other"
        can, cannot = str(d.get("can_conclude") or ""), str(d.get("cannot_conclude") or "")
        if dtype not in CAUSAL_CAPABLE and _CAUSAL_CLAIM.search(can):
            notes.append(f"'{d['name']}': a {dtype.replace('_', ' ')} design cannot show causation, so that claim was removed.")
            can = "Associations between the measured variables, not causes."
            cannot = (cannot + "; " if cannot else "") + "causation"
        measures = []
        for m in d.get("measures") or []:
            if not isinstance(m, dict):
                continue
            src = str(m.get("source_witness_id") or "new").strip()
            if src not in known:
                if src != "new":
                    notes.append(f"'{d['name']}': measure '{m.get('instrument')}' cited {src}, which is not a witness in this trial; marked new.")
                src = "new"
            # "used": the witness reported this instrument; "related": cited, but the witness didn't report it.
            match = "new" if src == "new" else ("used" if _instrument_used(m.get("instrument", ""), used[src]) else "related")
            measures.append({"construct": m.get("construct", ""), "instrument": m.get("instrument", ""), "source_witness_id": src,
                             "source_match": match, "source_title": known.get(src, ""),
                             "note": m.get("note", "") or ("needs validation" if src == "new" else "")})
        size = str(d.get("sample_size") or "")
        if re.search(r"\d", size) and not re.search(r"assum|power", size, re.I):
            size += " (assumption not stated; needs a power analysis before this number is used)"
        designs.append({
            "name": str(d["name"]), "design_type": dtype, "summary": str(d.get("summary") or ""),
            "can_conclude": can, "cannot_conclude": cannot,
            "tests_subclaims": [int(x) for x in d.get("tests_subclaims") or [] if str(x).isdigit() and int(x) in subclaim_ids],
            "measures": measures, "sampling": str(d.get("sampling") or ""), "sample_size": size,
            "threats": [t for t in d.get("threats") or [] if isinstance(t, dict) and t.get("validity") in VALIDITY],
            "feasibility": d.get("feasibility") if d.get("feasibility") in FEASIBILITY else "feasible_with_changes",
            "blockers": [str(b) for b in d.get("blockers") or []][:6],
            "changes_to_make_feasible": [str(c) for c in d.get("changes_to_make_feasible") or []][:5],
        })
        designs[-1]["trial_id"] = lessons.get("trial_id")
        flagged = unsourced(designs[-1])
        designs[-1]["unsourced"] = [s for _, s in flagged]
        for kind, sent in flagged:
            notes.append(f"'{d['name']}': “{sent[:120]}” " + ("appeals to unnamed studies; cite a trial witness (e.g. W3) or mark it as an assumption."
                                                              if kind == "unnamed" else "states an effect size with no source; cite a witness or mark it as assumed."))
    names = [d["name"] for d in designs]
    recommended = raw.get("recommended") if raw.get("recommended") in names else (names[0] if names else "")
    return {"designs": designs, "recommended": recommended, "why": str(raw.get("why") or ""),
            "what_others_add": str(raw.get("what_others_add") or ""), "guardrail_notes": list(dict.fromkeys(notes)),
            "lessons_used": lessons.get("available", False), "designed_by": str(raw.get("_served_by") or ""),
            "trial_id": lessons.get("trial_id")}


async def propose(hypothesis: str, subclaims: List[Dict[str, Any]], resources: Dict[str, str],
                  lessons: Dict[str, Any]) -> Dict[str, Any]:
    human = (f"<hypothesis>{hypothesis}</hypothesis>\n<subclaims>{json.dumps(subclaims)}</subclaims>\n"
             f"<trial_lessons>\n{json.dumps(lessons)}\n</trial_lessons>\n<resources>{json.dumps(resources)}</resources>")
    raw = await call_json("designer", PROMPT, human, default={}) or {}
    return enforce(raw if isinstance(raw, dict) else {}, lessons, [int(s["id"]) for s in subclaims])


REVISE_PROMPT = """ROLE
You are Thoth's Designer. A peer reviewer found problems that only a change to the study design can fix. Your job:
revise the chosen design to answer them, within the researcher's resources.

METHOD
1. Read each finding: the problem and the suggested fix.
2. Change the chosen design as little as needed to answer each finding: measures, timing, sampling or analysis.
3. Check the revision against the resources; if a finding cannot be answered within them, say so.
4. Keep everything the findings don't touch.

OUTPUT (JSON)
{"design": {same fields as a candidate design: name, design_type, summary, can_conclude, cannot_conclude,
            tests_subclaims, measures, sampling, sample_size, threats, feasibility, blockers, changes_to_make_feasible},
 "changes": [{"finding_id": "R1", "change": str}],
 "unresolved": [{"finding_id": "R1", "why": str}]}

RULES
- Never invent effect sizes, reliability coefficients or instrument properties; cite a witness id or say "assumed".
- Never describe a non-causal design as able to show causation.
- Use only witness ids that appear in the trial lessons. Name the revision so it is clearly a revision."""


async def revise(chosen: Dict[str, Any], findings: List[Dict[str, Any]], hypothesis: str, subclaims: List[Dict[str, Any]],
                 resources: Dict[str, str], lessons: Dict[str, Any]) -> Dict[str, Any]:
    """One revised design answering design-level review findings (docs/features/07, 08). Same guardrails as propose."""
    base = {k: v for k, v in chosen.items() if k not in ("version", "author", "unsourced")}
    human = (f"<hypothesis>{hypothesis}</hypothesis>\n<subclaims>{json.dumps(subclaims)}</subclaims>\n"
             f"<chosen_design>{json.dumps(base)}</chosen_design>\n"
             f"<findings>{json.dumps([{k: f.get(k) for k in ('id', 'problem', 'fix')} for f in findings])}</findings>\n"
             f"<trial_lessons>\n{json.dumps(lessons)}\n</trial_lessons>\n<resources>{json.dumps(resources)}</resources>")
    raw = await call_json("designer", REVISE_PROMPT, human, default={}) or {}
    raw = raw if isinstance(raw, dict) else {}
    design = raw.get("design") if isinstance(raw.get("design"), dict) else {}
    if design and design.get("name") == chosen.get("name"):
        design["name"] = f"{design['name']} (revised)"
    out = enforce({"designs": [design] if design else [], "recommended": design.get("name")}, lessons, [int(s["id"]) for s in subclaims])
    ids = {f.get("id") for f in findings}
    if out["designs"]:
        rev = out["designs"][0]
        changes = [c for c in raw.get("changes") or [] if isinstance(c, dict) and c.get("finding_id") in ids]
        rev.update(revision_of=chosen.get("name"), addresses=list(dict.fromkeys(c["finding_id"] for c in changes)),
                   changes=[{"finding_id": c["finding_id"], "change": str(c.get("change") or "")[:500]} for c in changes],
                   unresolved=[{"finding_id": u["finding_id"], "why": str(u.get("why") or "")[:500]}
                               for u in raw.get("unresolved") or [] if isinstance(u, dict) and u.get("finding_id") in ids],
                   findings=[{k: f.get(k) for k in ("id", "problem", "fix")} for f in findings])
    return out

