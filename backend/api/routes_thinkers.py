"""Thinkers as co-authors (docs/features/03-thinkers.md).

GET  /api/thinkers                     roster
GET  /api/thinkers/{id}/profile        what the user sees when they tap a bust
POST /api/thinkers/{id}/reply          join (main chat) or room (one-on-one)
POST /api/thinkers/review              independent reviews of an artefact
POST /api/thinkers/council             every thinker's first reaction, independently
POST /api/thinkers/debate              SSE: sequential rounds, then Thoth's distillation
"""
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.agents import sanitize_log_message
from backend.thinkers import modes, roster

router = APIRouter(prefix="/api/thinkers", tags=["Thinkers"])


def _thread(body: Dict[str, Any]) -> str:
    return str(body.get("project_id") or body.get("session_id") or "default")


def roster_payload() -> Dict[str, Any]:
    return {"thinkers": [{**t, "territory": roster.territory(t["id"])} for t in roster.ROSTER]}


@router.get("")
async def list_thinkers():
    return roster_payload()


@router.get("/{thinker_id}/profile")
async def thinker_profile(thinker_id: str):
    if roster.get(thinker_id) is None:
        raise HTTPException(status_code=404, detail="not on the roster")
    return roster.profile(thinker_id)


@router.post("/{thinker_id}/reply")
async def thinker_reply(thinker_id: str, request: Request, background: BackgroundTasks):
    body = await request.json()
    mode = body.get("mode") or "join"
    message = (body.get("message") or "").strip()
    if mode not in ("join", "room") or not message:
        raise HTTPException(status_code=400, detail="mode must be join or room, and message is required")
    thread = _thread(body)
    try:
        out = await modes.reply(thread, thinker_id, message, mode)
    except KeyError:
        raise HTTPException(status_code=404, detail="not on the roster")
    exchange = out.pop("exchange", None)
    if exchange:
        background.add_task(modes.update_memory, thread, thinker_id, exchange)
    return out


@router.post("/review")
async def thinker_review(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text (the artefact to review) is required")
    ids = body.get("thinker_ids") or modes.default_reviewers(text)
    reviews = await modes.review(_thread(body), ids, body.get("artifact") or "hypothesis", text)
    return {"artifact": body.get("artifact") or "hypothesis", "reviews": reviews}


@router.post("/council")
async def thinker_council(request: Request):
    body = await request.json()
    idea = (body.get("idea") or body.get("message") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="idea is required")
    takes = await modes.council(_thread(body), idea)
    return {"idea": idea, "council": takes, "degraded": not any(t["take"] for t in takes)}


@router.post("/debate")
async def thinker_debate(request: Request):
    body = await request.json()
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    async def events():
        try:
            async for name, payload in modes.debate(_thread(body), body.get("thinker_ids") or [], question,
                                                    body.get("rounds") or 3, body.get("hypothesis") or ""):
                yield {"event": "message", "data": json.dumps({"event": name, "payload": payload})}
        except Exception as exc:
            yield {"event": "message", "data": json.dumps({"event": "error", "payload": {"error": sanitize_log_message(str(exc))}})}
        yield {"event": "message", "data": json.dumps({"event": "complete", "payload": {"kind": "debate"}})}

    return EventSourceResponse(events())
