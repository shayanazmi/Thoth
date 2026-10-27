"""Reviewer (docs/features/08-writing.md; prompt in 09 § Reviewer).

A skeptical, fair peer review of the whole proposal: FATAL / MAJOR / MINOR, each quoting the passage it is
about. Guardrails enforced in code:
- a weakness whose passage is not in the proposal is kept but marked unquoted (a FATAL is never dropped);
- each weakness is placed in the section that contains its passage, so a FATAL can be revised there;
- with no model reachable there is no review, and the proposal cannot become "reviewed".
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List

from backend.research.llm import call_json

SEVERITIES = ("FATAL", "MAJOR", "MINOR")

PROMPT = """ROLE
You are Thoth's Reviewer: a skeptical, fair reviewer of a research proposal.

METHOD
1. Read the whole proposal once for its argument: question → gap → hypothesis → design → expected outcomes.
2. Check each link: does the gap follow from the literature review? Can the design test the hypothesis?
   Do the expected outcomes include refutation? Are limitations honest?
3. Classify each problem:
   FATAL = the proposal cannot stand as written (design cannot test the hypothesis; the central claim is
   unsupported; the gap is not real).
   MAJOR = a serious weakness a panel would require fixed.
   MINOR = clarity, polish, small omissions.
4. Keep looking after the first problem.

OUTPUT (JSON)
{"summary": str,
 "strengths": [{"point": str, "passage": str}],
 "weaknesses": [{"id": "R1", "severity": "FATAL"|"MAJOR"|"MINOR", "section": str, "passage": str, "problem": str,
                 "fix": str}],
 "questions": [str], "revision_plan": [str]}

RULES
- Every weakness quotes the exact passage (copy it character for character) and names its section title.
- [GAP: …] markers are known gaps the authors flagged themselves; review whether the proposal can stand with them.
- Do not invent literature; if you suspect missing work, write "check for …".
- No vague praise."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_`>#\[\]]", "", s or "")).strip().lower()


def locate(passage: str, sections: List[Dict[str, str]], named: str = "") -> str:
    """The key of the section whose text contains the passage (or its first 60 characters), else "".
    If several sections contain it, the one the Reviewer named wins."""
    p = _norm(passage)
    if len(p) < 8:
        return ""
    for probe in (p, p[:60]):
        hits = [s["key"] for s in sections if probe and probe in _norm(s["markdown"])]
        if hits:
            return next((s["key"] for s in sections if s["key"] in hits and _norm(s["title"]) == _norm(named)), hits[0])
    return ""


def enforce(raw: Dict[str, Any], sections: List[Dict[str, str]]) -> Dict[str, Any]:
    titles = {_norm(s["title"]): s["key"] for s in sections}
    weaknesses = []
    for n, w in enumerate(raw.get("weaknesses") or [], 1):
        if not isinstance(w, dict) or not str(w.get("problem") or "").strip():
            continue
        sev = str(w.get("severity") or "").upper()
        sev = sev if sev in SEVERITIES else "MAJOR"
        key = locate(str(w.get("passage") or ""), sections, str(w.get("section") or ""))
        quoted = bool(key)
        if not key:
            key = titles.get(_norm(str(w.get("section") or "")), "")
        weaknesses.append({"id": f"R{n}", "severity": sev, "section": key, "passage": str(w.get("passage") or "")[:600],
                           "quoted": quoted, "problem": str(w.get("problem"))[:800], "fix": str(w.get("fix") or "")[:600]})
    counts = {s: sum(1 for w in weaknesses if w["severity"] == s) for s in SEVERITIES}
    return {"summary": str(raw.get("summary") or "")[:1500],
            "strengths": [s for s in raw.get("strengths") or [] if isinstance(s, dict) and s.get("point")][:6],
            "weaknesses": weaknesses, "counts": counts,
            "questions": [str(q) for q in raw.get("questions") or []][:8],
            "revision_plan": [str(q) for q in raw.get("revision_plan") or []][:8],
            "reviewed_by": str(raw.get("_served_by") or "")}


def _usable(raw: Any) -> bool:
    return isinstance(raw, dict) and bool(raw.get("summary") or isinstance(raw.get("weaknesses"), list))


async def review(proposal_md: str, verifier_summary: Dict[str, Any], sections: List[Dict[str, str]],
                 retry_after: float = 20.0) -> Dict[str, Any]:
    human = f"<untrusted>\n{proposal_md}\n</untrusted>\n<verifier_summary>{json.dumps(verifier_summary)}</verifier_summary>"
    raw = None
    # One retry after a pause: on the free tier a failed review is usually a passing rate limit (429), after
    # which the fallback model answered with something that was not a review (seen 25 Oct 2026).
    for attempt in range(2):
        try:
            raw = await call_json("reviewer", PROMPT, human, default=None)
        except Exception:
            raw = None
        if _usable(raw) or attempt:
            break
        await asyncio.sleep(retry_after)
    if not _usable(raw):
        return {"degraded": True}
    return {**enforce(raw, sections), "degraded": False}
