#!/usr/bin/env python3
"""
Thoth · Web Server Gateway (FastAPI + SSE)
===========================================
High-performance asynchronous API gateway streaming multi-agent research telemetry,
multi-turn conversational turns, and serving the 3D shadcn/ui frontend.
"""

import os
import sys
import json
import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

# Add project root to sys.path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.orchestrator import stream_research_pipeline
from backend.pipeline import stream_followup_turn
from backend.agents import direct_chat_chain, strip_chain_of_thought
from backend.memory.vault import list_notes, read_note, DEFAULT_VAULT_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ThothWebServer")

app = FastAPI(title="Thoth Research Gateway", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import re

def is_casual_query(text: str) -> bool:
    """Detects simple greetings, meta-questions, or casual chat that does not require an 8-agent academic pipeline."""
    clean = text.strip().lower()
    clean = re.sub(r"[^\w\s]", "", clean)
    
    casual_patterns = [
        r"^(hello|hi|hey|greetings|howdy|hola|yo)$",
        r"^(who are you|what are you|what is your name|who made you)$",
        r"^(how are you|how do you do|whats up|sup)$",
        r"^(help|what can you do|what do you do|how to use|commands)$",
        r"^(thanks|thank you|thx|cheers)$",
        r"^(good morning|good afternoon|good evening|good day)$",
        r"^(test|testing|ping|are you there)$"
    ]
    if any(re.match(p, clean) for p in casual_patterns):
        return True
    
    if len(clean.split()) == 1 and clean in {"hi", "hello", "hey", "hola", "sup", "thoth", "help"}:
        return True
    
    return False


@app.post("/api/research/stream")
async def api_stream_research(request: Request):
    """
    Server-Sent Events endpoint streaming the 8-agent research pipeline in real-time,
    with an ultra-fast path for casual greetings and general inquiries.
    """
    body = await request.json()
    topic = body.get("topic", "Autonomous Research Topic")
    mode = body.get("mode", "auto")
    role = body.get("role", "senior academic researcher")
    tone = body.get("tone", "formal and analytical")
    scrape_top_n = int(body.get("scrape_top_n", 15))
    
    # Natural language paper count detection (e.g. 'research X with 20 papers' or 'top 10 papers')
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
        # Fast path for greetings and casual conversation (<500ms)
        if mode == "fast_chat" or is_casual_query(topic):
            logger.info(f"[SSE FAST-PATH] Detected casual/greeting query: '{topic}'. Generating direct conversational response.")
            try:
                loop = asyncio.get_running_loop()
                raw_ans = await loop.run_in_executor(None, lambda: direct_chat_chain.invoke({"user_query": topic}))
                clean_ans = strip_chain_of_thought(raw_ans)
            except Exception as e:
                clean_ans = f"Greetings! I am Thoth, the Divine Scribe. How may I assist your scientific or technical research today?"

            yield {
                "event": "message",
                "data": json.dumps({
                    "node": "direct_chat",
                    "update": {"answer": clean_ans},
                    "state": {
                        "topic": "General Inquiries & Exploration",
                        "report": "",
                        "direct_answer": clean_ans,
                        "follow_up_questions": [
                            "Quantum Computing Surface Codes Error Correction",
                            "CRISPR Prime Editing off-target fidelity breakthroughs",
                            "LLM Mechanistic Interpretability sparse autoencoders",
                            "How does Thoth's Truth Guard verify claims against primary sources?"
                        ]
                    }
                })
            }
            yield {
                "event": "message",
                "data": json.dumps({"node": "complete", "state": {}})
            }
            return

        # Execute full multi-agent stream_research_pipeline in threadpool
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()


        def _worker():
            try:
                for node_name, update, current_state in stream_research_pipeline(
                    topic=topic,
                    role=role,
                    tone=tone,
                    scrape_top_n=scrape_top_n,
                    min_score=min_score,
                    initial_turns=initial_turns,
                    initial_summary=initial_summary
                ):
                    # Clean state for JSON serialization
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
                        "conversation_summary": current_state.get("conversation_summary", "")
                    }
                    event_data = {
                        "node": node_name,
                        "update": update if isinstance(update, dict) else {},
                        "state": clean_state
                    }
                    asyncio.run_coroutine_threadsafe(queue.put(event_data), loop)
            except Exception as e:
                logger.error(f"[SSE ERROR] Pipeline worker exception: {e}")
                asyncio.run_coroutine_threadsafe(queue.put({"node": "error", "error": str(e), "state": {}}), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        # Run generator in separate background thread
        loop.run_in_executor(None, _worker)

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


@app.post("/api/followup/stream")
async def api_stream_followup(request: Request):
    """
    Server-Sent Events endpoint streaming multi-turn follow-up dialogue and living report expansions.
    """
    body = await request.json()
    current_state = body.get("state", {})
    user_query = body.get("user_query", "")
    mode_override = body.get("mode_override", "auto")

    logger.info(f"[SSE FOLLOWUP] Follow-up query: '{user_query}' (mode={mode_override})")

    async def event_generator():
        loop = asyncio.get_running_loop()

        # Fast direct dialogue path (<500ms)
        if mode_override == "fast_chat" or is_casual_query(user_query):
            logger.info(f"[SSE FAST FOLLOWUP] Direct dialogue path for: '{user_query}'")
            try:
                raw_ans = await loop.run_in_executor(None, lambda: direct_chat_chain.invoke({"user_query": user_query}))
                clean_ans = strip_chain_of_thought(raw_ans)
            except Exception as e:
                clean_ans = "I am at your service. How may I assist your research?"
            
            chat_turns = list(current_state.get("chat_turns", []))
            chat_turns.append({
                "turn": len(chat_turns) + 1,
                "user_query": user_query,
                "assistant_response": clean_ans,
                "route": "FAST_CHAT"
            })

            yield {
                "event": "message",
                "data": json.dumps({
                    "event": "answer",
                    "payload": {
                        "answer": clean_ans,
                        "route": "FAST_CHAT",
                        "citations": []
                    }
                })
            }
            yield {
                "event": "message",
                "data": json.dumps({
                    "event": "followup_complete",
                    "payload": {
                        "user_query": user_query,
                        "answer": clean_ans,
                        "route": "FAST_CHAT",
                        "citations": [],
                        "chat_turns": chat_turns,
                        "conversation_summary": current_state.get("conversation_summary", ""),
                        "follow_up_questions": [
                            "Explore key breakthroughs in this area",
                            "What are the major contradictory perspectives in the literature?",
                            "How can these findings be applied in real-world deployment?"
                        ]
                    }
                })
            }
            return

        queue = asyncio.Queue()

        def _worker():
            try:
                for event_type, payload in stream_followup_turn(
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
                logger.error(f"[SSE FOLLOWUP ERROR] {e}")
                asyncio.run_coroutine_threadsafe(queue.put({"event": "error", "payload": {"error": str(e)}}), loop)
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


@app.get("/health")
def api_health():
    """Health check endpoint."""
    return {"status": "ok", "app": "Thoth Research Intelligence"}


@app.get("/api/status")
def api_status():
    """Returns telemetry and circuit breaker status."""
    from backend.telemetry import get_telemetry_status
    return get_telemetry_status()


@app.get("/api/sessions")
def api_list_sessions(limit: int = 20):
    """Lists saved research sessions from SQLite database."""
    from backend.memory.db import list_sessions
    return list_sessions(limit=limit)


@app.get("/api/reports")
def api_list_reports(limit: int = 20):
    """Lists saved synthesis reports from SQLite database."""
    from backend.memory.db import list_reports
    return list_reports(limit=limit)


@app.get("/api/vault/graph")
def api_vault_graph(root_node: Optional[str] = None, max_depth: int = 2):
    """Returns nodes and edges from the Obsidian vault knowledge graph."""
    from backend.memory.graph import export_citation_subgraph
    start = [root_node] if root_node else None
    return export_citation_subgraph(start_notes=start, max_depth=max_depth)


@app.get("/api/vault/notes")
def api_list_vault_notes():
    """Returns all topic and source notes cataloged in the Obsidian Vault."""
    try:
        notes = list_notes(DEFAULT_VAULT_DIR)
        return {"notes": notes}
    except Exception as e:
        logger.error(f"[VAULT LIST ERROR] {e}")
        return {"notes": []}


@app.get("/api/vault/note/{note_id}")
def api_get_vault_note(note_id: str):
    """Reads content and frontmatter of a specific note from the Vault."""
    try:
        note_obj = read_note(note_id, vault_dir=DEFAULT_VAULT_DIR)
        if not note_obj:
            raise HTTPException(status_code=404, detail="Note not found")
        return {
            "id": note_obj.id,
            "type": note_obj.type,
            "content": note_obj.content,
            "frontmatter": note_obj.frontmatter
        }
    except Exception as e:
        logger.error(f"[VAULT READ ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mount Static Assets
_WEB_DIR = os.path.join(_PROJECT_ROOT, "web")
app.mount("/css", StaticFiles(directory=os.path.join(_WEB_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(_WEB_DIR, "js")), name="js")
app.mount("/assets", StaticFiles(directory=os.path.join(_WEB_DIR, "assets")), name="assets")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main single-page application."""
    index_file = os.path.join(_WEB_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Thoth Studio index.html not found.</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
