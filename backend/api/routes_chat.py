"""
The one chat endpoint: POST /api/chat/stream (vision §2 "Conversation first").

Every ordinary turn goes to the conductor (docs/features/01), which talks, proposes notebook entries
and *offers* heavier work but never starts it. Heavy work (the trial, the systematic review, study
design, the proposal) runs through its own router, each behind its own approval flag.

Two structured turns skip the conductor:
  - ``idea_promotion``: the user explicitly keeps an idea (vision §3.1; one action = one promoted idea).
  - ``approval`` / ``step_accept`` / ``brief_id``: the retired plan-and-pipeline path (archived in
    docs/archive/legacy_code/pipeline_v1/). They get an honest error and start nothing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.agents import sanitize_log_message
from backend.conversation import conductor
from backend.conversation.idea import create_tentative_idea, promote_idea_to_artifact

logger = logging.getLogger("ThothWebServer")
router = APIRouter(tags=["Unified Chat"])

RETIRED_MESSAGE = (
    "That plan-and-approve chat path was retired. Use Check (the trial) or a systematic review; "
    "each shows its plan and asks for approval before anything runs."
)


def _sse(event_name: str, payload: Dict[str, Any]) -> Dict[str, str]:
    """Package a typed card as an SSE 'message' event. Payload is JSON-safe."""
    return {
        "event": "message",
        "data": json.dumps({"event": event_name, "payload": payload}, default=str),
    }


class TurnKind:
    IDEA_PROMOTION = "idea_promotion"
    RETIRED = "retired"
    CONVERSATION = "conversation"


def _classify_turn(body: Dict[str, Any]) -> str:
    """Structured actions first; every other message is a conversation turn for the conductor."""
    if isinstance(body.get("idea_promotion"), dict):
        return TurnKind.IDEA_PROMOTION
    if isinstance(body.get("approval"), dict) or isinstance(body.get("step_accept"), dict) or body.get("brief_id"):
        return TurnKind.RETIRED
    return TurnKind.CONVERSATION


@router.post("/api/chat/stream")
async def chat_stream(request: Request):
    """One SSE endpoint for the whole conversation.

    Body: ``message``, ``session_id``, ``project_id``, ``chat_turns``, ``research_file``,
    ``active_thinker`` (conversation turns), or ``idea_promotion`` ``{title, hypothesis, rationale}``.
    Streams typed cards: ``direct_answer``, ``quick_look_result``, ``notebook_proposal``,
    ``thinker_suggestion``, ``step_offer``, ``idea_promoted``, ``error``, ``complete``.
    """
    body = await request.json()
    kind = _classify_turn(body)
    logger.info("[chat/stream] turn_kind=%s message=%r", kind, (body.get("message") or "")[:80])

    async def event_generator():
        try:
            if kind == TurnKind.IDEA_PROMOTION:
                async for ev in _run_idea_promotion(body):
                    yield ev
            elif kind == TurnKind.RETIRED:
                yield _sse("error", {"error": RETIRED_MESSAGE, "retired": True})
                yield _sse("complete", {"kind": kind})
            else:
                async for name, payload in conductor.run_conductor_turn(body):
                    yield _sse(name, payload)
        except Exception as exc:
            logger.exception("[chat/stream] unhandled error")
            yield _sse("error", {"error": sanitize_log_message(str(exc))})
            yield _sse("complete", {"kind": kind})

    return EventSourceResponse(event_generator())




@router.post("/api/chat/proposals/{proposal_id}")
async def resolve_proposal(proposal_id: str, request: Request):
    """Accept, edit or dismiss something the conductor proposed (docs/features/02):
    notebook proposals, step offers and thinker suggestions."""
    from fastapi import HTTPException
    body = await request.json()
    try:
        return conductor.resolve(proposal_id, body.get("action") or "", body.get("value"))
    except KeyError:
        raise HTTPException(status_code=404, detail="proposal not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid action or value: {exc}")


async def _run_idea_promotion(body: Dict[str, Any]):
    """User-approved promotion of a detector candidate. Vision §3.1:
    promotion is the point of persistence. Create a tentative idea and
    immediately promote it (one explicit user action = one atomic
    tentative→promoted lifecycle).
    """
    promo = body.get("idea_promotion") or {}
    title = (promo.get("title") or "").strip()
    hypothesis = (promo.get("hypothesis") or "").strip()
    rationale = (promo.get("rationale") or "").strip()
    thinker_id = promo.get("thinker_id")

    yield _sse("turn_start", {"kind": TurnKind.IDEA_PROMOTION})

    if not title or not hypothesis:
        yield _sse("error", {"error": "idea_promotion requires 'title' and 'hypothesis'"})
        yield _sse("complete", {"kind": TurnKind.IDEA_PROMOTION})
        return

    try:
        idea = create_tentative_idea(
            title=title,
            hypothesis=hypothesis,
            description=rationale,
            session_id=body.get("session_id") or "",
            thinker_id=thinker_id,
        )
    except Exception as exc:
        logger.error("[chat/idea_promotion] create_tentative failed: %s", sanitize_log_message(str(exc)))
        yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": TurnKind.IDEA_PROMOTION})
        return

    ok, promoted, msg = promote_idea_to_artifact(idea.idea_id, user_approved=True)
    if not ok or promoted is None:
        yield _sse("error", {"error": msg})
        yield _sse("complete", {"kind": TurnKind.IDEA_PROMOTION})
        return

    yield _sse(
        "idea_promoted",
        {
            "idea": promoted.to_dict(),
            "message": "Added to your idea network.",
        },
    )
    yield _sse("complete", {"kind": TurnKind.IDEA_PROMOTION})
