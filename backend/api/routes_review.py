"""Systematic review (docs/features/05-literature.md tier 3).

POST /api/review/protocol                      draft a protocol (nothing runs)
POST /api/review/{id}/run                      SSE; needs {"approve": true, "mode": "auto"|"copilot", "protocol": edits}
POST /api/review/{id}/decisions/{record_id}    the researcher confirms or overrides {"stage", "decision", "reason"}
POST /api/review/{id}/accept-all               confirm the Screener's remaining decisions for {"stage"}
POST /api/review/{id}/continue                 SSE; resume after screening, or retry after "blocked"
GET  /api/review/{id}                          state: protocol, PRISMA counts, queues, records
GET  /api/review/latest?project_id=            the project's latest started review
"""
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.agents import sanitize_log_message
from backend.research import review
from backend.research import review_store as rs

router = APIRouter(prefix="/api/review", tags=["Systematic review"])


def _stream(gen):
    async def events():
        try:
            async for name, payload in gen:
                yield {"event": "message", "data": json.dumps({"event": name, "payload": payload}, default=str)}
        except Exception as exc:
            yield {"event": "message", "data": json.dumps({"event": "error", "payload": {"error": sanitize_log_message(str(exc))}})}
        yield {"event": "message", "data": json.dumps({"event": "complete", "payload": {"kind": "review"}})}
    return EventSourceResponse(events())


@router.post("/protocol")
async def protocol(request: Request):
    body = await request.json()
    hyp = (body.get("hypothesis") or "").strip()
    if not hyp:
        raise HTTPException(status_code=400, detail="hypothesis is required")
    return await review.draft_protocol(str(body.get("project_id") or "default"), hyp, (body.get("question") or "").strip())


@router.get("/latest")
async def latest(project_id: str):
    rid = rs.latest(project_id)
    return review.state(rid) if rid else {"review_id": None}


@router.get("/{review_id}")
async def get_review(review_id: str):
    st = review.state(review_id)
    if not st:
        raise HTTPException(status_code=404, detail="no such review")
    return st


@router.post("/{review_id}/run")
async def run(review_id: str, request: Request):
    body = await request.json()
    if body.get("approve") is not True:
        raise HTTPException(status_code=403, detail="A systematic review runs only on the researcher's explicit approval.")
    return _stream(review.run(review_id, body.get("mode") or "copilot", body.get("protocol")))


@router.post("/{review_id}/decisions/{record_id}")
async def decide(review_id: str, record_id: str, request: Request):
    body = await request.json()
    try:
        out = review.decide(record_id, body.get("stage") or "", body.get("decision") or "", body.get("reason") or "")
    except KeyError:
        raise HTTPException(status_code=404, detail="no such record or stage")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**out, "counts": review.prisma_counts(review_id)}


@router.post("/{review_id}/accept-all")
async def accept_all(review_id: str, request: Request):
    body = await request.json()
    n = review.accept_all(review_id, body.get("stage") or "ta")
    return {"accepted": n, "counts": review.prisma_counts(review_id)}


@router.post("/{review_id}/continue")
async def resume(review_id: str):
    return _stream(review.resume(review_id))
