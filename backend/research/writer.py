"""Writer (docs/features/08-writing.md; prompt in 09 § Writer).

Proposes the proposal outline, then writes ONE section at a time from the research file only: the latest
completed trial (witnesses numbered W1.. exactly as the Judge and Designer numbered them), the chosen design,
the hypothesis, the question and the researcher's own "I say" text. Guardrails enforced in code:
- the Writer never writes the references (they are built from cited witnesses only);
- a section whose source material is missing gets a [GAP: …] marker, whatever the model wrote;
- "Expected outcomes" must say what would refute the hypothesis, or a GAP says it doesn't.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from backend.memory import conversation_store as notebook
from backend.research import designer
from backend.research.llm import call_json

# The default outline (doc 08). "references" is never written by a model.
DEFAULT_OUTLINE = [
    {"key": "title_abstract", "title": "Title and abstract", "purpose": "A working title and a 150-250 word abstract: question, hypothesis, design, why it matters."},
    {"key": "background", "title": "Background and rationale", "purpose": "Why the question matters, from the strongest and weakest witnesses (floor and ceiling papers)."},
    {"key": "literature", "title": "Literature review", "purpose": "Per sub-claim: the trial's verdict, the case for and against, stances, and conflicts explained."},
    {"key": "gap", "title": "Gap and contribution", "purpose": "Only gaps the witnesses reveal; the originality verdict quoted honestly."},
    {"key": "question_hypothesis", "title": "Research question and hypothesis", "purpose": "The question and hypothesis as stated, with sub-claims and what would falsify them."},
    {"key": "methods", "title": "Methods", "purpose": "The chosen design: measures, sample, analysis plan, threats to validity and how each is handled."},
    {"key": "expected_outcomes", "title": "Expected outcomes and interpretation", "purpose": "Each plausible result and what it would mean, including the result that refutes the hypothesis."},
    {"key": "limitations_ethics", "title": "Limitations and ethics", "purpose": "What this design cannot conclude; ethics route and participant risks."},
    {"key": "timeline", "title": "Timeline and resources", "purpose": "A timeline and resource plan within the researcher's stated resources."},
    {"key": "references", "title": "References", "purpose": "Built automatically from the witnesses cited in the sections above."},
]
REFERENCES = "references"
MAX_SECTIONS = 14

OUTLINE_PROMPT = """ROLE
You are Thoth's Writer. Tailor the purpose line of each section of a research proposal outline to this project.

METHOD
1. Read the research file: question, hypothesis, trial verdict, chosen design.
2. For each section key you are given, write one sentence saying what this section will cover FOR THIS PROJECT,
   naming what in the research file it will draw on. If the file lacks what a section needs, say so.

OUTPUT (JSON)
{"sections": [{"key": str, "purpose": str}]}

RULES
- Use only the keys given. Do not add facts that are not in the research file."""

PROMPT = """ROLE
You are Thoth's Writer. Write ONE section of a research proposal, using only the research file.

METHOD
1. Read the section's purpose in the outline and the research file.
2. Write in clear academic prose. Prefer the researcher's own "I say" wording (researcher_says) where it exists.
3. After every factual sentence, add a marker naming the witness it rests on: {{w:W3}}, or for one matrix cell
   {{cell:W3.subclaim2}}. A sentence that rests on the research file itself rather than a paper (the trial
   verdict, the gaps, the chosen design, the researcher's resources) gets {{file:verdict}}, {{file:gaps}},
   {{file:originality}}, {{file:design}}, {{file:resources}}, {{file:hypothesis}} or {{file:question}}.
   The Verifier turns markers into citations and removes claims the witness does not support.
4. If the section needs something the file does not contain, write [GAP: what is missing].

OUTPUT (JSON)
{"markdown": "the section only, in Markdown, starting with its ## heading"}

RULES
- No facts that are not in the research file. No references list. No author names or years: use markers.
- Never write witness ids (W3) in the prose itself: describe the study ("a cross-sectional survey of 229 nurses")
  and put the id only in the marker. Readers of the proposal never see witness ids.
- Keep disagreements and caveats visible. Do not upgrade "contested" or "insufficient evidence" to "supported".
- An abstract-only witness supports only what its abstract states; say so where it matters.
- Proposed work is future tense ("will"); what witnesses found is past tense with a marker.
- In "Expected outcomes", include the result that would refute the hypothesis and what it would mean."""

REVISE = """
REVISION
A reviewer found this problem in your previous version of the section. Rewrite the section to fix it, still
using only the research file. If fixing it needs something the file does not contain, write [GAP: …] instead
of inventing it.
<previous_version>{previous}</previous_version>
<problem severity="{severity}">{problem}</problem>
<suggested_fix>{fix}</suggested_fix>"""

_MARKER = re.compile(r"\{\{\s*(w|cell|file)\s*:\s*([^}]+?)\s*\}\}")
_REFUTES = re.compile(r"refut|falsif|disconfirm|not support|count(s)? against|contradict|null (result|finding)|no (difference|association)", re.I)


def _section(thread: str, kind: str) -> Optional[Dict[str, Any]]:
    sec = notebook.notebook_snapshot(thread).get(kind)
    if not sec:
        return None
    try:
        return json.loads(sec["content"])
    except Exception:
        return {"text": sec["content"]}


def _text(thread: str, kind: str) -> str:
    sec = notebook.notebook_snapshot(thread).get(kind)
    return (sec or {}).get("content", "").strip()


def research_file(thread: str) -> Dict[str, Any]:
    """Everything the Writer may draw on, and nothing else. Witness ids match designer.trial_lessons."""
    # The design's witness ids belong to the trial it was built from; read that trial so W3 means the same paper
    # in the Methods as in the design (a newer trial would renumber them).
    trial = designer.trial_for_design(thread, _section(thread, "design"))
    witnesses: List[Dict[str, Any]] = []
    verdict: Dict[str, Any] = {}
    subclaims: List[Dict[str, Any]] = []
    if trial:
        subclaims = trial.get("subclaims") or []
        done = [p for p in trial["papers"] if p["status"] == "done"]
        for i, p in enumerate(done, 1):
            rec, row, meta = p.get("record") or {}, p.get("row") or {}, p.get("meta") or {}
            witnesses.append({
                "id": f"W{i}", "title": meta.get("title"), "year": meta.get("year"), "authors": (meta.get("authors") or [])[:6],
                "doi": meta.get("doi"), "url": meta.get("url"), "venue": meta.get("venue"), "abstract": (meta.get("abstract") or "")[:1800],
                "access": p.get("access"), "weight": p.get("weight"),
                "design": (rec.get("design") or {}).get("value"), "sample_size": (rec.get("sample_size") or {}).get("value"),
                "population": (rec.get("population") or {}).get("value"), "setting": (rec.get("setting") or {}).get("value"),
                "measures": [{"construct": m.get("construct"), "instrument": m.get("instrument")} for m in rec.get("measures") or []][:6],
                "results": [{k: r.get(k) for k in ("finding", "numbers", "locator", "provenance")} for r in rec.get("results") or []][:8],
                "limitations_stated": (rec.get("limitations_stated") or [])[:4],
                "per_subclaim": [{k: s.get(k) for k in ("id", "direction", "locator", "note")} for s in row.get("per_subclaim") or []],
                "stance": row.get("stance"), "floor_or_ceiling": row.get("floor_or_ceiling"),
                "boundary_conditions": (row.get("boundary_conditions") or [])[:4],
                "risks_of_bias": ((row.get("appraisal") or {}).get("risks_of_bias") or [])[:4],
                "researcher_says": p.get("i_say_user") or None,
                "analyst_reading": None if p.get("i_say_user") else row.get("i_say_draft"),
            })
        v = trial.get("verdict") or {}
        verdict = {k: v.get(k) for k in ("overall", "per_subclaim", "originality", "gaps", "hypothesis_weaknesses", "guardrail_notes")}
        verdict["witnesses"], verdict["full_text_witnesses"] = v.get("witnesses"), v.get("full_text_witnesses")
    design = _section(thread, "design")
    if design:
        design = {k: v for k, v in design.items() if k not in ("version", "author")}
    return {
        "question": _text(thread, "question"), "hypothesis": _text(thread, "hypothesis") or (trial or {}).get("hypothesis", ""),
        "subclaims": subclaims, "trial_available": bool(trial), "verdict": verdict, "witnesses": witnesses,
        "design": design, "resources": _section(thread, "resources"),
    }


def file_keys(rf: Dict[str, Any]) -> Dict[str, bool]:
    """Which {{file:…}} markers can resolve: the part of the research file must exist."""
    v = rf.get("verdict") or {}
    return {"question": bool(rf.get("question")), "hypothesis": bool(rf.get("hypothesis")), "verdict": bool(v.get("overall")),
            "gaps": bool(v.get("gaps")), "originality": bool(v.get("originality")), "design": bool(rf.get("design")),
            "resources": bool(rf.get("resources") and any((rf.get("resources") or {}).values()))}


# What a section cannot be written without. Missing → a GAP marker, whatever the model said.
NEEDS = {
    "background": ("trial", "a completed trial (no witnesses to draw on)"),
    "literature": ("trial", "a completed trial (no witnesses to review)"),
    "gap": ("trial", "a completed trial (gaps must be revealed by witnesses)"),
    "question_hypothesis": ("hypothesis", "a pinned hypothesis"),
    "methods": ("design", "a chosen study design (choose one in the Design tab)"),
    "expected_outcomes": ("hypothesis", "a pinned hypothesis"),
    "limitations_ethics": ("design", "a chosen study design"),
    "timeline": ("resources", "the researcher's resources (time, budget, access)"),
}


def missing_for(key: str, rf: Dict[str, Any]) -> Optional[str]:
    need = NEEDS.get(key)
    if not need:
        return None
    have = {"trial": rf.get("trial_available") and rf.get("witnesses"), "hypothesis": rf.get("hypothesis"),
            "design": rf.get("design"), "resources": file_keys(rf)["resources"]}
    return None if have.get(need[0]) else need[1]


def default_outline() -> List[Dict[str, str]]:
    return [dict(s) for s in DEFAULT_OUTLINE]


def clean_outline(outline: Any) -> List[Dict[str, str]]:
    """The researcher may reorder, rename, re-purpose, add or drop sections. References always come last."""
    out, seen = [], set()
    for s in outline if isinstance(outline, list) else []:
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or "").strip()[:120]
        key = re.sub(r"[^a-z0-9_]", "_", str(s.get("key") or title).strip().lower())[:40].strip("_")
        if not title or not key or key in seen or key == REFERENCES:
            continue
        seen.add(key)
        out.append({"key": key, "title": title, "purpose": str(s.get("purpose") or "").strip()[:400]})
    out = out[:MAX_SECTIONS - 1]
    out.append(dict(DEFAULT_OUTLINE[-1]))
    return out


async def propose_outline(rf: Dict[str, Any]) -> Dict[str, Any]:
    outline = default_outline()
    keys = [s["key"] for s in outline if s["key"] != REFERENCES]
    human = (f"<section_keys>{json.dumps([{'key': s['key'], 'title': s['title'], 'default_purpose': s['purpose']} for s in outline[:-1]])}</section_keys>\n"
             f"<research_file>\n{json.dumps(_compact(rf, 'outline'))}\n</research_file>")
    served = ""
    try:
        raw = await call_json("writer", OUTLINE_PROMPT, human, default={}) or {}
        served = str(raw.get("_served_by") or "") if isinstance(raw, dict) else ""
        tailored = {s.get("key"): str(s.get("purpose") or "") for s in (raw.get("sections") or []) if isinstance(s, dict)}
    except Exception:
        tailored = {}
    for s in outline:
        if s["key"] in keys and tailored.get(s["key"]):
            s["purpose"] = tailored[s["key"]][:400]
        gap = missing_for(s["key"], rf)
        if gap:
            s["missing"] = gap
    return {"outline": outline, "tailored": bool(tailored), "outlined_by": served}


# Which sections need the witnesses' full records, and which need the full design. The rest get a brief view,
# so nine section calls don't each carry the whole file (~75 KB on the night-shift project).
FULL_WITNESSES = {"background", "literature", "gap"}
FULL_DESIGN = {"title_abstract", "methods", "expected_outcomes", "limitations_ethics", "timeline"}
_BRIEF_W = ("id", "title", "year", "design", "access", "weight", "stance", "floor_or_ceiling", "researcher_says")
_BRIEF_D = ("name", "design_type", "summary", "can_conclude", "cannot_conclude", "researcher_notes")


def _compact(rf: Dict[str, Any], key: str = "") -> Dict[str, Any]:
    """The research file for one section, without bibliographic detail the Writer must not use (authors, DOIs, URLs)."""
    full = key in FULL_WITNESSES or not key
    ws = []
    for w in rf["witnesses"]:
        keep = {k: v for k, v in w.items() if k not in ("authors", "doi", "url", "venue") and v not in (None, [], "")}
        if full:
            keep["abstract"] = (keep.get("abstract") or "")[:600] if not w.get("results") else ""
            keep["results"] = [{"finding": str(r.get("finding") or "")[:260], "numbers": r.get("numbers"), "provenance": r.get("provenance")}
                               for r in w.get("results") or []][:5]
            keep["per_subclaim"] = [{"id": p.get("id"), "direction": p.get("direction"), "note": str(p.get("note") or "")[:180]}
                                    for p in w.get("per_subclaim") or [] if p.get("direction") != "not_addressed"]
            for k, n in (("measures", 4), ("boundary_conditions", 2), ("risks_of_bias", 2), ("limitations_stated", 2)):
                keep[k] = [str(x)[:200] if not isinstance(x, dict) else x for x in keep.get(k) or []][:n]
        else:
            keep = {k: v for k, v in keep.items() if k in _BRIEF_W}
        ws.append({k: v for k, v in keep.items() if v not in (None, [], "")})
    design = rf.get("design")
    if design and key and key not in FULL_DESIGN:
        design = {k: design.get(k) for k in _BRIEF_D if design.get(k)}
    verdict = dict(rf.get("verdict") or {})
    if key and key not in FULL_WITNESSES | {"title_abstract", "question_hypothesis", "expected_outcomes"}:
        verdict["per_subclaim"] = [{k: p.get(k) for k in ("id", "claim", "verdict", "certainty")} for p in verdict.get("per_subclaim") or []]
    return {**{k: v for k, v in rf.items() if k not in ("witnesses", "design", "verdict")}, "verdict": verdict, "design": design, "witnesses": ws}


def enforce(markdown: str, section: Dict[str, str], rf: Dict[str, Any]) -> Dict[str, Any]:
    text = str(markdown or "").strip()
    notes = []
    # The Writer never writes references: drop any list it adds.
    stripped = re.sub(r"(?is)\n#{1,6}\s*(references|bibliography|sources)\b.*$", "", "\n" + text).strip()
    if stripped != text:
        notes.append("The Writer added a references list; it was removed (references are built from cited witnesses).")
        text = stripped
    body = re.sub(r"^\s*#{1,6}[^\n]*\n?", "", text, count=1).strip() if text.lstrip().startswith("#") else text
    # Witness ids in the prose become markers (so they are checked and cited), or are dropped from descriptions.
    ids_only = re.compile(r"\s*\((W\d+(?:\s*(?:,|;|and)\s*W\d+)*)\)")
    if ids_only.search(body) or re.search(r"\(W\d+[,;]\s*(?!W\d)", body):
        notes.append("Witness ids written into the prose were turned into evidence markers.")
    body = ids_only.sub(lambda m: " " + "".join(f"{{{{w:{w}}}}}" for w in re.findall(r"W\d+", m.group(1))), body)
    body = re.sub(r"\((W\d+)[,;]\s*(?!W\d)", "(", body)
    text = f"## {section['title']}\n\n{body}".strip()
    gap = missing_for(section["key"], rf)
    if gap and f"[GAP: {gap}" not in text:
        text += f"\n\n[GAP: this section needs {gap}.]"
    if section["key"] == "expected_outcomes" and not _REFUTES.search(body):
        text += "\n\n[GAP: the result that would refute the hypothesis, and what it would mean, is not described.]"
    return {"markdown": text, "notes": notes}


async def write_section(section: Dict[str, str], outline: List[Dict[str, str]], rf: Dict[str, Any],
                        earlier: List[Dict[str, str]], revision: Optional[Dict[str, str]] = None,
                        instruction: str = "") -> Dict[str, Any]:
    gap = missing_for(section["key"], rf)
    human = (f"<section>{json.dumps({'title': section['title'], 'purpose': section.get('purpose', '')})}</section>\n"
             f"<outline>{json.dumps([{'title': s['title'], 'purpose': s.get('purpose', '')} for s in outline])}</outline>\n"
             f"<sections_already_written>{json.dumps([{'title': e['title'], 'opening': e['markdown'][:500]} for e in earlier])}</sections_already_written>\n"
             f"<research_file>\n{json.dumps(_compact(rf, section['key']))}\n</research_file>")
    if gap:
        human += f"\n<missing>The research file has no {gap}. Write [GAP: …] where it would be needed.</missing>"
    if instruction:
        human += f"\n<researcher_instruction><untrusted>{instruction[:800]}</untrusted></researcher_instruction>"
    system = PROMPT + (REVISE.format(**revision) if revision else "")
    try:
        raw = await call_json("writer", system, human, default={}) or {}
    except Exception:
        raw = {}
    md = raw.get("markdown") if isinstance(raw, dict) else None
    if not isinstance(md, str) or not md.strip():
        return {"markdown": "", "degraded": True, "notes": [], "written_by": ""}
    out = enforce(md, section, rf)
    return {**out, "degraded": False, "written_by": str(raw.get("_served_by") or "")}
