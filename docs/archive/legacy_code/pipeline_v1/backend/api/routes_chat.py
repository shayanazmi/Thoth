"""
Thoth Unified Conversational Entrypoint — Phase 1.

Realises `THOTH.docx` §2 "Conversation first" and §10 "User experience and
interaction rules" by collapsing every mode into a single server-classified
turn routed through one SSE endpoint:

    POST /api/chat/stream

The user never picks "Fast Chat" / "Deep Research" / "Brainstorm". The
server infers depth from the exchange and emits typed cards the frontend
renders. The chat input must stay live at all times — preparation
(brief synthesis) is non-blocking.

Design notes
------------
- No new state table and no replacement of existing primitives. We compose
  `is_casual_query`, `evaluate_clarification_need`, `synthesize_research_mandate`,
  `prepare_research_brief`, `approve_research_brief`, `verify_brief_approval`,
  `direct_chat_chain`, and `stream_research_pipeline` as they stand today.
- The `fast_chat` and `deep_research` "modes" the old routes carried do not
  cross this boundary. If the message is casual we chat; if it names a
  real research question we prepare a brief; if an approval is attached
  we launch. There is no backdoor.
- Thinker invocation inside the pipeline is Phase 4. This phase keeps the
  shape intact so Phase 4 can slot in without a router change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.agents import (
    direct_chat_chain,
    strip_chain_of_thought,
    sanitize_log_message,
)
from backend.conversation import (
    BriefApprovalStatus,
    approve_research_brief,
    detect_escalation_intent,
    evaluate_clarification_need,
    get_research_brief,
    prepare_research_brief,
    synthesize_research_mandate,
    update_research_brief,
    verify_brief_approval,
    task_manager,
    EscalationState,
)
from backend.orchestrator import stream_research_pipeline
from backend.conversation import conductor
from backend.api.routes_research import is_casual_query
from backend.conversation.idea_detector import (
    detect_promising_direction,
    IdeaCandidate,
)
from backend.conversation.idea import (
    create_tentative_idea,
    promote_idea_to_artifact,
)

logger = logging.getLogger("ThothWebServer")
router = APIRouter(tags=["Unified Chat"])


# -----------------------------------------------------------------------------
# Event helpers
# -----------------------------------------------------------------------------

def _sse(event_name: str, payload: Dict[str, Any]) -> Dict[str, str]:
    """Package a typed card as an SSE 'message' event. Payload is JSON-safe."""
    return {
        "event": "message",
        "data": json.dumps({"event": event_name, "payload": payload}, default=str),
    }


# -----------------------------------------------------------------------------
# Classification — a single server-side decision per turn.
# -----------------------------------------------------------------------------

class TurnKind:
    APPROVAL_RESPONSE = "approval_response"
    CASUAL = "casual"
    CLARIFICATION_NEEDED = "clarification_needed"
    APPROVED_RESEARCH = "approved_research"
    RESEARCH_INTENT = "research_intent"
    IDEA_PROMOTION = "idea_promotion"  # Phase 2: user explicitly approves an idea candidate
    FORMAL_REVIEW_REQUEST = "formal_review_request"  # Phase 3: escalate a brief to formal PRISMA
    CONVERSATION = "conversation"  # docs/features/01: the conductor handles ordinary turns
    STEP_ACCEPTED = "step_accepted"  # the user accepted a conductor offer → brief + approval gate


# An explicit request ("run a formal review"), not a mere mention ("what does PRISMA stand for?").
_FORMAL_REVIEW_RE = re.compile(
    r"\b(run|do|start|launch|begin|proceed with|go (?:for|with|ahead with)|want|need|let'?s do)\b"
    r"[^?]{0,40}?\b(formal|systematic|prisma|proper|full)\b[^?]{0,20}?\breview\b",
    re.I,
)


def _cost_estimate(review_mode: str) -> Dict[str, Any]:
    """Rough effort shown before approval (vision §10: explain the added effort)."""
    if review_mode == "formal":
        from backend.intellectual_rigour.lightweight_scan import FORMAL_REVIEW_EFFORT
        return {"review_mode": "formal", **FORMAL_REVIEW_EFFORT}
    return {
        "review_mode": "scan",
        "papers_considered": "up to 20 papers (titles + abstracts only)",
        "full_text_attempts": "none",
        "llm_calls": "~4-8",
        "typical_duration": "1-4 minutes",
    }


def _classify_turn(body: Dict[str, Any]) -> str:
    """Decide what kind of turn this is. No modes, no client flags.

    Structured actions are routed directly; every other message goes to the
    conductor (docs/features/01), which talks, proposes and offers but never
    starts heavy work itself.

    Precedence (highest first):
      1. ``idea_promotion`` block attached → IDEA_PROMOTION
      2. ``approval`` block attached       → APPROVAL_RESPONSE
      3. ``step_accept`` block attached    → STEP_ACCEPTED (prepare a brief for approval)
      4. explicit formal-review request on a brief → FORMAL_REVIEW_REQUEST
      5. ``brief_id`` already approved     → APPROVED_RESEARCH
      6. otherwise                         → CONVERSATION
    """
    if isinstance(body.get("idea_promotion"), dict):
        return TurnKind.IDEA_PROMOTION
    if isinstance(body.get("approval"), dict):
        return TurnKind.APPROVAL_RESPONSE
    if isinstance(body.get("step_accept"), dict):
        return TurnKind.STEP_ACCEPTED

    brief_id = body.get("brief_id")
    if brief_id and _FORMAL_REVIEW_RE.search(body.get("message") or ""):
        return TurnKind.FORMAL_REVIEW_REQUEST
    if brief_id:
        try:
            existing = get_research_brief(brief_id)
            if existing and existing.is_approved():
                return TurnKind.APPROVED_RESEARCH
        except Exception:
            # fall through — not fatal
            pass

    return TurnKind.CONVERSATION


# -----------------------------------------------------------------------------
# Branches
# -----------------------------------------------------------------------------

async def _run_casual(message: str, loop: asyncio.AbstractEventLoop):
    """Direct conversational reply. Fail-open with a graceful stock answer."""
    yield _sse("turn_start", {"kind": TurnKind.CASUAL, "message": message})
    is_fallback = False
    try:
        raw = await loop.run_in_executor(None, lambda: direct_chat_chain.invoke({"user_query": message}))
        clean = strip_chain_of_thought(raw)
    except Exception as exc:
        is_fallback = True
        clean = (
            "I am at your service. How may I assist your research? "
            "You can describe an observation, ask a question, or just think out loud."
        )
        logger.error(
            "[chat/casual] direct chat failed: %s",
            sanitize_log_message(str(exc)),
        )
    yield _sse(
        "direct_answer",
        {"answer": clean, "fallback": is_fallback, "degraded": is_fallback},
    )
    yield _sse("complete", {"kind": TurnKind.CASUAL})


async def _run_clarification(message: str, body: Dict[str, Any]):
    """Thoth needs one more thing before preparing a plan. Not blocking."""
    try:
        clar = evaluate_clarification_need(
            user_message=message,
            chat_turns=body.get("chat_turns") or [],
            conversation_summary=body.get("conversation_summary", "") or "",
        )
        options = list(getattr(clar, "suggested_angles", []) or [])
        prompt = getattr(clar, "clarification_prompt", "") or (
            "Could you say a bit more about what you'd like to explore?"
        )
    except Exception as exc:
        options = []
        prompt = "Could you say a bit more about what you'd like to explore?"
        logger.warning("[chat/clarification] clarifier failed: %s", sanitize_log_message(str(exc)))
    yield _sse("turn_start", {"kind": TurnKind.CLARIFICATION_NEEDED, "message": message})
    yield _sse(
        "clarification_needed",
        {"prompt": prompt, "options": options},
    )
    yield _sse("complete", {"kind": TurnKind.CLARIFICATION_NEEDED})


async def _run_research_intent(message: str, body: Dict[str, Any]):
    """A research direction appears to be forming. Prepare a plan,
    emit it as a pending card, and return. Vision §3 stage 3: preparation
    is non-blocking. The client is free to keep chatting; a later turn
    with an ``approval`` block kicks off the pipeline."""
    session_id = body.get("session_id") or body.get("sessionId") or ""
    chat_turns: List[Dict[str, Any]] = body.get("chat_turns") or []
    summary: str = body.get("conversation_summary", "") or ""

    # Combine the current message into the mandate inputs so the brief
    # reflects what the user just said.
    accumulated_turns = list(chat_turns) + [{"user": message, "assistant": ""}]

    yield _sse("turn_start", {"kind": TurnKind.RESEARCH_INTENT, "message": message})

    # Phase 2 (vision §3.1): detect, suggest, but DO NOT persist. An idea
    # candidate is a non-blocking suggestion. The research-plan path still
    # runs; the user can promote the idea separately or at the same time.
    try:
        candidate = detect_promising_direction(
            message,
            chat_history=chat_turns,
            conversation_summary=summary,
            use_llm=False,  # heuristic for speed; LLM-assisted path reserved for a dedicated review
        )
    except Exception as exc:
        logger.info("[chat/research_intent] detector failed silently: %s", sanitize_log_message(str(exc)))
        candidate = None
    if candidate is not None:
        yield _sse(
            "idea_candidate",
            {
                "candidate": candidate.to_dict(),
                "guidance": (
                    "This looks like a research direction worth capturing. "
                    "I haven't saved it — approve to add it to the idea network, "
                    "or ignore it and keep chatting."
                ),
                "requires_approval": True,
            },
        )

    yield _sse(
        "plan_preparing",
        {"note": "I'm sketching a focused research plan — the chat stays live while I do."},
    )

    try:
        thinker_ctx = body.get("thinker_context") or {}
        brief = prepare_research_brief(
            topic=message,
            chat_turns=accumulated_turns,
            conversation_summary=summary,
            session_id=session_id,
            thinker_id=thinker_ctx.get("thinker_id") if isinstance(thinker_ctx, dict) else None,
            unresolved_questions=body.get("unresolved_questions"),
            idea_id=body.get("idea_id"),
        )
    except Exception as exc:
        logger.error("[chat/research_intent] brief prep failed: %s", sanitize_log_message(str(exc)))
        yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": TurnKind.RESEARCH_INTENT})
        return

    yield _sse(
        "plan_pending",
        {
            "brief": brief.to_dict(),
            "requires_approval": True,
            "cost_estimate": _cost_estimate(brief.review_mode),
            "guidance": (
                "Here's the plan I'd follow (a lightweight literature scan to start). Review it, edit it, or approve it when you're ready. "
                "You can keep chatting — this won't lock the conversation."
            ),
        },
    )
    yield _sse("complete", {"kind": TurnKind.RESEARCH_INTENT})


async def _run_step_accepted(body: Dict[str, Any]):
    """The user accepted a conductor offer (or pressed Check / Review). Prepare the
    brief exactly as before and emit plan_pending; nothing runs until approval."""
    step_info = body.get("step_accept") or {}
    step = step_info.get("step") or "scan"
    topic = (step_info.get("topic") or body.get("message") or "").strip()
    if step_info.get("proposal_id"):
        try:
            conductor.resolve(step_info["proposal_id"], "accept")
        except Exception:
            pass
    if not topic:
        yield _sse("error", {"error": "step_accept needs a topic (the question or hypothesis to research)"})
        yield _sse("complete", {"kind": TurnKind.STEP_ACCEPTED})
        return
    brief_payload = None
    async for ev in _run_research_intent(topic, body):
        data = json.loads(ev["data"])
        if data.get("event") == "plan_pending" and step == "systematic_review":
            brief_payload = data["payload"]["brief"]
            continue
        if data.get("event") == "complete" and brief_payload:
            try:
                formal = update_research_brief(brief_payload["brief_id"], {"review_mode": "formal"})
                yield _sse("plan_pending", {
                    "brief": formal.to_dict(),
                    "requires_approval": True,
                    "cost_estimate": _cost_estimate("formal"),
                    "guidance": "Here's the systematic review plan. It costs noticeably more than a scan; approve this version to start it.",
                })
            except Exception as exc:
                yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield ev


async def _run_approval_response(body: Dict[str, Any]):
    """The user approved (or edited) a plan. Mark it APPROVED, hand off to
    the pipeline, and stream its events as the frontend expects."""
    appr = body.get("approval") or {}
    brief_id = appr.get("brief_id") or body.get("brief_id")
    if not brief_id:
        yield _sse("error", {"error": "approval missing brief_id"})
        yield _sse("complete", {"kind": TurnKind.APPROVAL_RESPONSE})
        return

    expected_version = appr.get("approved_version") or appr.get("version")
    yield _sse("turn_start", {"kind": TurnKind.APPROVAL_RESPONSE, "brief_id": brief_id})

    # Optional edits before approval. Vision §3.2: edits mutate the brief
    # and auto-invalidate prior approvals (handled by update_research_brief).
    edits = appr.get("edits")
    if isinstance(edits, dict) and edits:
        try:
            updated = update_research_brief(brief_id, edits)
            expected_version = updated.version
            yield _sse("brief_updated", {"brief": updated.to_dict()})
        except Exception as exc:
            logger.error("[chat/approval] brief update failed: %s", sanitize_log_message(str(exc)))
            yield _sse("error", {"error": sanitize_log_message(str(exc))})
            yield _sse("complete", {"kind": TurnKind.APPROVAL_RESPONSE})
            return

    try:
        ok, approved, msg = approve_research_brief(brief_id, int(expected_version))
    except Exception as exc:
        logger.error("[chat/approval] approve failed: %s", sanitize_log_message(str(exc)))
        yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": TurnKind.APPROVAL_RESPONSE})
        return
    if not ok or approved is None:
        yield _sse("approval_rejected", {"reason": msg})
        yield _sse("complete", {"kind": TurnKind.APPROVAL_RESPONSE})
        return

    yield _sse(
        "approval_recorded",
        {"brief_id": approved.brief_id, "approved_version": approved.approved_version, "message": msg},
    )

    # Launch the pipeline. Phase 3 will replace the unconditional PRISMA
    # inside the orchestrator with scan-first; the router shape stays the same.
    async for event in _run_pipeline(approved, body):
        yield event




async def _run_formal_review_request(body: Dict[str, Any]):
    """Vision §5.4: escalate an existing brief to a formal PRISMA-aligned review.
    Changing review_mode bumps the brief version, which invalidates any earlier
    approval — so the formal review needs its own explicit approval."""
    brief_id = body.get("brief_id")
    yield _sse("turn_start", {"kind": TurnKind.FORMAL_REVIEW_REQUEST, "brief_id": brief_id})
    try:
        brief = update_research_brief(brief_id, {"review_mode": "formal"})
    except Exception as exc:
        yield _sse("error", {"error": sanitize_log_message(str(exc))})
        yield _sse("complete", {"kind": TurnKind.FORMAL_REVIEW_REQUEST})
        return
    yield _sse(
        "plan_pending",
        {
            "brief": brief.to_dict(),
            "requires_approval": True,
            "cost_estimate": _cost_estimate("formal"),
            "guidance": (
                "Here's the formal review plan: PRISMA-aligned search, screening and exclusion records, "
                "citation snowballing and full-text attempts. It costs noticeably more than the scan — "
                "approve this version to start it."
            ),
        },
    )
    yield _sse("complete", {"kind": TurnKind.FORMAL_REVIEW_REQUEST})


async def _run_idea_promotion(body: Dict[str, Any]):
    """User-approved promotion of a detector candidate. Vision §3.1:
    promotion is the point of persistence. Create a tentative idea and
    immediately promote it (one explicit user action = one atomic
    tentative→promoted lifecycle). Edges to other ideas are deferred to
    Phase 3+ where they can be grounded on evidence rather than text
    similarity.
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


async def _run_pipeline(brief_obj, body: Dict[str, Any]):
    """Stream the orchestrator's FSM output through this endpoint's SSE
    envelope. Mirrors routes_research.py's register-task + claim + complete
    lifecycle so the chat router participates in the same durable task layer.
    """
    import os
    import threading
    import time
    loop = asyncio.get_running_loop()

    # Task lifecycle: atomic reservation + cooperative cancellation.
    task_id = f"task_{brief_obj.brief_id}_{int(time.time() * 1000)}"
    can_run, cancel_event, task_msg = task_manager.register_task(
        task_id=task_id,
        brief_id=brief_obj.brief_id,
        version=brief_obj.version,
    )
    if not can_run:
        yield _sse("duplicate_execution_rejected", {"error": task_msg})
        yield _sse("complete", {"task_id": task_id})
        return

    yield _sse(
        "approval_verified",
        {
            "task_id": task_id,
            "brief_id": brief_obj.brief_id,
            "version": brief_obj.version,
            "approved_at": brief_obj.approved_at,
            "message": f"Launching research with approved brief (v{brief_obj.version}).",
        },
    )

    queue: asyncio.Queue = asyncio.Queue()

    def _worker():
        try:
            worker_id = f"chat-worker_{os.getpid()}_{threading.get_ident()}"
            claimed, _claimed_task, claim_msg = task_manager.claim_task(task_id, worker_id=worker_id)
            if not claimed:
                asyncio.run_coroutine_threadsafe(
                    queue.put(("error", {"error": claim_msg}, {})), loop,
                )
                return

            was_cancelled = False
            for item in stream_research_pipeline(
                topic=brief_obj.topic or body.get("message", ""),
                role=body.get("role", "senior academic researcher"),
                tone=body.get("tone", "formal and analytical"),
                scrape_top_n=int(body.get("scrape_top_n", 15)),
                min_score=float(body.get("min_score", 6.5)),
                initial_turns=body.get("chat_turns") or [],
                initial_summary=body.get("conversation_summary", "") or "",
                cancel_event=cancel_event,
                brief=brief_obj.to_dict(),
                project_id=body.get("project_id"),
                session_id=body.get("session_id") or brief_obj.session_id,
            ):
                if isinstance(item, (tuple, list)) and len(item) == 3:
                    node_name, update, _state = item
                elif isinstance(item, dict):
                    node_name = item.get("node", "")
                    update = item.get("update", {})
                else:
                    continue
                asyncio.run_coroutine_threadsafe(
                    queue.put((node_name, update if isinstance(update, dict) else {}, {})),
                    loop,
                )
                if node_name == "cancelled":
                    was_cancelled = True

            if was_cancelled:
                task_manager.record_cancellation(task_id)
            else:
                task_manager.complete_task(task_id, "COMPLETED")
        except Exception as exc:
            clean = sanitize_log_message(str(exc))
            logger.error("[chat/pipeline] worker exception: %s", clean)
            try:
                task_manager.complete_task(task_id, "FAILED", error_code="WORKER_EXCEPTION", error_summary=clean)
            except Exception:
                pass
            asyncio.run_coroutine_threadsafe(
                queue.put(("error", {"error": clean}, {})), loop,
            )
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    while True:
        item = await queue.get()
        if item is None:
            # Pipeline finished — emit the terminating card.
            yield _sse("complete", {"task_id": task_id})
            break
        node_name, update, _state = item
        yield _sse(node_name or "pipeline_update", update)


# -----------------------------------------------------------------------------
# Public endpoint
# -----------------------------------------------------------------------------

@router.post("/api/chat/stream")
async def chat_stream(request: Request):
    """One SSE endpoint for the whole conversation.

    Request body (all fields optional unless noted):
      - ``message`` (str, required for new turns)
      - ``session_id`` (str) — identifies the chat thread
      - ``chat_turns`` (list[dict]) — prior turns, same shape as the
        existing routes
      - ``conversation_summary`` (str)
      - ``brief_id`` (str) — attach to an in-flight plan
      - ``approval`` (dict) — ``{brief_id, approved_version, edits?}`` to
        launch a plan the user approved

    The response is an SSE stream of typed cards:
      ``turn_start``, ``direct_answer``, ``clarification_needed``,
      ``plan_preparing``, ``plan_pending``, ``brief_updated``,
      ``approval_recorded``, pipeline FSM events (``approval_verified``,
      ``search``, ``scrape``, ``writer``, ``truth_guard``, …), ``error``,
      ``complete``.
    """
    body = await request.json()
    message = (body.get("message") or body.get("topic") or "").strip()
    kind = _classify_turn(body)
    logger.info("[chat/stream] turn_kind=%s message=%r", kind, message[:80])

    async def event_generator():
        loop = asyncio.get_running_loop()
        try:
            if kind == TurnKind.IDEA_PROMOTION:
                async for ev in _run_idea_promotion(body):
                    yield ev
            elif kind == TurnKind.FORMAL_REVIEW_REQUEST:
                async for ev in _run_formal_review_request(body):
                    yield ev
            elif kind == TurnKind.APPROVAL_RESPONSE:
                async for ev in _run_approval_response(body):
                    yield ev
            elif kind == TurnKind.APPROVED_RESEARCH:
                brief_id = body.get("brief_id")
                existing = get_research_brief(brief_id) if brief_id else None
                if not existing or not existing.is_approved():
                    yield _sse("error", {"error": "approved brief not found or no longer approved"})
                    yield _sse("complete", {"kind": kind})
                else:
                    async for ev in _run_pipeline(existing, body):
                        yield ev
            elif kind == TurnKind.STEP_ACCEPTED:
                async for ev in _run_step_accepted(body):
                    yield ev
            else:  # CONVERSATION
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
