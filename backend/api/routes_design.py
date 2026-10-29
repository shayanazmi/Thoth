"""Study design (docs/features/07-study-design.md).

GET  /api/design?project_id=     resources, latest candidates, chosen design (versioned)
POST /api/design/resources       remember the researcher's resources for this project
POST /api/design/propose         Designer: 2-3 candidates from the hypothesis, trial lessons and resources
POST /api/design/choose          the researcher picks (and may edit) one; saved as the Design section
POST /api/design/revise          a design-level FATAL from the peer Reviewer: one revised design answering it,
                                 offered first among the candidates (choosing it is still the researcher's call)
"""
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from backend.memory import conversation_store as notebook
from backend.research import designer

router = APIRouter(prefix="/api/design", tags=["Study design"])


def _section(thread: str, kind: str) -> Any:
    sec = notebook.notebook_snapshot(thread).get(kind)
    if not sec:
        return None
    try:
        return {**json.loads(sec["content"]), "version": sec["version"], "author": sec["author"]}
    except Exception:
        return None


@router.get("")
async def get_design(project_id: str):
    chosen = _section(project_id, "design")
    if chosen:
        # Why this version exists (the rationale written with it); kept out of _section so prompts never see it.
        chosen["rationale"] = (notebook.notebook_snapshot(project_id).get("design") or {}).get("rationale") or {}
    return {"resources": _section(project_id, "resources"), "candidates": _section(project_id, "design_candidates"), "chosen": chosen}


@router.post("/resources")
async def save_resources(request: Request):
    body = await request.json()
    thread = str(body.get("project_id") or "default")
    res = {k: str((body.get("resources") or {}).get(k) or "").strip()[:500] for k in designer.RESOURCE_FIELDS}
    version = notebook.write_section(thread, "resources", json.dumps(res), "user")
    return {**res, "version": version}


@router.post("/propose")
async def propose(request: Request):
    body = await request.json()
    thread = str(body.get("project_id") or "default")
    hypothesis = (body.get("hypothesis") or "").strip()
    if not hypothesis:
        raise HTTPException(status_code=400, detail="hypothesis is required")
    resources = body.get("resources") or (_section(thread, "resources") or {})
    resources = {k: str(resources.get(k) or "") for k in designer.RESOURCE_FIELDS}
    if not any(resources.values()):
        raise HTTPException(status_code=400, detail="tell Thoth your resources first (time, access, budget, skills)")
    trial = designer.latest_trial(thread)
    lessons = designer.trial_lessons(trial)
    subclaims = (trial or {}).get("subclaims") or [{"id": 1, "claim": hypothesis}]
    try:
        out = await designer.propose(hypothesis, subclaims, resources, lessons)
    except Exception:
        out = {"designs": [], "recommended": "", "guardrail_notes": [], "lessons_used": lessons["available"]}
    out["degraded"] = not out["designs"]
    out["subclaims"] = subclaims
    if out["designs"]:
        out["version"] = notebook.write_section(thread, "design_candidates", json.dumps(out), "thoth")
    return out


@router.post("/choose")
async def choose(request: Request):
    body = await request.json()
    thread = str(body.get("project_id") or "default")
    cands = _section(thread, "design_candidates")
    idx = body.get("index")
    if not cands or not isinstance(idx, int) or not (0 <= idx < len(cands["designs"])):
        raise HTTPException(status_code=400, detail="choose one of the proposed designs")
    chosen: Dict[str, Any] = dict(cands["designs"][idx])
    edits = (body.get("notes") or "").strip()
    if edits:
        chosen["researcher_notes"] = edits[:4000]
    author = "user" if edits else "thoth_accepted"
    version = notebook.write_section(thread, "design", json.dumps(chosen), author, rationale=_choice_rationale(thread, chosen, cands, edits))
    return {**chosen, "version": version, "author": author,
            "rationale": (notebook.notebook_snapshot(thread).get("design") or {}).get("rationale") or {}}


def _choice_rationale(thread: str, chosen: Dict[str, Any], cands: Dict[str, Any], notes: str) -> Dict[str, Any]:
    """Why this design version exists (vision §3.2, §8.1). A revision names the peer Reviewer's findings it answers,
    so a later review can record that the finding was resolved by this version."""
    if chosen.get("revision_of"):
        from backend.research import proposal
        review = proposal.get_meta(thread).get("review") or {}
        held = {h.get("id"): h for h in review.get("held") or []}
        changes = "; ".join(c.get("change", "") for c in chosen.get("changes") or [] if c.get("change"))
        return {"trigger": "design_revision", "source": "you" if notes else "thoth",
                "reason": (notes or changes or "Revised to answer the peer Reviewer")[:1000],
                "evidence": [{"kind": "reviewer_finding", "ref": {"finding_id": fid, "review_at": review.get("at") or ""},
                              "label": (held.get(fid) or {}).get("problem", "")} for fid in chosen.get("addresses") or []],
                "decision_ref": {"kind": "reviewer_finding", "id": ",".join(chosen.get("addresses") or [])},
                "context": [{"kind": "reviewer_finding", "ref": {"finding_id": u.get("finding_id", "")}, "label": f"Still open: {u.get('why', '')}"}
                            for u in chosen.get("unresolved") or []]}
    ev = [{"kind": "trial_verdict", "ref": {"trial_id": chosen["trial_id"]}, "label": "the trial's lessons were used"}] if chosen.get("trial_id") else []
    return {"trigger": "design_choice", "source": "you" if notes else "thoth",
            "reason": (notes or cands.get("why") or "Chosen as proposed")[:1000], "evidence": ev}


@router.post("/revise")
async def revise(request: Request):
    """Findings default to the proposal review's held design-level FATALs (docs/features/08 → 07)."""
    body = await request.json()
    thread = str(body.get("project_id") or "default")
    chosen = _section(thread, "design")
    findings = body.get("findings")
    if not findings:
        from backend.research import proposal
        held = (proposal.get_meta(thread).get("review") or {}).get("held") or []
        findings = [h for h in held if h.get("fix_in") == "design"]
    if not chosen or not findings:
        raise HTTPException(status_code=400, detail="needs a chosen design and at least one design-level finding to answer")
    stale = [f for f in findings if f.get("design_version") is not None and f["design_version"] != chosen["version"]]
    if stale:
        raise HTTPException(status_code=409, detail=f"These findings were raised against design v{stale[0]['design_version']}; the design is "
                                                    f"now v{chosen['version']}. Run the Reviewer again first.")
    resources = {k: str((_section(thread, "resources") or {}).get(k) or "") for k in designer.RESOURCE_FIELDS}
    trial = designer.trial_for_design(thread, chosen)
    lessons = designer.trial_lessons(trial)
    hypothesis = notebook.notebook_snapshot(thread).get("hypothesis", {}).get("content") or (trial or {}).get("hypothesis", "")
    subclaims = (trial or {}).get("subclaims") or [{"id": 1, "claim": hypothesis}]
    try:
        out = await designer.revise(chosen, findings, hypothesis, subclaims, resources, lessons)
    except Exception:
        out = {"designs": [], "guardrail_notes": []}
    if not out["designs"]:
        return {**out, "degraded": True, "message": "The Designer couldn't be reached; no revision was made up in its place."}
    prev = _section(thread, "design_candidates") or {}
    others = [d for d in prev.get("designs") or [] if d.get("name") != out["designs"][0]["name"]][:3]
    merged = {**prev, "designs": out["designs"] + others, "recommended": out["designs"][0]["name"],
              "why": f"Revised to answer the peer Reviewer: {'; '.join(f.get('problem', '')[:100] for f in findings)}",
              "guardrail_notes": out["guardrail_notes"], "lessons_used": lessons["available"]}
    merged.pop("version", None); merged.pop("author", None)
    merged["version"] = notebook.write_section(thread, "design_candidates", json.dumps(merged), "thoth")
    return merged

