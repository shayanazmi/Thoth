# Thoth · Developed by Shayan Azmi
"""Projects and their state on the server (docs/FEATURES.md §2).

POST /api/projects                  {title}: a new thread
GET  /api/projects                  every thread and project, each with its kind
DELETE /api/projects/{id}?confirm=true   removes the project and everything it holds (409 with the counts without confirm)
GET  /api/projects/{id}/state      thread or project, question, hypothesis versions, rivals, the conversation
PUT  /api/projects/{id}/notebook    the researcher's own question / hypothesis / rival (a new version), with an optional rationale
GET  /api/projects/{id}/history?kind=   every version of question / hypothesis / rival / design with why it changed
GET  /api/projects/{id}/footprint   what the project holds, with counts (shown before deleting)
GET  /api/projects/{id}/markers     strength markers of the current hypothesis (once per version)
POST /api/projects/{id}/rivals/retire   {text}: a parked rival is retired
POST /api/projects/{id}/rivals/swap     {text}: the rival becomes the main hypothesis; the old main is parked
GET|PUT /api/projects/{id}/mode     Autopilot / Co-pilot with per-step overrides (subclaims, screening, proposal)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator

from backend.conversation import projects
from backend.workspace.project import create_project, list_projects

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class ProjectCreateRequest(BaseModel):
    """Accepts ``title`` or its common alias ``name``."""
    title: str = Field(..., min_length=1)
    description: str = ""
    session_id: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _accept_name_alias(cls, data):
        if isinstance(data, dict) and "title" not in data and "name" in data:
            return {**data, "title": data["name"]}
        return data


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(req: ProjectCreateRequest):
    proj = create_project(title=req.title, description=req.description, session_id=req.session_id, metadata=req.metadata)
    return {"status": "success", "project": proj.to_dict()}


@router.get("")
async def list_all(session_id: Optional[str] = Query(None), status_filter: Optional[str] = Query(None, alias="status")):
    # A chat is a thread until a hypothesis is accepted (docs/FEATURES.md §2).
    return {"status": "success", "projects": [{**p.to_dict(), "kind": projects.kind(p.project_id)}
                                              for p in list_projects(session_id=session_id, status=status_filter)]}


@router.delete("/{project_id}")
async def delete(project_id: str, confirm: bool = Query(False)):
    """Without ?confirm=true nothing is deleted: 409 with the counts the researcher must see first."""
    if not projects.exists(project_id):
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    if not confirm:
        raise HTTPException(status_code=409, detail=projects.footprint(project_id))
    return {"status": "success", "deleted": True, "removed": projects.delete(project_id)}


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

