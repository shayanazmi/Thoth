"""
Report and claim statuses (vision §8.2, §8.3).

Claim labels: supported | contradicted | uncertain | insufficiently_assessed.
Report status: provisional | fully_reviewed. A report is only
``fully_reviewed`` when the integrity gate passed, no claim is contradicted or
insufficiently assessed, and the review covered more than abstracts.
"""
from __future__ import annotations

from typing import Any, Dict, List

_LABEL = {
    "DIRECTLY_SUPPORTED": "supported",
    "QUALIFIED_SUPPORT": "uncertain",
    "CONTRADICTED": "contradicted",
    "UNSUPPORTED": "uncertain",
    "UNRESOLVED": "insufficiently_assessed",
}


def label_claim(claim: Dict[str, Any]) -> str:
    support = (claim.get("support_status") or "").upper()
    if support == "UNVERIFIABLE":
        return "insufficiently_assessed"
    if support == "CONTRADICTED":
        return "contradicted"
    return _LABEL.get((claim.get("verification_status") or "UNRESOLVED").upper(), "insufficiently_assessed")


def compute_report_status(state: Dict[str, Any]) -> Dict[str, Any]:
    integrity = state.get("integrity_result") or {}
    claims = [
        {"claim": c.get("claim", ""), "label": label_claim(c), "reason": c.get("reason", "")}
        for c in (integrity.get("claims") or [])
        if isinstance(c, dict)
    ]
    counts: Dict[str, int] = {}
    for c in claims:
        counts[c["label"]] = counts.get(c["label"], 0) + 1

    gaps: List[str] = []
    if not state.get("is_verified"):
        gaps.append(f"Integrity gate did not pass ({state.get('integrity_status', 'UNVERIFIED')}).")
    if counts.get("contradicted"):
        gaps.append(f"{counts['contradicted']} claim(s) are contradicted by the sources.")
    if counts.get("insufficiently_assessed"):
        gaps.append(f"{counts['insufficiently_assessed']} claim(s) could not be reliably assessed.")
    if state.get("unresolved_citations"):
        gaps.append(f"{len(state['unresolved_citations'])} citation(s) could not be resolved to a source.")
    if (state.get("brief") or {}).get("review_mode", "scan") != "formal":
        gaps.append("Lightweight scan only (abstract-level); no formal review has been run.")
    if not claims:
        gaps.append("No claims were individually audited.")

    return {
        "report_status": "fully_reviewed" if not gaps else "provisional",
        "claim_counts": counts,
        "claims": claims[:30],
        "gaps": gaps,
        "pdf_export": "Offered only on request — no PDF has been created.",
    }
