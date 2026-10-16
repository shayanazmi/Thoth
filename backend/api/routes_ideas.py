from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.core.logging import get_logger
from backend.conversation.idea import (
    create_tentative_idea,
    promote_idea_to_artifact,
    revise_idea,
    abandon_idea,
    get_idea,
    list_ideas,
    get_idea_history,
    ResearchIdea,
    IdeaStatus,
)
from backend.intellectual_rigour.counter_evidence import (
    generate_counter_evidence_plan,
    generate_hypothesis_revision_proposal,
)

logger = get_logger("IdeasRouter")
router = APIRouter(prefix="/api/ideas", tags=["Ideas & Hypotheses Lifecycle"])


class CreateTentativeIdeaRequest(BaseModel):
    title: str = Field(..., description="Descriptive title of the idea")
    hypothesis: str = Field(..., description="Core testable hypothesis")
    description: Optional[str] = Field(default="", description="Detailed context or exploratory rationale")
    session_id: Optional[str] = Field(default="", description="Associated conversation session ID")
    thinker_id: Optional[str] = Field(default=None, description="Thinker ID if generated through sparring")
    thinker_critique: Optional[str] = Field(default=None, description="Critique or dialectic feedback")
    unresolved_objections: Optional[List[str]] = Field(default_factory=list, description="Open objections or falsification criteria")


class PromoteIdeaRequest(BaseModel):
    approved: bool = Field(..., description="Explicit user confirmation to promote idea into persistent storage")


class ReviseIdeaRequest(BaseModel):
    new_hypothesis: str = Field(..., description="Revised testable hypothesis")
    revision_notes: Optional[str] = Field(default="", description="Rationale for this hypothesis revision")
    new_title: Optional[str] = Field(default=None, description="Updated title, if applicable")
    thinker_id: Optional[str] = Field(default=None, description="Thinker ID prompting revision")
    thinker_critique: Optional[str] = Field(default=None, description="New critique or dialectic refinement")
    unresolved_objections: Optional[List[str]] = Field(default=None, description="Updated objections or falsification criteria")


class AbandonIdeaRequest(BaseModel):
    reason: Optional[str] = Field(default="", description="Reason for shelving or abandoning this idea")


class CounterEvidencePlanRequest(BaseModel):
    thinker_id: Optional[str] = Field(default=None, description="Thinker ID override")
    objections: Optional[List[str]] = Field(default=None, description="Specific objections to translate into counter-evidence queries")
    topic: Optional[str] = Field(default=None, description="Broader research topic context")


class ProposeRevisionRequest(BaseModel):
    counter_evidence_findings: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted counter-evidence claims or findings")
    thinker_id: Optional[str] = Field(default=None, description="Thinker ID override")
    objection: Optional[str] = Field(default="", description="Specific objection prompting the revision")


@router.post("/tentative", status_code=status.HTTP_201_CREATED)
async def api_create_tentative_idea(payload: CreateTentativeIdeaRequest):
    idea = create_tentative_idea(
        title=payload.title,
        hypothesis=payload.hypothesis,
        description=payload.description or "",
        session_id=payload.session_id or "",
        thinker_id=payload.thinker_id,
        thinker_critique=payload.thinker_critique,
        unresolved_objections=payload.unresolved_objections,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "idea": idea.to_dict(), "message": "Tentative idea formulated."},
    )


@router.post("/{idea_id}/promote")
async def api_promote_idea(idea_id: str, payload: PromoteIdeaRequest):
    success, idea, msg = promote_idea_to_artifact(
        idea_id=idea_id,
        user_approved=payload.approved,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
    return JSONResponse(
        content={"success": True, "idea": idea.to_dict(), "message": msg}
    )


@router.post("/{idea_id}/revise", status_code=status.HTTP_201_CREATED)
async def api_revise_idea(idea_id: str, payload: ReviseIdeaRequest):
    success, child, msg = revise_idea(
        idea_id=idea_id,
        new_hypothesis=payload.new_hypothesis,
        revision_notes=payload.revision_notes or "",
        new_title=payload.new_title,
        thinker_id=payload.thinker_id,
        thinker_critique=payload.thinker_critique,
        unresolved_objections=payload.unresolved_objections,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "idea": child.to_dict(), "message": msg},
    )


@router.post("/{idea_id}/abandon")
async def api_abandon_idea(idea_id: str, payload: AbandonIdeaRequest):
    success, idea, msg = abandon_idea(
        idea_id=idea_id,
        reason=payload.reason or "",
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=msg,
        )
    return JSONResponse(
        content={"success": True, "idea": idea.to_dict(), "message": msg}
    )


@router.get("/{idea_id}")
async def api_get_idea(idea_id: str):
    idea = get_idea(idea_id)
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research idea '{idea_id}' not found.",
        )
    return JSONResponse(content={"idea": idea.to_dict()})


@router.get("/{idea_id}/history")
async def api_get_idea_history(idea_id: str):
    history = get_idea_history(idea_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research idea '{idea_id}' has no recorded history or does not exist.",
        )
    return JSONResponse(content={"idea_id": idea_id, "history": [i.to_dict() for i in history]})


@router.get("")
async def api_list_ideas(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    ideas = list_ideas(session_id=session_id, status=status, limit=limit)
    return JSONResponse(content={"ideas": [i.to_dict() for i in ideas]})


@router.post("/{idea_id}/counter-evidence-plan")
async def api_counter_evidence_plan(idea_id: str, payload: Optional[CounterEvidencePlanRequest] = None):
    idea = get_idea(idea_id)
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research idea '{idea_id}' not found.",
        )
    p = payload or CounterEvidencePlanRequest()
    plan = generate_counter_evidence_plan(
        hypothesis=idea.hypothesis,
        thinker_id=p.thinker_id or idea.thinker_id,
        objections=p.objections if p.objections is not None else idea.unresolved_objections,
        topic=p.topic or idea.title,
    )
    return JSONResponse(
        content={
            "success": True,
            "idea_id": idea_id,
            "plan": plan.to_dict(),
        }
    )


@router.post("/{idea_id}/propose-revision")
async def api_propose_revision(idea_id: str, payload: ProposeRevisionRequest):
    idea = get_idea(idea_id)
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research idea '{idea_id}' not found.",
        )
    primary_objection = payload.objection
    if not primary_objection and idea.unresolved_objections:
        primary_objection = idea.unresolved_objections[0]

    proposal = generate_hypothesis_revision_proposal(
        idea_id=idea_id,
        current_hypothesis=idea.hypothesis,
        counter_evidence_findings=payload.counter_evidence_findings,
        thinker_id=payload.thinker_id or idea.thinker_id,
        objection=primary_objection or "",
    )
    return JSONResponse(
        content={
            "success": True,
            "idea_id": idea_id,
            "proposal": proposal.to_dict(),
            "message": "Hypothesis revision proposal generated. Note: The persisted idea remains unchanged until explicit user approval via POST /api/ideas/{idea_id}/revise.",
        }
    )

