import sys
import json
import asyncio
import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends
from sse_starlette.sse import EventSourceResponse

from backend.agents import (
    direct_chat_chain,
    strip_chain_of_thought,
    sanitize_log_message,
)
from backend.pipeline import stream_followup_turn
from backend.api.routes_research import is_casual_query

logger = logging.getLogger("ThothWebServer")
router = APIRouter(tags=["Follow-up & Multi-turn Dialogue"])

def _get_direct_chat_chain():
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "direct_chat_chain"):
        return ws.direct_chat_chain
    return direct_chat_chain

def _get_stream_followup_turn():
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "stream_followup_turn"):
        return ws.stream_followup_turn
    return stream_followup_turn

@router.post("/api/followup/stream")
async def api_stream_followup(request: Request):
    body = await request.json()
    current_state = body.get("state", {})
    user_query = body.get("user_query", "")
    mode_override = body.get("mode_override", "auto")

    logger.info(f"[SSE FOLLOWUP] Follow-up query: '{user_query}' (mode={mode_override})")

    async def event_generator():
        loop = asyncio.get_running_loop()

        if mode_override == "fast_chat" or is_casual_query(user_query):
            logger.info(f"[SSE FAST FOLLOWUP] Direct dialogue path for: '{user_query}'")
            is_fallback = False
            error_details = None
            try:
                chat_chain = _get_direct_chat_chain()
                raw_ans = await loop.run_in_executor(None, lambda: chat_chain.invoke({"user_query": user_query}))
                clean_ans = strip_chain_of_thought(raw_ans)
            except Exception as e:
                is_fallback = True
                error_details = f"{type(e).__name__}: {sanitize_log_message(str(e))}"
                logger.error(f"[SSE FAST FOLLOWUP ERROR] Direct chat invocation failed in /api/followup/stream ({type(e).__name__}): {sanitize_log_message(str(e))}")
                clean_ans = "I am at your service. How may I assist your research?"

            chat_turns = list(current_state.get("chat_turns", []))
            turn_record = {
                "turn": len(chat_turns) + 1,
                "user_query": user_query,
                "assistant_response": clean_ans,
                "route": "FAST_CHAT",
                "fallback": is_fallback,
                "degraded": is_fallback,
            }
            chat_turns.append(turn_record)

            ans_payload = {
                "answer": clean_ans,
                "route": "FAST_CHAT",
                "citations": [],
                "fallback": is_fallback,
                "degraded": is_fallback,
            }
            if is_fallback:
                ans_payload["error"] = error_details

            yield {
                "event": "message",
                "data": json.dumps({
                    "event": "answer",
                    "payload": ans_payload
                })
            }

            comp_payload = {
                "user_query": user_query,
                "answer": clean_ans,
                "route": "FAST_CHAT",
                "citations": [],
                "chat_turns": chat_turns,
                "conversation_summary": current_state.get("conversation_summary", ""),
                "fallback": is_fallback,
                "degraded": is_fallback,
                "follow_up_questions": [
                    "Explore key breakthroughs in this area",
                    "What are the major contradictory perspectives in the literature?",
                    "How can these findings be applied in real-world deployment?"
                ] if not is_fallback else []
            }

            yield {
                "event": "message",
                "data": json.dumps({
                    "event": "followup_complete",
                    "payload": comp_payload
                })
            }
            return

        queue = asyncio.Queue()
        pipeline_func = _get_stream_followup_turn()

        def _worker():
            try:
                for event_type, payload in pipeline_func(
                    current_state=current_state,
                    user_query=user_query,
                    mode_override=mode_override
                ):
                    event_data = {
                        "event": event_type,
                        "payload": payload
                    }
                    asyncio.run_coroutine_threadsafe(queue.put(event_data), loop)
            except Exception as e:
                clean_err = sanitize_log_message(str(e))
                logger.error(f"[SSE FOLLOWUP ERROR] {clean_err}")
                asyncio.run_coroutine_threadsafe(queue.put({"event": "error", "payload": {"error": clean_err}}), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop.run_in_executor(None, _worker)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield {
                "event": "message",
                "data": json.dumps(item)
            }

    return EventSourceResponse(event_generator())
