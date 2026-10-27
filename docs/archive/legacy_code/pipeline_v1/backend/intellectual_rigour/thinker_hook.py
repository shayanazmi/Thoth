"""
Thinkers inside the research pipeline (vision §6.3, §6.4; docs/features/03-thinkers.md).

``invoke_thinker_when_useful`` asks ONE relevant co-author to review the report, through the same
dossier-driven engine the user talks to (backend/thinkers). It replaces the old framework auditors
(archived in docs/archive/legacy_code/redesign_v3/). Findings are advisory: no thinker has a veto, and
philosophical disagreement alone never invalidates a report. If no model is reachable, nothing is said
on the thinker's behalf.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_CAUSAL_RE = re.compile(r"\b(why|cause[sd]?|causal|explain[s]?|because|despite|leads? to|drives?|effect of)\b", re.I)
_HEALTH_RE = re.compile(r"\b(nurs\w*|patient\w*|hospital\w*|health|clinic\w*|mortality|disease|care)\b", re.I)


def choose_thinker(query: str) -> Dict[str, str]:
    """A causal question → Hume (association vs cause); a health question → Nightingale (comparisons and
    rates); otherwise Popper (what would show it wrong)."""
    if _CAUSAL_RE.search(query or ""):
        return {"id": "hume", "why": "Your question asks for a causal explanation; Hume separates what was observed from what is being added."}
    if _HEALTH_RE.search(query or ""):
        return {"id": "nightingale", "why": "A health question; Nightingale asks whether like is being compared with like."}
    return {"id": "popper", "why": "Popper asks what result would show the claim wrong."}


def _run(coro):
    """Run a coroutine from sync pipeline code, whether or not this thread has a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: Dict[str, Any] = {}
    t = threading.Thread(target=lambda: box.setdefault("v", asyncio.run(coro)))
    t.start()
    t.join()
    return box.get("v")


def invoke_thinker_when_useful(stage: str, topic: str, report_text: str, brief: Dict[str, Any]) -> Dict[str, Any]:
    from backend.thinkers import modes, roster

    query = " ".join([topic] + list(brief.get("hypotheses") or []))
    pick = choose_thinker(query)
    name = roster.get(pick["id"])["name"]
    payload: Dict[str, Any] = {"stage": stage, "invoked": True, "thinker_id": pick["id"], "thinker_name": name,
                               "why_this_thinker": pick["why"], "findings": []}
    if not (report_text or "").strip():
        return {**payload, "invoked": False, "reason": "There was no report to review."}

    thread = str(brief.get("session_id") or brief.get("brief_id") or "pipeline")
    try:
        review = _run(modes._review_one(thread, pick["id"], "research report", report_text[:14000]))
    except Exception as exc:  # fail-open: a thinker is a perspective, not a gate
        logger.warning("[thinker_hook] %s review failed: %s", pick["id"], exc)
        review = {"degraded": True}
    if not review or review.get("degraded"):
        return {**payload, "invoked": False, "reason": f"{name} couldn't be reached; the report stands without a thinker review."}

    env = review.get("envelope") or {}
    payload["review_markdown"] = review["review"]
    payload["opening_challenge"] = review["review"]
    payload["verdict"] = env.get("verdict")
    payload["findings"] = _findings(env)
    payload["would_change_mind_if"] = env.get("would_change_mind_if", "")
    # Vision §6.4: a critical concern keeps attention on the report until answered; it never vetoes.
    severities = {f["severity"] for f in payload["findings"]}
    payload["gate_severity"] = "critical" if "critical" in severities else ("substantive" if severities & {"serious", "substantive"} else "non_critical")
    return payload


def _findings(envelope: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for c in (envelope.get("concerns") or [])[:5]:
        if isinstance(c, dict):
            out.append({"severity": c.get("severity", "substantive"), "problem": c.get("claim", ""),
                        "why": c.get("why", ""), "blocking": False})
    return out
