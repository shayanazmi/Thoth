import re
import sys
import json
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
)

logger = logging.getLogger("ThothWebServer")
router = APIRouter(tags=["Research Pipeline"])

def _get_direct_chat_chain():
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "direct_chat_chain"):
        return ws.direct_chat_chain
    return direct_chat_chain

def _get_stream_research_pipeline():
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

        mandate = synthesize_research_mandate(
            user_query=topic,
            chat_turns=initial_turns,
            conversation_summary=initial_summary,
        )
        clarification = evaluate_clarification_need(mandate)
        if clarification.needs_clarification and not body.get("skip_clarification", False):
            yield {
                "event": "message",
                "data": json.dumps({
                    "node": "clarification_gate",
                    "update": {
                        "clarification_prompt": clarification.clarification_prompt,
                        "options": clarification.options,
                        "reason": clarification.reason,
                    },
                    "state": {
                        "topic": topic,
                        "mandate": mandate.to_dict(),
                    }
                })
            }
            if body.get("clarification_only", False):
                yield {
                    "event": "message",
                    "data": json.dumps({"node": "complete", "state": {}})
                }
                return

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        pipeline_func = _get_stream_research_pipeline()

        def _worker():
            try:
                for node_name, update, current_state in pipeline_func(
                    topic=topic,
                    role=role,
                    tone=tone,
                    scrape_top_n=scrape_top_n,
                    min_score=min_score,
                    initial_turns=initial_turns,
                    initial_summary=initial_summary
                ):
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
                        "integrity_result": current_state.get("integrity_result", {})
                    }
                    event_data = {
                        "node": node_name,
                        "update": update if isinstance(update, dict) else {},
                        "state": clean_state
                    }
                    asyncio.run_coroutine_threadsafe(queue.put(event_data), loop)
            except Exception as e:
                logger.error(f"[SSE ERROR] Pipeline worker exception: {e}")
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
