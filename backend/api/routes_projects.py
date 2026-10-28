"""Project state on the server (docs/features/02-threads-projects-notebook.md).

GET  /api/projects/{id}/state       thread or project, question, hypothesis versions, rivals, the conversation
PUT  /api/projects/{id}/notebook    the researcher's own question / hypothesis / rival (a new version), with an optional rationale
GET  /api/projects/{id}/history?kind=   every version of question / hypothesis / rival / design with why it changed
GET  /api/projects/{id}/footprint   what the project holds, with counts (shown before deleting)
GET  /api/projects/{id}/markers     strength markers of the current hypothesis (once per version)
POST /api/projects/{id}/rivals/retire   {text}: a parked rival is retired
POST /api/projects/{id}/rivals/swap     {text}: the rival becomes the main hypothesis; the old main is parked
GET|PUT /api/projects/{id}/mode     Autopilot / Co-pilot with per-step overrides (subclaims, screening, proposal)
Deleting is DELETE /api/projects/{id}?confirm=true (routes_workspace), which removes all of it.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.conversation import projects

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("/{project_id}/state")
async def get_state(project_id: str):
    return projects.state(project_id)


@router.put("/{project_id}/notebook")
async def write_notebook(project_id: str, request: Request):
    body = await request.json()
    try:
        return projects.write(project_id, str(body.get("section") or ""), str(body.get("value") or ""),
                              body.get("rationale") if isinstance(body.get("rationale"), dict) else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/history")
async def get_history(project_id: str, kind: str = "hypothesis"):
    try:
        return projects.history(project_id, kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/footprint")
async def get_footprint(project_id: str):
    return projects.footprint(project_id)


@router.get("/{project_id}/markers")
async def get_markers(project_id: str):
    return await projects.markers(project_id)


@router.post("/{project_id}/rivals/retire")
async def retire_rival(project_id: str, request: Request):
    body = await request.json()
    try:
        return {"rivals": projects.retire_rival(project_id, str(body.get("text") or ""))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{project_id}/rivals/swap")
async def swap_rival(project_id: str, request: Request):
    body = await request.json()
    try:
        return projects.swap(project_id, str(body.get("text") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/mode")
async def get_mode(project_id: str):
    return projects.get_mode(project_id)


@router.put("/{project_id}/mode")
async def set_mode(project_id: str, request: Request):
    body = await request.json()
    try:
        return projects.set_mode(project_id, str(body.get("mode") or ""), body.get("step_overrides") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

