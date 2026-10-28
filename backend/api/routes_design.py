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
    return {"resources": _section(project_id, "resources"), "candidates": _section(project_id, "design_candidates"),
            "chosen": _section(project_id, "design")}


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
    version = notebook.write_section(thread, "design", json.dumps(chosen), author)
    return {**chosen, "version": version, "author": author}


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

