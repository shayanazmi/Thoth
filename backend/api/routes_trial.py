"""The trial and its library (docs/features/05, 06).

POST  /api/trial/plan                    sub-claims + estimate; nothing heavy runs
POST  /api/trial/{id}/run                SSE; requires {"approve": true} on a planned trial (runs once)
GET   /api/trial/{id}                    full state: papers, records, matrix rows, verdict
GET   /api/trial/latest?project_id=      the project's most recent trial
PATCH /api/trial/papers/{paper_id}       the researcher's own "I say" for a row
POST  /api/trial/{id}/papers             add a paper by DOI (read + analysed immediately)
POST  /api/trial/papers/{paper_id}/pdf   "Upload PDF to complete" (base64 body)
POST  /api/trial/{id}/rejudge            weigh the witnesses again after edits or additions (Judge only)
POST  /api/trial/{id}/stop               keep finished rows, mark the rest "not run" (trial becomes "stopped")
POST  /api/trial/{id}/remap              a rival was swapped in: plan a trial of it on the same library (run needs approval)
POST  /api/trial/{id}/subclaims          SSE; requires {"approve": true}: edited sub-claims → every row redone → re-judged
"""
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.agents import sanitize_log_message
from backend.memory import db as _db
from backend.research import store, trial

router = APIRouter(prefix="/api/trial", tags=["Trial"])


def _sse(name: str, payload: Dict[str, Any]) -> Dict[str, str]:
    return {"event": "message", "data": json.dumps({"event": name, "payload": payload}, default=str)}


@router.post("/plan")
async def plan_trial(request: Request):
    body = await request.json()
    hypothesis = (body.get("hypothesis") or "").strip()
    if not hypothesis:
        raise HTTPException(status_code=400, detail="hypothesis is required")
    try:
        return await trial.plan(str(body.get("project_id") or "default"), hypothesis)
    except trial.NotTrialable as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _with_version(t: Dict[str, Any]) -> Dict[str, Any]:
    """Is this verdict about the hypothesis as it stands? (docs/features/04: an old verdict is labelled stale.)"""
    from backend.conversation import projects
    now = projects.current_hypothesis(t["thread_id"])
    version = t.get("hypothesis_version")
    inferred = version is None
    if inferred:  # trials from before versions were recorded: match the text to a version
        version = projects.version_of(t["thread_id"], t["hypothesis"])
    if not now:
        stale = False
    elif version is not None:
        stale = version != now["version"]
    else:
        stale = t["hypothesis"].strip() != now["text"].strip()
    return {**t, "hypothesis_version": version, "version_inferred": inferred and version is not None, "hypothesis_now": now, "stale": stale}


@router.post("/{trial_id}/stop")
async def stop(trial_id: str):
    t = store.get_trial(trial_id)
    if not t:
        raise HTTPException(status_code=404, detail="no such trial")
    if t["status"] != "running":
        raise HTTPException(status_code=409, detail=f"This trial is {t['status']}; only a running trial can be stopped.")
    trial.request_stop(trial_id)
    return {"stopping": True, "trial_id": trial_id}


@router.post("/{trial_id}/remap")
async def remap(trial_id: str, request: Request):
    body = await request.json()
    try:
        return await trial.remap_plan(trial_id, body.get("hypothesis"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/latest")
async def latest_trial(project_id: str):
    conn = _db.get_connection(_db.DEFAULT_DB_PATH)
    _db.init_db(_db.DEFAULT_DB_PATH)
    row = conn.execute("SELECT trial_id FROM trials WHERE thread_id = ? AND status != 'planned' ORDER BY created_at DESC LIMIT 1",
                       (project_id,)).fetchone()
    return _with_version(store.get_trial(row[0])) if row else {"trial_id": None}


@router.get("/{trial_id}")
async def get_trial(trial_id: str):
    t = store.get_trial(trial_id)
    if not t:
        raise HTTPException(status_code=404, detail="no such trial")
    return _with_version(t)


@router.post("/{trial_id}/run")
async def run_trial(trial_id: str, request: Request):
    body = await request.json()
    if body.get("approve") is not True:
        raise HTTPException(status_code=403, detail="A trial runs only on the researcher's explicit approval.")

    async def events():
        try:
            async for name, payload in trial.run(trial_id, body.get("subclaims")):
                yield _sse(name, payload)
        except Exception as exc:
            yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": "trial"})

    return EventSourceResponse(events())


@router.patch("/papers/{paper_id}")
async def edit_i_say(paper_id: str, request: Request):
    body = await request.json()
    if not store.get_paper(paper_id):
        raise HTTPException(status_code=404, detail="no such paper")
    store.update_paper(paper_id, i_say_user=(body.get("i_say") or "").strip() or None)
    return store.get_paper(paper_id)


async def _collect(gen) -> Dict[str, Any]:
    events = [{"event": n, "payload": p} async for n, p in gen]
    return {"events": events}


@router.post("/{trial_id}/papers")
async def add_paper(trial_id: str, request: Request):
    body = await request.json()
    if not store.get_trial(trial_id):
        raise HTTPException(status_code=404, detail="no such trial")
    return await _collect(trial.add_by_doi(trial_id, body.get("doi") or ""))


@router.post("/papers/{paper_id}/pdf")
async def upload_pdf(paper_id: str, request: Request):
    body = await request.json()
    data = body.get("pdf_base64") or ""
    if not data or len(data) > 22_000_000:
        raise HTTPException(status_code=400, detail="pdf_base64 is required (max ~15 MB)")
    return await _collect(trial.complete_with_pdf(paper_id, data))


@router.post("/{trial_id}/subclaims")
async def edit_subclaims(trial_id: str, request: Request):
    body = await request.json()
    if not store.get_trial(trial_id):
        raise HTTPException(status_code=404, detail="no such trial")
    if body.get("approve") is not True:
        raise HTTPException(status_code=403, detail="Re-analysing every row runs only on the researcher's explicit approval.")
    subs = body.get("subclaims")
    if not isinstance(subs, list) or not any(str(s.get("claim") if isinstance(s, dict) else s).strip() for s in subs):
        raise HTTPException(status_code=400, detail="subclaims must list at least one claim")

    async def events():
        try:
            async for name, payload in trial.reanalyse(trial_id, subs):
                yield _sse(name, payload)
        except Exception as exc:
            yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": "trial_reanalysis"})

    return EventSourceResponse(events())


@router.post("/{trial_id}/rejudge")
async def rejudge(trial_id: str):
    if not store.get_trial(trial_id):
        raise HTTPException(status_code=404, detail="no such trial")
    return await trial.rejudge(trial_id)
