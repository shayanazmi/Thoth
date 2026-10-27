"""Hypothesis strength markers (docs/features/04-hypothesis.md § Where I pushed back).

Four markers on the hypothesis card. Named constructs are the entry bar for a trial; a missing direction and
comparison, population and scope, or falsifier is a visible weakness, not a blocker. Guardrail in code: a marker
counts only if the words it quotes are in the hypothesis, so the model cannot credit the researcher with a
falsifier (or a construct) they never stated. With no model, the markers are "not checked" and block nothing.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from backend.research.llm import call_json

PROMPT = """ROLE
You read ONE research hypothesis and report its strength markers, quoting the hypothesis itself.

METHOD
1. Constructs: the things that vary or are compared (e.g. "night-shift work", "emotional exhaustion").
   For each, give a short name and the exact words of the hypothesis that name it. Include a construct only
   if a study could measure it; placeholders such as "things", "it" or "people" are not constructs.
2. Direction and comparison: does it say which way the relationship goes and against what ("higher than
   day-shift nurses")? Quote those words, or null.
3. Population and scope: does it say who, where or when ("hospital RNs in the EU, 2010-2025")? Quote, or null.
   One word naming the population ("nurses") is not enough: scope narrows it (which nurses, where, when).
4. Falsifier: does it say what result would show it wrong ("no difference after controlling for workload")?
   Quote, or null.

OUTPUT (JSON)
{"constructs": [{"name": str, "quote": str}], "direction_comparison": {"quote": str} | null,
 "population_scope": {"quote": str} | null, "falsifier": {"quote": str} | null}

RULES
- Quote the hypothesis exactly. Never supply a marker the hypothesis does not state, however obvious it seems.
- A population word inside a construct ("nurses") is not a scope; scope narrows who, where or when."""

RULES_VERSION = 4
# Placeholders a model may offer as "constructs" (seen live: "things" in "Things just get worse at night").
VAGUE = {"thing", "things", "stuff", "it", "this", "that", "everything", "something", "people", "life", "situation", "issues", "problems"}
MIN_CONSTRUCTS = 2  # a hypothesis relates something to something  # bump when enforce() changes, so markers cached under older rules are recomputed

OPTIONAL = (("direction_comparison", "direction or comparison missing"), ("population_scope", "population or scope missing"),
            ("falsifier", "falsifier missing"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _quoted(quote: Any, text: str) -> Optional[str]:
    q = str((quote or {}).get("quote") if isinstance(quote, dict) else quote or "").strip()
    return q if q and _norm(q) and _norm(q) in _norm(text) else None


_FILLER = {"the", "a", "an", "of", "in", "on", "at", "and", "or", "who", "with", "than", "for", "to"}


def _adds_scope(quote: str, constructs: list, direction: Optional[str]) -> bool:
    """A scope narrows who, where or when. Seen live: the model offered "nurses" and "Night-shift nurses", which
    only repeat a construct and the comparison. It must be more than one word and add a word of its own."""
    words = set(_norm(quote).split()) - _FILLER
    seen = set(_norm(" ".join([c["quote"] for c in constructs] + [direction or ""])).split())
    return len(_norm(quote).split()) >= 2 and bool(words - seen)


def enforce(raw: Any, text: str) -> Dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("constructs"), list):
        return unchecked()
    constructs: list = []
    for c in raw["constructs"]:
        name = str(c.get("name") or c.get("quote") or "").strip() if isinstance(c, dict) else ""
        if name.lower() in VAGUE or _norm(_quoted(c, text) or "") in VAGUE:
            continue
        if name and _quoted(c, text) and name.lower() not in {x["name"].lower() for x in constructs}:
            constructs.append({"name": name, "quote": _quoted(c, text)})
    out: Dict[str, Any] = {"checked": True, "constructs": constructs, "checked_by": str(raw.get("_served_by") or ""), "rules": RULES_VERSION}
    for key, _ in OPTIONAL:
        q = _quoted(raw.get(key), text)
        if key == "population_scope" and q and not _adds_scope(q, constructs, out.get("direction_comparison", {}).get("quote")):
            q = None
        out[key] = {"present": bool(q), "quote": q}
    out["weaknesses"] = (["named constructs missing"] if len(constructs) < MIN_CONSTRUCTS else []) + [label for key, label in OPTIONAL if not out[key]["present"]]
    out["can_go_on_trial"] = len(constructs) >= MIN_CONSTRUCTS
    return out


def unchecked() -> Dict[str, Any]:
    return {"checked": False, "constructs": [], "weaknesses": [], "can_go_on_trial": True,
            **{key: {"present": None, "quote": None} for key, _ in OPTIONAL}}


async def markers(text: str) -> Dict[str, Any]:
    try:
        raw = await call_json("analyst", PROMPT, f"<hypothesis>{text}</hypothesis>", default=None)
    except Exception:
        return unchecked()
    return enforce(raw, text)
