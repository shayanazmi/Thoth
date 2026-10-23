"""
Thinkers inside the research pipeline (vision §6.3, §6.4).

``invoke_thinker_when_useful`` picks one relevant thinker for the stage and
asks it to review the draft. It is gated: if no framework clearly applies,
nothing runs and the reason is reported. Findings are severity-labelled and
advisory — no thinker gets a veto, and philosophical disagreement alone never
invalidates a report.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Map framework severities onto the vision §6.4 gate.
_SEVERITY = {
    "CRITICAL": "critical",
    "MAJOR": "serious",
    "MODERATE": "substantive",
    "MINOR": "non_critical",
    "INFORMATIONAL": "non_critical",
}


def invoke_thinker_when_useful(stage: str, topic: str, report_text: str, brief: Dict[str, Any]) -> Dict[str, Any]:
    from backend.intellectual_rigour.matcher import _match_by_fast_heuristics
    from backend.intellectual_rigour.registry import get_framework

    query = " ".join([topic] + list(brief.get("hypotheses") or []))
    match = _match_by_fast_heuristics(query) or _causal_fallback(query)
    if match is None:
        return {"stage": stage, "invoked": False, "reason": "No thinker framework clearly applies to this question."}

    payload: Dict[str, Any] = {
        "stage": stage,
        "invoked": True,
        "thinker_id": match.thinker_id,
        "thinker_name": match.name,
        "why_this_thinker": match.rationalization,
        "opening_challenge": match.suggested_opening_spar,
        "findings": [],
    }

    framework = get_framework(match.thinker_id)
    if framework is None or not report_text.strip():
        return payload
    try:
        from backend.intellectual_rigour.models import ReviewRequest
        artifact = framework.review(ReviewRequest(query=f"/{match.thinker_id}"), report_text, topic=topic)
        payload["review_markdown"] = (artifact.formatted_markdown or "")[:4000]
        meta = artifact.metadata or {}
        payload["verdict"] = meta.get("verdict")
        payload["critiques_count"] = meta.get("critiques_count", 0)
        payload["findings"] = _findings(meta)
        # Frameworks report objections without per-item severity in metadata;
        # treat a material objection as substantive (investigate, never veto).
        payload["gate_severity"] = "substantive" if meta.get("has_material_objections") else "non_critical"
    except Exception as exc:  # fail-open: a thinker is a perspective, not a gate
        logger.warning("[thinker_hook] %s review failed: %s", match.thinker_id, exc)
        payload["review_error"] = "The thinker review could not be completed; the report stands without it."
    return payload


_CAUSAL_RE = re.compile(r"\b(why|cause[sd]?|causal|explain[s]?|because|despite|leads? to|drives?)\b", re.I)


def _causal_fallback(query: str):
    """A causal question is exactly where a critique of causal inference adds value (Hume)."""
    from backend.intellectual_rigour.matcher import ARCHETYPE_DEFINITIONS, ThinkerMatchResult

    if not _CAUSAL_RE.search(query or ""):
        return None
    tid = "hume" if "hume" in ARCHETYPE_DEFINITIONS else "popper"
    meta = ARCHETYPE_DEFINITIONS[tid]
    return ThinkerMatchResult(
        thinker_id=tid,
        name=meta["name"],
        tradition=meta["tradition"],
        archetype=meta["archetype"],
        bottleneck_detected="Causal claim: the explanation may confuse correlation with cause.",
        confidence=0.7,
        rationalization=(
            f"Your question asks for a causal explanation. {meta['name']} helps separate observed "
            f"association from causation before the literature is read as proof."
        ),
        suggested_opening_spar=meta["default_opening"],
    )


def _findings(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    raw = metadata.get("critiques") or (metadata.get("thinker_output") or {}).get("critiques") or []
    for c in raw[:5]:
        if not isinstance(c, dict):
            continue
        out.append({
            "severity": _SEVERITY.get(str(c.get("severity", "MODERATE")).upper(), "substantive"),
            "problem": c.get("problem", ""),
            "recommendation": c.get("recommendation", ""),
            "blocking": False,  # vision §6.4: no single thinker has veto authority
        })
    return out
