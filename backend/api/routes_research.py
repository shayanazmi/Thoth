import re
import sys
import json
import time
import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends
from sse_starlette.sse import EventSourceResponse

from backend.agents import (
    direct_chat_chain,
    strip_chain_of_thought,
    sanitize_log_message,
)
from backend.orchestrator import stream_research_pipeline
from backend.conversation import (
    synthesize_research_mandate,
    evaluate_clarification_need,
    detect_escalation_intent,
    EscalationState,
    BriefApprovalStatus,
    ResearchBrief,
    prepare_research_brief,
    update_research_brief,
    approve_research_brief,
    get_research_brief,
    verify_brief_approval,
    task_manager,
)

logger = logging.getLogger("ThothWebServer")
router = APIRouter(tags=["Research Pipeline"])

def _get_direct_chat_chain():
    from unittest.mock import Mock
    if isinstance(direct_chat_chain, Mock):
        return direct_chat_chain
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "direct_chat_chain"):
        return ws.direct_chat_chain
    return direct_chat_chain

def _get_stream_research_pipeline():
    from unittest.mock import Mock
    if isinstance(stream_research_pipeline, Mock):
        return stream_research_pipeline
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "stream_research_pipeline"):
        return ws.stream_research_pipeline
    return stream_research_pipeline

def is_casual_query(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False

    raw = text.strip()
    if not raw or raw.startswith("/"):
        return False

    try:
        from backend.intellectual_rigour import resolve_thinker_command
        if resolve_thinker_command(raw) is not None:
            return False
    except ImportError:
        pass

    try:
        esc = detect_escalation_intent(raw)
        if esc.get("state") == EscalationState.RESEARCH_READY:
            return False
    except Exception:
        pass

    clean = re.sub(r"[^\w\s\']", " ", raw.lower())
    clean = clean.replace("'", "")
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return False

    casual_patterns = [
        r"^(thoth\s+)?(hello|hi|hey|greetings|howdy|hola|yo)(\s+(there|thoth|friend|assistant|bot))?$",
        r"^thoth$",
        r"^((?:(?:hello|hi|hey|greetings|howdy|hola|yo)(?:\s+(?:there|thoth|friend|assistant|bot))?\s+)?)(how\s+are\s+you(\s+doing)?|how\s+do\s+you\s+do|how\s+is\s+it\s+going|hows\s+it\s+going|whats\s+up|what\s+is\s+up|sup)(\s+(today|thoth|there))?$",
        r"^((?:(?:hello|hi|hey|greetings)(?:\s+(?:there|thoth))?\s+)?)(good\s+(morning|afternoon|evening|day|night))(\s+thoth)?$",
        r"^((?:(?:hello|hi|hey|greetings)(?:\s+(?:there|thoth))?\s+)?)(who\s+are\s+you|what\s+are\s+you|what\s+is\s+your\s+name|who\s+made\s+you|who\s+created\s+you|who\s+is\s+thoth|what\s+is\s+thoth|tell\s+me\s+about\s+yourself)(\s+thoth)?$",
        r"^((?:(?:hello|hi|hey|greetings)(?:\s+(?:there|thoth))?\s+)?)(help|what\s+can\s+you\s+do|what\s+do\s+you\s+do|how\s+to\s+use|commands|what\s+are\s+your\s+capabilities|can\s+you\s+help\s+me)(\s+thoth)?$",
        r"^(thanks|thank\s+you|thank\s+you\s+very\s+much|thanks\s+a\s+lot|thank\s+you\s+so\s+much|many\s+thanks|thx|cheers)(\s+thoth)?$",
        r"^(youre\s+welcome|you\s+are\s+welcome|no\s+problem|anytime|my\s+pleasure)$",
        r"^(ok|okay|got\s+it|understood|great|cool|awesome|nice)(\s+thanks|\s+thank\s+you)?$",
        r"^((bye|goodbye|see\s+you(\s+later)?|see\s+ya|talk\s+to\s+you\s+later|have\s+a\s+good\s+day|cya)(\s+thoth)?)$",
        r"^(test|testing|ping|pong|are\s+you\s+there|are\s+you\s+alive|status)$",
    ]

    return any(re.match(p, clean) for p in casual_patterns)

@router.post("/api/research/stream")
async def api_stream_research(request: Request):
    body = await request.json()
    topic = body.get("topic", "Autonomous Research Topic")
    mode = body.get("mode", "auto")
    role = body.get("role", "senior academic researcher")
    tone = body.get("tone", "formal and analytical")
    scrape_top_n = int(body.get("scrape_top_n", 15))

    match_papers = re.search(r'\b(?:top|scrape|fetch|analyze|with)\s+(\d{1,2})\s+papers?\b', topic, re.IGNORECASE)
    if match_papers:
        try:
            scrape_top_n = max(3, min(int(match_papers.group(1)), 50))
            logger.info(f"[SSE STREAM] Extracted natural language paper count: {scrape_top_n} papers")
        except Exception:
            pass

    min_score = float(body.get("min_score", 6.5))
    initial_turns = body.get("chat_turns", [])
    initial_summary = body.get("conversation_summary", "")

    logger.info(f"[SSE STREAM] Request for topic: '{topic}' (mode={mode}, papers={scrape_top_n}, inherited_turns={len(initial_turns)})")

    async def event_generator():
        if mode == "fast_chat" or is_casual_query(topic):
            logger.info(f"[SSE FAST-PATH] Detected casual/greeting query: '{topic}'. Generating direct conversational response.")
            is_fallback = False
            error_details = None
            try:
                loop = asyncio.get_running_loop()
                chat_chain = _get_direct_chat_chain()
                raw_ans = await loop.run_in_executor(None, lambda: chat_chain.invoke({"user_query": topic}))
                clean_ans = strip_chain_of_thought(raw_ans)
            except Exception as e:
                is_fallback = True
                error_details = f"{type(e).__name__}: {sanitize_log_message(str(e))}"
                logger.error(f"[SSE FAST-PATH ERROR] Direct chat invocation failed in /api/research/stream ({type(e).__name__}): {sanitize_log_message(str(e))}")
                clean_ans = f"Greetings! I am Thoth, the Divine Scribe. How may I assist your scientific or technical research today?"

            update_data = {
                "answer": clean_ans,
                "fallback": is_fallback,
                "degraded": is_fallback,
            }
            if is_fallback:
                update_data["error"] = error_details

            state_data = {
                "topic": "General Inquiries & Exploration",
                "report": "",
                "direct_answer": clean_ans,
                "fallback": is_fallback,
                "degraded": is_fallback,
                "follow_up_questions": [
                    "Quantum Computing Surface Codes Error Correction",
                    "CRISPR Prime Editing off-target fidelity breakthroughs",
                    "LLM Mechanistic Interpretability sparse autoencoders",
                    "How does Thoth's Truth Guard verify claims against primary sources?"
                ] if not is_fallback else []
            }

            yield {
                "event": "message",
                "data": json.dumps({
                    "node": "direct_chat",
                    "update": update_data,
                    "state": state_data
                })
            }
            yield {
                "event": "message",
                "data": json.dumps({"node": "complete", "state": {}})
            }
            return

        # Check for Research Brief and explicit User Approval barrier
        brief_id = body.get("brief_id")
        brief_payload = body.get("brief")
        expected_version = body.get("version") or body.get("brief_version")
        if expected_version is None and isinstance(brief_payload, dict):
            expected_version = brief_payload.get("version")

        brief_identifier = brief_id
        if not brief_identifier and isinstance(brief_payload, dict):
            brief_identifier = brief_payload.get("brief_id")

        thinker_id = body.get("thinker_id")
        hypothesis = body.get("hypothesis")
        constraints = body.get("constraints")
        selection_criteria = body.get("selection_criteria")

        brief_obj: Optional[ResearchBrief] = None
        is_approved = False
        barrier_reason = ""

        if brief_identifier:
            is_approved, brief_obj, barrier_reason = verify_brief_approval(
                brief_identifier,
                expected_version=expected_version,
            )
        elif brief_payload:
            is_approved, brief_obj, barrier_reason = verify_brief_approval(
                brief_payload,
                expected_version=expected_version,
            )
        else:
            is_approved = False
            barrier_reason = "No research brief provided. Formal research requires an explicit, approved Research Brief."

        # If not approved, synthesize/prepare a brief and stop execution at the barrier!
        if not is_approved:
            if not brief_obj:
                brief_obj = prepare_research_brief(
                    topic=topic,
                    chat_turns=initial_turns,
                    conversation_summary=initial_summary,
                    thinker_id=thinker_id,
                    hypothesis=hypothesis,
                    constraints=constraints,
                    selection_criteria=selection_criteria,
                )

            logger.info(
                f"[SSE APPROVAL BARRIER] Execution halted for topic '{topic}'. "
                f"Brief '{brief_obj.brief_id}' (v{brief_obj.version}) status='{brief_obj.approval_status}': {barrier_reason}"
            )

            yield {
                "event": "message",
                "data": json.dumps({
                    "node": "approval_barrier",
                    "update": {
                        "approval_status": brief_obj.approval_status,
                        "requires_approval": True,
                        "barrier_reason": barrier_reason,
                        "brief": brief_obj.to_dict(),
                        "message": (
                            f"Formal research cannot begin without explicit user approval. "
                            f"Please review and approve the Research Brief (version {brief_obj.version})."
                        ),
                    },
                    "state": {
                        "topic": topic,
                        "brief": brief_obj.to_dict(),
                        "approval_status": brief_obj.approval_status,
                    }
                })
            }
            yield {
                "event": "message",
                "data": json.dumps({"node": "complete", "state": {}})
            }
            return

        # At this point, the brief is genuinely approved!
        # Register task and enforce concurrency protection against duplicate launches
        task_id = f"task_{brief_obj.brief_id}_{int(time.time() * 1000)}"
        can_run, cancel_event, task_msg = task_manager.register_task(
            task_id=task_id,
            brief_id=brief_obj.brief_id,
            version=brief_obj.version,
        )

        if not can_run:
            logger.warning(f"[SSE REJECTED] Duplicate execution attempt: {task_msg}")
            yield {
                "event": "message",
                "data": json.dumps({
                    "node": "duplicate_execution_rejected",
                    "update": {"error": task_msg},
                    "state": {"error": task_msg}
                })
            }
            yield {
                "event": "message",
                "data": json.dumps({"node": "complete", "state": {}})
            }
            return

        # Announce verified approval to client before launching worker
        yield {
            "event": "message",
            "data": json.dumps({
                "node": "approval_verified",
                "update": {
                    "task_id": task_id,
                    "brief_id": brief_obj.brief_id,
                    "version": brief_obj.version,
                    "approved_at": brief_obj.approved_at,
                    "thinker_context": brief_obj.thinker_context,
                    "hypotheses": brief_obj.hypotheses,
                    "message": f"Mandate confirmed. Launching deep academic research with approved brief (v{brief_obj.version})."
                },
                "state": {
                    "topic": topic,
                    "brief": brief_obj.to_dict(),
                    "task_id": task_id,
                }
            })
        }

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        pipeline_func = _get_stream_research_pipeline()

        def _worker():
            try:
                # 1. Revalidate authorization at execution-claim boundary
                import os
                import threading
                worker_id = f"worker_{os.getpid()}_{threading.get_ident()}"
                claimed, claimed_task, claim_msg = task_manager.claim_task(task_id, worker_id=worker_id)
                if not claimed:
                    logger.warning(f"[WORKER ABORTED] Could not claim execution for task '{task_id}': {claim_msg}")
                    err_data = {
                        "node": "error",
                        "update": {"error": claim_msg},
                        "state": {"error": claim_msg}
                    }
                    asyncio.run_coroutine_threadsafe(queue.put(err_data), loop)
                    return

                was_cancelled = False
                for item in pipeline_func(
                    topic=topic,
                    role=role,
                    tone=tone,
                    scrape_top_n=scrape_top_n,
                    min_score=min_score,
                    initial_turns=initial_turns,
                    initial_summary=initial_summary,
                    cancel_event=cancel_event,
                    brief=brief_obj.to_dict() if brief_obj else None,
                ):
                    if isinstance(item, (tuple, list)) and len(item) == 3:
                        node_name, update, current_state = item
                    elif isinstance(item, dict):
                        node_name = item.get("node", "")
                        update = item.get("update", {})
                        current_state = item.get("state", {})
                    else:
                        continue
                    if not isinstance(current_state, dict):
                        current_state = {}
                    clean_state = {
                        "topic": current_state.get("topic", ""),
                        "report": current_state.get("report", ""),
                        "score": current_state.get("score", 0.0),
                        "attempt": current_state.get("attempt", 0),
                        "verification_results": current_state.get("verification_results", []),
                        "mindmap": current_state.get("mindmap", {}),
                        "cumulative_sources": current_state.get("cumulative_sources", []),
                        "follow_up_questions": current_state.get("follow_up_questions", []),
                        "chat_turns": current_state.get("chat_turns", []),
                        "conversation_summary": current_state.get("conversation_summary", ""),
                        "integrity_status": current_state.get("integrity_status", "PENDING"),
                        "is_verified": current_state.get("is_verified", False),
                        "integrity_result": current_state.get("integrity_result", {}),
                        "brief": current_state.get("brief", {}),
                        "thinker_context": current_state.get("thinker_context", {}),
                        "hypotheses": current_state.get("hypotheses", []),
                        "unresolved_questions": current_state.get("unresolved_questions", []),
                    }
                    event_data = {
                        "node": node_name,
                        "update": update if isinstance(update, dict) else {},
                        "state": clean_state
                    }
                    asyncio.run_coroutine_threadsafe(queue.put(event_data), loop)
                    if node_name == "cancelled" or current_state.get("cancelled"):
                        was_cancelled = True

                if was_cancelled:
                    task_manager.record_cancellation(task_id)
                else:
                    task_manager.complete_task(task_id, "COMPLETED")
            except Exception as e:
                logger.error(f"[SSE ERROR] Pipeline worker exception: {e}")
                task_manager.complete_task(task_id, "FAILED", error_code="WORKER_EXCEPTION", error_summary=str(e))
                err_data = {
                    "node": "error",
                    "update": {"error": str(e)},
                    "state": {"error": str(e)}
                }
                asyncio.run_coroutine_threadsafe(queue.put(err_data), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        import threading
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        while True:
            item = await queue.get()
            if item is None:
                yield {
                    "event": "message",
                    "data": json.dumps({"node": "complete", "state": {}})
                }
                break

            yield {
                "event": "message",
                "data": json.dumps(item)
            }

    return EventSourceResponse(event_generator())

@router.post("/api/research/clarify")
async def api_check_clarification(request: Request):
    body = await request.json()
    topic = body.get("topic", "")
    chat_turns = body.get("chat_turns", [])
    summary = body.get("conversation_summary", "")

    mandate = synthesize_research_mandate(
        user_query=topic,
        chat_turns=chat_turns,
        conversation_summary=summary,
    )
    result = evaluate_clarification_need(mandate)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={
            "mandate": mandate.to_dict(),
            "clarification": result.to_dict(),
        }
    )


@router.post("/api/research/brief/prepare")
async def api_prepare_brief(request: Request):
    body = await request.json()
    topic = body.get("topic", "")
    chat_turns = body.get("chat_turns", [])
    summary = body.get("conversation_summary", "")
    thinker_id = body.get("thinker_id")
    hypothesis = body.get("hypothesis")
    constraints = body.get("constraints")
    criteria = body.get("selection_criteria")
    unresolved = body.get("unresolved_questions")
    session_id = body.get("session_id", "")

    brief = prepare_research_brief(
        topic=topic,
        chat_turns=chat_turns,
        conversation_summary=summary,
        thinker_id=thinker_id,
        hypothesis=hypothesis,
        constraints=constraints,
        selection_criteria=criteria,
        unresolved_questions=unresolved,
        session_id=session_id,
    )
    from fastapi.responses import JSONResponse
    return JSONResponse(content={"success": True, "brief": brief.to_dict()})


@router.get("/api/research/brief/{brief_id}")
async def api_get_brief(brief_id: str):
    brief = get_research_brief(brief_id)
    from fastapi.responses import JSONResponse
    if not brief:
        return JSONResponse(content={"success": False, "error": f"Brief '{brief_id}' not found."}, status_code=404)
    return JSONResponse(content={"success": True, "brief": brief.to_dict()})


@router.post("/api/research/brief/update")
async def api_update_brief(request: Request):
    body = await request.json()
    brief_id = body.get("brief_id")
    updates = body.get("updates", {})
    from fastapi.responses import JSONResponse
    if not brief_id:
        return JSONResponse(content={"success": False, "error": "Missing brief_id parameter."}, status_code=400)
    try:
        updated = update_research_brief(brief_id, updates)
        return JSONResponse(content={"success": True, "brief": updated.to_dict()})
    except ValueError as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=404)


@router.post("/api/research/brief/approve")
async def api_approve_brief(request: Request):
    body = await request.json()
    brief_id = body.get("brief_id")
    version = int(body.get("version", 1))
    from fastapi.responses import JSONResponse
    if not brief_id:
        return JSONResponse(content={"error": "Missing brief_id parameter."}, status_code=400)

    ok, brief, msg = approve_research_brief(brief_id, version)
    if not ok:
        return JSONResponse(
            content={"error": msg, "brief": brief.to_dict() if brief else None},
            status_code=409 if "Stale" in msg else 400
        )
    return JSONResponse(content={"success": True, "message": msg, "brief": brief.to_dict()})


@router.post("/api/research/cancel")
async def api_cancel_research(request: Request):
    body = await request.json()
    identifier = body.get("task_id") or body.get("brief_id")
    from fastapi.responses import JSONResponse
    if not identifier:
        return JSONResponse(content={"error": "Missing task_id or brief_id."}, status_code=400)
    cancelled = task_manager.cancel_task(identifier)
    return JSONResponse(content={"cancelled": cancelled, "identifier": identifier})


@router.get("/api/research/task/{task_id}")
async def api_get_task(task_id: str):
    task = task_manager.get_task(task_id)
    from fastapi.responses import JSONResponse
    if not task:
        return JSONResponse(
            content={"success": False, "error": f"Research task '{task_id}' not found."},
            status_code=404
        )
    clean_task = {
        "task_id": task["task_id"],
        "brief_id": task["brief_id"],
        "brief_version": task["brief_version"],
        "status": task["status"],
        "created_at": task["created_at"],
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
        "updated_at": task["updated_at"],
        "error_code": task.get("error_code"),
        "error_summary": task.get("error_summary"),
        "cancel_requested": bool(task.get("cancel_requested", 0)),
    }
    return JSONResponse(content={"success": True, "task": clean_task})


@router.get("/api/research/tasks")
async def api_list_tasks(brief_id: Optional[str] = None, limit: int = 50):
    from backend.memory.db import list_tasks_db
    from fastapi.responses import JSONResponse
    raw_tasks = list_tasks_db(brief_id=brief_id, limit=limit)
    clean_tasks = [
        {
            "task_id": t["task_id"],
            "brief_id": t["brief_id"],
            "brief_version": t["brief_version"],
            "status": t["status"],
            "created_at": t["created_at"],
            "started_at": t.get("started_at"),
            "completed_at": t.get("completed_at"),
            "updated_at": t["updated_at"],
            "error_code": t.get("error_code"),
            "error_summary": t.get("error_summary"),
            "cancel_requested": bool(t.get("cancel_requested", 0)),
        }
        for t in raw_tasks
    ]
    return JSONResponse(content={"success": True, "tasks": clean_tasks, "total": len(clean_tasks)})
