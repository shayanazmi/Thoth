"""Why a research-file version exists (vision §3.2, §8.1): the reason, what triggered it, the evidence or decision
behind it, and what was known at the time. Stored write-once with its version (notebook_sections.rationale_json),
never edited later, so the history of a hypothesis or a design can be defended.

`evidence` is what the researcher or Thoth gave as the reason. `context` is attached automatically (e.g. the latest
trial verdict for the previous version) and is shown as "what was known then", never as the motivation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

TRIGGERS = ("initial", "user_edit", "thoth_proposal", "trial_verdict", "review_finding", "thinker_critique",
            "rival_swap", "idea", "design_choice", "design_revision", "unknown")
EVIDENCE_KINDS = ("trial_verdict", "trial_witness", "review_record", "reviewer_finding", "thinker_reply",
                  "conductor_proposal", "citation_neighbour", "question")


def _refs(items: Any, cap: int) -> List[Dict[str, Any]]:
    out = []
    for e in items if isinstance(items, list) else []:
        if not isinstance(e, dict) or e.get("kind") not in EVIDENCE_KINDS:
            continue
        ref = e.get("ref") if isinstance(e.get("ref"), dict) else {}
        out.append({"kind": e["kind"], "label": str(e.get("label") or "")[:200],
                    "ref": {str(k)[:40]: (v if isinstance(v, (int, float)) else str(v)[:120]) for k, v in list(ref.items())[:6]}})
    return out[:cap]


def clean(r: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    r = r if isinstance(r, dict) else {}
    dec = r.get("decision_ref") if isinstance(r.get("decision_ref"), dict) else None
    prev = r.get("previous_version")
    return {
        "reason": str(r.get("reason") or "")[:1000],
        "trigger": r.get("trigger") if r.get("trigger") in TRIGGERS else "unknown",
        "source": str(r.get("source") or "")[:40],
        "evidence": _refs(r.get("evidence"), 10),
        "context": _refs(r.get("context"), 5),
        "decision_ref": {"kind": str(dec.get("kind") or "")[:40], "id": str(dec.get("id") or "")[:120]} if dec else None,
        "previous_version": prev if isinstance(prev, int) else None,
    }
