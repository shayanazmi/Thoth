"""Verifier (docs/features/08-writing.md; prompt in 09 § Verifier).

Checks every factual sentence of a section against the record of the witness it cites, then turns evidence
markers into citations. Deterministic checks run first, in code:
- the cited witness must exist in the research file, and its record must have readable content;
- numbers in the sentence must appear in the witness's record (integrity_gate.verify_quantitative_claim and a
  plain number check), otherwise the sentence is removed as number_mismatch;
- a {{file:…}} marker must point at a part of the research file that exists;
- a factual-looking sentence with no marker is flagged "uncited" (kept, shown, and the proposal stays provisional).
Only then does the model judge entailment, one sentence at a time. Unsupported sentences are softened or
removed, and every removal is recorded. If the model can't be reached, the sentence is flagged "not checked":
it is never reported as verified.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.intellectual_rigour.integrity_gate import verify_quantitative_claim
from backend.research.llm import call_json

SUPPORT = ("supports", "partially_supports", "does_not_support", "refutes")
PROBLEMS = ("none", "overgeneralization", "direction_inversion", "causal_leap", "predicate_drift", "number_mismatch")
ACTIONS = ("keep", "soften", "remove")

PROMPT = """ROLE
You are Thoth's Verifier. For ONE sentence and the passage it cites, decide whether the passage
supports the sentence exactly as written.

METHOD
1. Restate the sentence's claim in its strongest form: who, what, how much, causal or associational.
2. Restate what the passage actually says, the same way.
3. Compare. Look specifically for:
   overgeneralization (sample → everyone), direction_inversion, causal_leap (association → cause),
   predicate_drift (a different outcome or measure), number_mismatch.
4. Decide, and if the sentence can be fixed by weakening it, give the weakened wording.

OUTPUT (JSON)
{"support": "supports"|"partially_supports"|"does_not_support"|"refutes",
 "problem": "none"|"overgeneralization"|"direction_inversion"|"causal_leap"|"predicate_drift"|"number_mismatch",
 "action": "keep"|"soften"|"remove", "softened": str, "why": str}

RULES
- Same topic is not support. A quotation being present is not support.
- An abstract-only passage supports only what the abstract states.
- "softened" must claim no more than the passage states, and must not add anything new.

EXAMPLE
Sentence "Night shifts cause burnout in nurses". Passage: "night-shift nurses reported higher exhaustion than
day-shift nurses (cross-sectional)". Correct: partially_supports, causal_leap, soften → "Night-shift nurses
reported higher exhaustion than day-shift nurses in a cross-sectional survey"."""

# Evidence markers: the Writer's {{w:W3}} / {{cell:W3.subclaim2}} / {{file:design}}, and the [W3] / [W3; W10]
# citations the app shows, so a section the researcher edited can be verified again.
MARKER = re.compile(r"\{\{\s*(w|cell|file)\s*:\s*([^}]+?)\s*\}\}")
CITE = re.compile(r"\[(W\d+(?:\s*[;,]\s*W\d+)*)\]")
GAP = re.compile(r"\[GAP:[^\]]*\]")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“(\[*_])")
_LIST = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)(.*)$")
_FUTURE = re.compile(r"\b(will|would|could|should|we propose|this (study|proposal|project)|the (study|proposal|project)|aims? to|plan(s|ned)? to|propose[sd]?|intend)\b", re.I)
_FACTUAL = re.compile(r"\b(studies|literature|evidence (shows|suggests|indicates)|found|finds|report(ed|s)|show(n|ed|s)|"
                      r"demonstrat\w*|associat\w*|correlat\w*|meta-analys\w*|previous(ly)?|prior work|according to|"
                      r"is known|are known|has been|have been|increase[sd]?|decrease[sd]?|higher|lower|\d+(\.\d+)?\s*%)", re.I)
# Sentences about the proposal itself (its hypothesis, sub-claims, conditional outcomes, labelled lines) are not
# claims about the world, even when they use words like "associated" or "higher".
_ABOUT_PROPOSAL = re.compile(r"(^\*\*[^*]{1,40}:\*\*|^\*\*[^*]{1,40}\*\*\s*:|^if\b|^whether\b|hypothes[ie]s|sub-?claims?|research question|"
                             r"we ask|this proposal|is tested|are tested|will be tested|would (mean|suggest|indicate|support))", re.I)
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")


def markers(sentence: str) -> Tuple[List[str], List[str], Dict[str, int]]:
    """(witness ids, file keys, cell sub-claims by witness) cited by a sentence."""
    ws: List[str] = []
    files: List[str] = []
    cells: Dict[str, int] = {}
    for kind, val in MARKER.findall(sentence):
        for v in re.split(r"\s*[;,]\s*", val):
            if kind == "file":
                files.append(v.strip().lower())
                continue
            m = re.match(r"(W\d+)(?:\.subclaim(\d+))?", v.strip(), re.I)
            if m:
                ws.append(m.group(1).upper())
                if kind == "cell" and m.group(2):
                    cells[m.group(1).upper()] = int(m.group(2))
    for grp in CITE.findall(sentence):
        ws.extend(re.split(r"\s*[;,]\s*", grp))
    return list(dict.fromkeys(ws)), list(dict.fromkeys(files)), cells


def strip_markers(sentence: str) -> str:
    s = MARKER.sub("", sentence)
    s = CITE.sub("", s)
    return re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", s)).strip()


def segment(markdown: str) -> List[Dict[str, Any]]:
    """Split a section into layout text and sentences. Joining every segment's text gives the section back."""
    mk = r"(?:\{\{[^}]+\}\}|\[W\d+(?:\s*[;,]\s*W\d+)*\])"
    md = re.sub(rf"([.!?])[ \t]*((?:{mk}[ \t]*)*{mk})", lambda m: " " + m.group(2).strip() + m.group(1), markdown or "")
    segs: List[Dict[str, Any]] = []
    n = 0
    blocks = re.split(r"(\n\s*\n)", md)
    for block in blocks:
        if not block.strip() or re.fullmatch(r"\n\s*\n", block):
            segs.append({"t": "text", "text": block})
            continue
        lines = block.split("\n")
        for li, line in enumerate(lines):
            nl = "\n" if li < len(lines) - 1 else ""
            if not line.strip() or line.lstrip().startswith("#") or line.strip().startswith("|"):
                segs.append({"t": "text", "text": line + nl})
                continue
            prefix, body = "", line
            m = _LIST.match(line)
            if m:
                prefix, body = m.group(1), m.group(2)
            if prefix:
                segs.append({"t": "text", "text": prefix})
            parts = _SPLIT.split(body.strip())
            lead = body[: len(body) - len(body.lstrip())]
            if lead and not prefix:
                segs.append({"t": "text", "text": lead})
            for pi, p in enumerate(parts):
                segs.append({"t": "s", "i": n, "text": p})
                n += 1
                if pi < len(parts) - 1:
                    segs.append({"t": "text", "text": " "})
            if nl:
                segs.append({"t": "text", "text": nl})
    return segs


def looks_factual(sentence: str) -> bool:
    plain = strip_markers(GAP.sub("", sentence))
    plain = re.sub(r"^\*\*[^*]{1,40}\*\*\s*:\s*(?=if\b)", "", plain, flags=re.I)
    if len(plain) < 25 or plain.endswith("?") or plain.endswith(":"):
        return False
    return bool(_FACTUAL.search(plain)) and not _FUTURE.search(plain) and not _ABOUT_PROPOSAL.search(plain)


def passage(w: Dict[str, Any], cell: Optional[int] = None) -> str:
    """What the witness's record actually holds: the only thing a sentence citing it may rest on."""
    lines = [f'Witness {w["id"]}: "{w.get("title") or "untitled"}" ({w.get("year") or "n.d."}). Access: {w.get("access") or "unknown"}.']
    for k in ("design", "sample_size", "population", "setting"):
        if w.get(k):
            lines.append(f"{k.replace('_', ' ').capitalize()}: {w[k]}")
    if w.get("measures"):
        lines.append("Measures: " + "; ".join(f"{m.get('construct')}: {m.get('instrument')}" for m in w["measures"]))
    for r in w.get("results") or []:
        lines.append(f"Result: {r.get('finding')}" + (f" ({r['numbers']})" if r.get("numbers") else "") + f" [{r.get('locator')}, {r.get('provenance')}]")
    for s in w.get("per_subclaim") or []:
        if cell is None or s.get("id") == cell:
            lines.append(f"Analyst's reading for sub-claim {s.get('id')}: {s.get('direction')} — {s.get('note')}")
    if w.get("researcher_says"):
        lines.append(f"Researcher's own reading: {w['researcher_says']}")
    if w.get("limitations_stated"):
        lines.append("Limitations the authors state: " + "; ".join(map(str, w["limitations_stated"])))
    if w.get("abstract"):
        lines.append(f"Abstract: {w['abstract']}")
    return "\n".join(lines)


def readable(w: Dict[str, Any]) -> bool:
    return bool(w.get("results") or w.get("abstract") or w.get("researcher_says"))


def _numbers_ok(sentence: str, text: str) -> Tuple[bool, str]:
    claim = strip_markers(sentence)
    status, reason = verify_quantitative_claim(claim, "src-w", [{"id": "src-w", "extracted_text": text}])
    if status in ("CONTRADICTED", "UNSUPPORTED"):
        return False, reason or "a number in the sentence is not in the witness's record"
    low = text.lower().replace(",", "")
    for num in _NUM.findall(claim):
        bare = num.replace(",", "").rstrip("%")
        try:
            if float(bare) < 10 and "." not in bare:
                continue  # small counts ("two studies", "sub-claim 3") are not the witness's numbers
        except ValueError:
            continue
        if bare not in low:
            return False, f"{num} does not appear in the cited witness's record"
    return True, ""


def _result(i: int, text: str, **kw: Any) -> Dict[str, Any]:
    base = {"i": i, "original": text, "witnesses": [], "files": [], "kind": "claim", "support": None, "problem": "none",
            "action": "keep", "final": strip_markers(text), "why": "", "checked_by": ""}
    return {**base, **kw}


async def check_sentence(i: int, text: str, by_id: Dict[str, Dict[str, Any]], fkeys: Dict[str, bool]) -> Dict[str, Any]:
    if GAP.search(text) and not MARKER.search(text) and not CITE.search(text):
        return _result(i, text, kind="gap")
    ws, files, cells = markers(text)
    if not ws and not files:
        if looks_factual(text):
            return _result(i, text, kind="uncited", action="flag", why="A factual-looking sentence with no source marker.")
        return _result(i, text, kind="prose")
    bad_files = [f for f in files if not fkeys.get(f)]
    unknown = [w for w in ws if w not in by_id]
    known = [w for w in ws if w in by_id]
    if not known:
        if unknown:
            return _result(i, text, witnesses=[], files=files, support="does_not_support", problem="none", action="remove",
                           why=f"Cites {', '.join(unknown)}, which {'is' if len(unknown) == 1 else 'are'} not a witness in this research file.")
        if bad_files:
            return _result(i, text, files=files, kind="uncited", action="flag",
                           why=f"Rests on the research file's {', '.join(bad_files)}, which does not exist yet.")
        return _result(i, text, files=files, kind="file")
    usable = [w for w in known if readable(by_id[w])]
    if not usable:
        return _result(i, text, witnesses=known, support="does_not_support", action="remove",
                       why=f"The record of {', '.join(known)} has no readable content (no results, abstract or reading).")
    text_all = "\n\n".join(passage(by_id[w], cells.get(w)) for w in usable)
    ok, why = _numbers_ok(text, text_all)
    if not ok:
        return _result(i, text, witnesses=usable, files=files, support="does_not_support", problem="number_mismatch", action="remove", why=why)
    try:
        raw = await call_json("verifier", PROMPT, f"<sentence>{strip_markers(text)}</sentence>\n<untrusted>\n{text_all}\n</untrusted>", default=None)
    except Exception:
        raw = None
    if not isinstance(raw, dict) or raw.get("support") not in SUPPORT:
        return _result(i, text, witnesses=usable, files=files, kind="unchecked", action="flag",
                       why="The Verifier could not be reached; this sentence was not checked.")
    return _result(i, text, witnesses=usable, files=files, **enforce(raw, text_all, unknown))


def enforce(raw: Dict[str, Any], text_all: str, unknown: List[str]) -> Dict[str, Any]:
    support = raw["support"]
    problem = raw.get("problem") if raw.get("problem") in PROBLEMS else "none"
    action = raw.get("action") if raw.get("action") in ACTIONS else "remove"
    softened = strip_markers(str(raw.get("softened") or "")).strip()
    why = str(raw.get("why") or "")[:500]
    # Labels must agree: only "supports" may keep the sentence as written.
    if action == "keep" and support != "supports":
        action = "soften" if softened else "remove"
    if support in ("does_not_support", "refutes") and action == "soften" and not softened:
        action = "remove"
    if action == "soften":
        if not softened:
            action = "remove"
        elif not _numbers_ok(softened, text_all)[0]:
            action, why = "remove", (why + " The softened wording still had a number the record does not contain.").strip()
    if unknown:
        why = (why + f" Citation to {', '.join(unknown)} dropped: not a witness in this research file.").strip()
    out = {"support": support, "problem": problem, "action": action, "why": why, "checked_by": str(raw.get("_served_by") or "")}
    if action == "soften":
        out["final"] = softened
    return out


def cite(sentence_final: str, ids: List[str], files: Optional[List[str]] = None) -> str:
    """Attach [W3; W10] citations, and keep {{file:…}} markers so an edited section can be verified again
    (readers never see them: rendering strips them)."""
    if not ids and not files:
        return sentence_final
    s = sentence_final.rstrip()
    end = s[-1] if s and s[-1] in ".!?" else ""
    core = s[:-1].rstrip() if end else s
    tail = (f" [{'; '.join(ids)}]" if ids else "") + "".join(f" {{{{file:{f}}}}}" for f in files or [])
    return f"{core}{tail}{end or '.'}"


async def verify_section(markdown: str, witnesses: List[Dict[str, Any]], fkeys: Dict[str, bool]) -> Dict[str, Any]:
    by_id = {w["id"]: w for w in witnesses}
    segs = segment(markdown)
    sentences = [s for s in segs if s["t"] == "s"]
    results = await asyncio.gather(*[check_sentence(s["i"], s["text"], by_id, fkeys) for s in sentences])
    by_i = {r["i"]: r for r in results}
    out_segs, final = [], []
    for s in segs:
        if s["t"] == "text":
            out_segs.append(s)
            final.append(s["text"])
            continue
        r = by_i[s["i"]]
        if r["action"] == "remove":
            out_segs.append({"t": "s", "i": s["i"], "text": "", "r": r})
            continue
        shown = cite(r["final"], r["witnesses"], r["files"])
        out_segs.append({"t": "s", "i": s["i"], "text": shown, "r": r})
        final.append(shown)
    final_md = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", "".join(final))).strip()
    checked = [r for r in results if r["kind"] == "claim"]
    summary = {
        "sentences": len(results), "checked": len(checked),
        "kept": sum(1 for r in checked if r["action"] == "keep"), "softened": sum(1 for r in checked if r["action"] == "soften"),
        "removed": sum(1 for r in results if r["action"] == "remove"),
        "flagged": sum(1 for r in results if r["action"] == "flag"),
        "uncited": sum(1 for r in results if r["kind"] == "uncited"), "unchecked": sum(1 for r in results if r["kind"] == "unchecked"),
        "gaps": len(GAP.findall(final_md)), "from_file": sum(1 for r in results if r["kind"] == "file"),
    }
    removed = [{"sentence": strip_markers(r["original"]), "witnesses": r["witnesses"], "problem": r["problem"], "why": r["why"]}
               for r in results if r["action"] == "remove"]
    cited = list(dict.fromkeys(w for r in results if r["action"] != "remove" for w in r["witnesses"]))
    return {"segments": out_segs, "final_markdown": final_md, "summary": summary, "removed": removed, "cited": cited}
