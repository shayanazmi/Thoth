import asyncio
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from backend.core.logging import get_logger
from backend.core.auth import get_optional_user

logger = get_logger("BrainstormRouter")
router = APIRouter(prefix="/api/brainstorm", tags=["Intellectual Sparring & Thinkers"])

@router.get("/thinkers")
async def api_list_brainstorm_thinkers():
    """Kept for older clients; the roster now comes from backend/thinkers (docs/features/03)."""
    from backend.api.routes_thinkers import roster_payload
    return JSONResponse(content=roster_payload())

@router.post("/match")
async def api_match_thinker(request: Request):
    body = await request.json()
    query = body.get("query", "")
    chat_turns = body.get("chat_turns", [])
    from backend.intellectual_rigour.matcher import match_ideation_archetype
    result = match_ideation_archetype(user_query=query, chat_history=chat_turns)
    return JSONResponse(content=result.model_dump())

@router.post("/chat")
async def api_brainstorm_spar(request: Request, user: Dict[str, Any] = Depends(get_optional_user)):
    """Kept for older clients: one thinker replies through the dossier-driven engine
    (docs/features/03). The old shared sparring script is retired."""
    from backend.thinkers import modes, roster
    body = await request.json()
    thinker_id = body.get("thinker_id") or ""
    if roster.get(thinker_id) is None:
        return JSONResponse(status_code=404, content={"error": "not on the roster"})
    out = await modes.reply(str(body.get("project_id") or body.get("session_id") or "default"),
                            thinker_id, (body.get("message") or "").strip() or "Introduce how you would look at my idea.",
                            body.get("mode") or "join")
    out.pop("exchange", None)
    return JSONResponse(content=out)


@router.post("/council")
async def api_brainstorm_council(request: Request):
    """Kept for older clients: every thinker reacts independently (docs/features/03)."""
    from backend.thinkers import modes
    body = await request.json()
    idea = (body.get("idea") or body.get("message") or "").strip()
    takes = await modes.council(str(body.get("project_id") or "default"), idea) if idea else []
    return JSONResponse(content={"idea": idea, "council": takes, "degraded": not any(t["take"] for t in takes)})
