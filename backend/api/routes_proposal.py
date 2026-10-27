"""The research proposal (docs/features/08-writing.md).

GET   /api/proposal?project_id=                    outline, sections, status, references
POST  /api/proposal/outline                        Writer tailors the outline + estimate; nothing heavy runs
PUT   /api/proposal/outline                        the researcher's reordered / edited outline
POST  /api/proposal/write                          SSE; requires {"approve": true}: sections → Verifier → Reviewer loops
PUT   /api/proposal/sections/{key}                 the researcher's own edit of a section (kept; needs re-verifying)
POST  /api/proposal/sections/{key}/regenerate      rewrite one section (409 if it has your edits, unless overwrite)
POST  /api/proposal/sections/{key}/verify          run the Verifier on the section as it stands
POST  /api/proposal/review                         run the Reviewer again (with its bounded revision loops)
POST  /api/proposal/review/stream                  the same, as SSE (revision rounds show live)
POST  /api/proposal/thinkers                       independent thinker reviews of the whole proposal
POST  /api/proposal/concerns/{concern_id}/answer   the researcher's reply to a thinker's concern
POST  /api/proposal/export                         Markdown download; requires {"approve": true}; provisional is watermarked
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.agents import sanitize_log_message
from backend.research import proposal, verifier, writer

router = APIRouter(prefix="/api/proposal", tags=["Proposal"])


def _sse(name: str, payload: Dict[str, Any]) -> Dict[str, str]:
    return {"event": "message", "data": json.dumps({"event": name, "payload": payload}, default=str)}


async def _body(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


def _thread(body: Dict[str, Any]) -> str:
    return str(body.get("project_id") or "default")


def _state(thread: str) -> Dict[str, Any]:
    rf = writer.research_file(thread)
    meta = proposal.get_meta(thread)
    outline = proposal.outline_of(thread)
    return {"outline": outline, "has_outline": bool(meta.get("outline")), "approved": meta.get("approved"),
            "estimate": proposal.estimate(outline, thread),
            "sections": {s["key"]: s for s in proposal.sections(thread, outline)},
            "review": meta.get("review"), "thinkers": meta.get("thinkers"), "status": proposal.status(thread),
            "references": proposal.references(thread, rf),
            "witnesses": {w["id"]: {"title": w.get("title"), "year": w.get("year"), "access": w.get("access"),
                                    "cite": proposal.author_year(w), "narrative": proposal.narrative(w)} for w in rf["witnesses"]},
            "research_file": {"trial": rf["trial_available"], "witnesses": len(rf["witnesses"]), "design": bool(rf["design"]),
                              "hypothesis": rf["hypothesis"], "question": rf["question"]}}


@router.get("")
async def get_proposal(project_id: str):
    return _state(project_id)


@router.post("/outline")
async def propose_outline(request: Request):
    body = await _body(request)
    thread = _thread(body)
    rf = writer.research_file(thread)
    if not rf["hypothesis"]:
        raise HTTPException(status_code=400, detail="Pin a hypothesis first: a proposal argues for testing a specific claim.")
    out = await writer.propose_outline(rf)
    proposal.update_meta(thread, outline=out["outline"], outlined_by=out["outlined_by"], approved=None)
    return {**_state(thread), "tailored": out["tailored"]}


@router.put("/outline")
async def save_outline(request: Request):
    body = await _body(request)
    thread = _thread(body)
    outline = writer.clean_outline(body.get("outline"))
    if len(outline) < 2:
        raise HTTPException(status_code=400, detail="An outline needs at least one section besides the references.")
    proposal.update_meta(thread, author="user", outline=outline)
    return _state(thread)


@router.post("/write")
async def write(request: Request):
    body = await _body(request)
    if body.get("approve") is not True:
        raise HTTPException(status_code=403, detail="Writing the proposal runs only on the researcher's explicit approval.")
    thread = _thread(body)
    outline = writer.clean_outline(body.get("outline")) if body.get("outline") else proposal.outline_of(thread)
    proposal.update_meta(thread, author="user", outline=outline,
                         approved={"at": time.time(), "estimate": proposal.estimate(outline, thread), "sections": [s["key"] for s in outline]})
    only_missing = body.get("only_missing", True) is not False

    async def events():
        try:
            async for name, payload in proposal.write_all(thread, outline, only_missing):
                yield _sse(name, payload)
        except Exception as exc:
            yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": "proposal"})

    return EventSourceResponse(events())


def _outline_section(thread: str, key: str) -> Dict[str, str]:
    s = next((o for o in proposal.outline_of(thread) if o["key"] == key), None)
    if not s or key == writer.REFERENCES:
        raise HTTPException(status_code=404, detail="no such section in the outline (references are built automatically)")
    return s


@router.put("/sections/{key}")
async def edit_section(key: str, request: Request):
    body = await _body(request)
    thread = _thread(body)
    s = _outline_section(thread, key)
    text = str(body.get("markdown") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="markdown is required")
    prev = proposal.get_section(thread, key) or {}
    return proposal.save_section(thread, {**{k: v for k, v in prev.items() if k != "version"}, "key": key, "title": s["title"],
                                          "draft": text[:40000], "author": "user", "user_edited": True, "verification": None,
                                          "edited_at": time.time()}, "user")


@router.post("/sections/{key}/regenerate")
async def regenerate(key: str, request: Request):
    body = await _body(request)
    thread = _thread(body)
    s = _outline_section(thread, key)
    if not proposal.is_approved(thread):
        raise HTTPException(status_code=403, detail="Approve the outline first; writing runs only on your approval.")
    cur = proposal.get_section(thread, key)
    if cur and cur.get("user_edited") and body.get("overwrite") is not True:
        raise HTTPException(status_code=409, detail="This section has your edits. Regenerating would replace them; confirm to overwrite.")
    outline = proposal.outline_of(thread)
    rf = writer.research_file(thread)
    sec = await proposal.write_and_verify(thread, s, outline, rf, proposal._earlier(thread, outline, key),
                                          instruction=str(body.get("instruction") or ""))
    if not sec:
        return {"degraded": True, "message": "The Writer couldn't be reached; nothing was written in its place.", "status": proposal.status(thread)}
    return {"section": sec, "status": proposal.status(thread), "references": proposal.references(thread, rf)}


@router.post("/sections/{key}/verify")
async def verify(key: str, request: Request):
    body = await _body(request)
    thread = _thread(body)
    s = _outline_section(thread, key)
    cur = proposal.get_section(thread, key)
    if not cur or not (cur.get("draft") or "").strip():
        raise HTTPException(status_code=400, detail="nothing to verify yet")
    rf = writer.research_file(thread)
    ver = await verifier.verify_section(cur["draft"], rf["witnesses"], writer.file_keys(rf))
    sec = proposal.save_section(thread, {**cur, "title": s["title"], "verification": ver}, cur.get("author") or "thoth")
    return {"section": sec, "status": proposal.status(thread), "references": proposal.references(thread, rf)}


@router.post("/review")
async def review(request: Request):
    body = await _body(request)
    thread = _thread(body)
    if not proposal.sections(thread):
        raise HTTPException(status_code=400, detail="write at least one section first")
    events = [{"event": n, "payload": p} async for n, p in proposal.review_loop(thread)]
    return {"events": events, **_state(thread)}


@router.post("/review/stream")
async def review_stream(request: Request):
    """The same as /review, as SSE, so revision rounds show live."""
    body = await _body(request)
    thread = _thread(body)
    if not proposal.sections(thread):
        raise HTTPException(status_code=400, detail="write at least one section first")

    async def events():
        try:
            async for name, payload in proposal.review_loop(thread):
                yield _sse(name, payload)
            yield _sse("status", proposal.status(thread))
        except Exception as exc:
            yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": "proposal_review"})

    return EventSourceResponse(events())


@router.post("/thinkers")
async def thinkers(request: Request):
    body = await _body(request)
    thread = _thread(body)
    if not proposal.sections(thread):
        raise HTTPException(status_code=400, detail="write the proposal first")
    ids = [str(t) for t in body.get("thinker_ids") or []][:4]
    return await proposal.thinker_review(thread, ids or None)


@router.post("/concerns/{concern_id}/answer")
async def answer(concern_id: str, request: Request):
    body = await _body(request)
    thread = _thread(body)
    reply = str(body.get("reply") or "").strip()
    if not reply:
        raise HTTPException(status_code=400, detail="reply is required")
    hit = proposal.answer_concern(thread, concern_id, reply)
    if not hit:
        raise HTTPException(status_code=404, detail="no such concern")
    return {"concern": hit, "status": proposal.status(thread)}


@router.post("/export")
async def export(request: Request):
    body = await _body(request)
    if body.get("approve") is not True:
        raise HTTPException(status_code=403, detail="Nothing is exported without the researcher's explicit approval.")
    fmt = str(body.get("format") or "markdown").lower()
    if fmt not in ("markdown", "md"):
        raise HTTPException(status_code=501, detail="Only Markdown export is available for now.")
    thread = _thread(body)
    if not proposal.sections(thread):
        raise HTTPException(status_code=400, detail="nothing to export yet")
    out = proposal.export_markdown(thread)
    meta = proposal.get_meta(thread)
    proposal.update_meta(thread, author="user", exports=(meta.get("exports") or [])[-9:] + [{"at": time.time(), "status": out["status"], "format": "markdown"}])
    return out
