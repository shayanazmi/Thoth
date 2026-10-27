import os
import sys
import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from backend.repositories.base import supabase_provider
from backend.memory.vault import list_notes, read_note, DEFAULT_VAULT_DIR
from backend.memory.graph import export_citation_subgraph
from backend.memory.db import list_sessions, list_reports
from backend.conversation import detect_escalation_intent

logger = logging.getLogger("ThothWebServer")
router = APIRouter(prefix="/api", tags=["Vault & Sessions"])

def _get_read_note():
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "read_note"):
        return ws.read_note
    return read_note

def _get_list_notes():
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "list_notes"):
        return ws.list_notes
    return list_notes

@router.get("/vault/notes")
def api_list_vault_notes():
    try:
        notes = _get_list_notes()(DEFAULT_VAULT_DIR)
        return {"notes": notes}
    except Exception as e:
        logger.error(f"[VAULT LIST ERROR] {e}")
        return {"notes": []}

@router.get("/vault/note/{note_id}")
def api_get_vault_note(note_id: str):
    try:
        note_obj = _get_read_note()(note_id, vault_dir=DEFAULT_VAULT_DIR)
        if not note_obj:
            raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")
        return {
            "id": note_obj.note_id,
            "type": note_obj.note_type,
            "content": note_obj.content,
            "frontmatter": note_obj.frontmatter,
            "note_id": note_obj.note_id,
            "note_type": note_obj.note_type,
            "file_path": note_obj.file_path,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VAULT READ ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/vault/graph")
def api_vault_graph(root_node: Optional[str] = None, max_depth: int = 2):
    start = [root_node] if root_node else None
    return export_citation_subgraph(start_notes=start, max_depth=max_depth)

@router.get("/sessions")
def api_list_sessions(limit: int = 50):
    client = supabase_provider.get_client()
    if client:
        try:
            res = client.table("sessions").select("*").order("updated_at", desc=True).limit(limit).execute()
            if res.data is not None:
                return res.data
        except Exception as e:
            logger.warning(f"Failed to query Supabase sessions: {e}")
    return list_sessions(limit=limit)

@router.get("/reports")
def api_list_reports(limit: int = 50):
    client = supabase_provider.get_client()
    if client:
        try:
            res = client.table("reports").select("*").order("created_at", desc=True).limit(limit).execute()
            if res.data is not None:
                return res.data
        except Exception as e:
            logger.warning(f"Failed to query Supabase reports: {e}")
    return list_reports(limit=limit)

@router.post("/conversation/escalate")
async def api_check_escalation(request: Request):
    body = await request.json()
    query = body.get("query", "")
    chat_turns = body.get("chat_turns", [])
    summary = body.get("summary", "")
    escalation = detect_escalation_intent(
        user_query=query,
        chat_turns=chat_turns,
        conversation_summary=summary,
    )
    return JSONResponse(content=escalation)
