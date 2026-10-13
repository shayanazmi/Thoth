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
    from backend.intellectual_rigour.matcher import ARCHETYPE_DEFINITIONS
    thinkers_list = []
    for tid, data in ARCHETYPE_DEFINITIONS.items():
        thinkers_list.append({
            "id": tid,
            "name": data["name"],
            "tradition": data["tradition"],
            "archetype": data["archetype"],
            "description": data["description"],
            "opening_spar": data["default_opening"],
        })
    return JSONResponse(content={"thinkers": thinkers_list})

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
    body = await request.json()
    thinker_id = body.get("thinker_id", "auto")
    message = body.get("message", "")
    chat_turns = body.get("chat_turns", [])

    from backend.intellectual_rigour.matcher import match_ideation_archetype
    from backend.intellectual_rigour.sparring import spar_with_thinker

    matched_info = None
    if thinker_id == "auto" or not thinker_id:
        match_res = match_ideation_archetype(user_query=message, chat_history=chat_turns)
        thinker_id = match_res.thinker_id
        matched_info = match_res.model_dump()

    loop = asyncio.get_running_loop()
    output = await loop.run_in_executor(
        None,
        lambda: spar_with_thinker(
            thinker_id=thinker_id,
            user_message=message,
            chat_turns=chat_turns
        )
    )

    data = output.model_dump()
    if matched_info:
        data["auto_match"] = matched_info

    return JSONResponse(content=data)
