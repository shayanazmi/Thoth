"""Systematic review (docs/features/05-literature.md tier 3).

POST /api/review/protocol                      draft a protocol (nothing runs)
POST /api/review/{id}/run                      SSE; needs {"approve": true, "mode": "auto"|"copilot", "protocol": edits}
POST /api/review/{id}/decisions/{record_id}    the researcher confirms or overrides {"stage", "decision", "reason"}
POST /api/review/{id}/accept-all               confirm the Screener's remaining decisions for {"stage"}
POST /api/review/{id}/continue                 SSE; resume after screening, after Stop, after a raised budget, or retry after "blocked"
POST /api/review/{id}/stop                     the researcher stops a running review (everything recorded is kept)
POST /api/review/{id}/budget                   more room: {"full_text"?, "citation_records"?, "citation_rounds"?}; then Continue
POST /api/review/estimate                      the estimate for a budget {"budget": {...}} (nothing runs)
GET  /api/review/{id}                          state: protocol, budget, PRISMA counts, stopping rules, limitations, queues, records
GET  /api/review/{id}/searches                 the search record: every request, its query, page, date, totals and errors
GET  /api/review/{id}/records?offset&limit&filter   records, paged (filter: all|included|excluded_ta|excluded_ft|not_screened|duplicates|citation)
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


@router.post("/estimate")
async def estimate(request: Request):
    body = await request.json()
    b = review.clean_budget(body.get("budget") if isinstance(body.get("budget"), dict) else {})
    return {"budget": b, "estimate": review.estimate(b)}


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
    return _stream(review.run(review_id, body.get("mode") or "copilot", body.get("protocol"), body.get("budget")))


@router.post("/{review_id}/stop")
async def stop(review_id: str):
    rev = rs.get(review_id)
    if not rev:
        raise HTTPException(status_code=404, detail="no such review")
    if rev["status"] != "running":
        raise HTTPException(status_code=409, detail=f"This review is {rev['status']}, not running.")
    review.request_stop(review_id)
    return {"stopping": True}


@router.post("/{review_id}/budget")
async def budget(review_id: str, request: Request):
    body = await request.json()
    try:
        return review.raise_budget(review_id, body if isinstance(body, dict) else {})
    except KeyError:
        raise HTTPException(status_code=404, detail="no such review")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/{review_id}/searches")
async def searches(review_id: str):
    if not rs.get(review_id):
        raise HTTPException(status_code=404, detail="no such review")
    return {"searches": rs.searches(review_id)}


@router.get("/{review_id}/records")
async def records(review_id: str, offset: int = 0, limit: int = 50, filter: str = "all"):
    if not rs.get(review_id):
        raise HTTPException(status_code=404, detail="no such review")
    return review.records_page(review_id, offset, limit, filter)


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
