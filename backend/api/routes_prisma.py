from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, status, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from backend.core.logging import get_logger
from backend.intellectual_rigour.prisma import (
    ScreeningStage,
    ScreeningDisposition,
    ReviewerType,
    run_prisma_review_workflow,
)
from backend.memory.db import (
    DEFAULT_DB_PATH,
    get_prisma_review_db,
    list_prisma_reviews_db,
    save_prisma_review_db,
    get_screening_decision_db,
    list_screening_decisions_db,
    update_screening_decision_db,
    get_brief_db,
)

logger = get_logger("PrismaRouter")
router = APIRouter(prefix="/api/prisma", tags=["PRISMA Systematic Review & Evidence Ledger"])


class ExecuteReviewRequest(BaseModel):
    brief_id: str = Field(..., description="Research brief ID to run PRISMA review on")
    sources: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional list of retrieved sources to screen")


class ConfirmDecisionRequest(BaseModel):
    disposition: ScreeningDisposition = Field(..., description="Confirmed or overridden disposition: INCLUDED, EXCLUDED, UNRESOLVED, NOT_RETRIEVED")
    reviewer_notes: Optional[str] = Field(default="", description="Reviewer justification or audit note")
    reviewer_type: Optional[ReviewerType] = Field(default=ReviewerType.REVIEWER_CONFIRMED, description="Reviewer role")


@router.get("/reviews", response_model=List[Dict[str, Any]])
async def list_reviews(
    session_id: Optional[str] = Query(default=None, description="Filter by session ID"),
    db_path: Optional[str] = None,
):
    """List historical PRISMA reviews with high-level metadata and flow counts."""
    path = db_path or DEFAULT_DB_PATH
    reviews = list_prisma_reviews_db(session_id=session_id, db_path=path)
    return reviews


@router.get("/reviews/{review_id_or_brief_id}")
async def get_review(
    review_id_or_brief_id: str,
    db_path: Optional[str] = None,
):
    """Retrieve full PRISMA review ledger by review_id or linked brief_id."""
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id_or_brief_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id_or_brief_id}' not found.",
        )
    return rev


@router.post("/reviews", status_code=status.HTTP_201_CREATED)
async def execute_review_for_brief(
    req: ExecuteReviewRequest,
    db_path: Optional[str] = None,
):
    """
    Execute PRISMA systematic review and evidence synthesis ledger for a research brief.
    Screens available sources against brief criteria and persists flow counts.
    """
    path = db_path or DEFAULT_DB_PATH
    brief = get_brief_db(req.brief_id, db_path=path)
    if not brief:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research brief '{req.brief_id}' not found.",
        )

    sources = req.sources or []
    topic = brief.get("topic") or "Systematic Review"
    session_id = brief.get("session_id") or ""

    ledger = run_prisma_review_workflow(
        topic=topic,
        sources=sources,
        brief=brief,
        session_id=session_id,
        db_path=path,
    )
    return ledger.to_dict()


@router.get("/reviews/{review_id_or_brief_id}/decisions", response_model=List[Dict[str, Any]])
async def list_decisions_for_review(
    review_id_or_brief_id: str,
    stage: Optional[ScreeningStage] = Query(default=None, description="Filter by screening stage"),
    disposition: Optional[ScreeningDisposition] = Query(default=None, description="Filter by disposition"),
    db_path: Optional[str] = None,
):
    """List granular screening and eligibility decisions for a review."""
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id_or_brief_id, db_path=path)
    brief_id = rev["brief_id"] if rev else review_id_or_brief_id
    review_id = rev["review_id"] if rev else review_id_or_brief_id

    decisions = list_screening_decisions_db(
        review_id=review_id,
        brief_id=brief_id,
        stage=stage.value if stage else None,
        disposition=disposition.value if disposition else None,
        db_path=path,
    )
    return decisions


@router.post("/reviews/{review_id_or_brief_id}/decisions/{decision_id}/confirm")
async def confirm_decision(
    review_id_or_brief_id: str,
    decision_id: str,
    req: ConfirmDecisionRequest,
    db_path: Optional[str] = None,
):
    """
    Confirm or override an AI-generated screening decision.
    Grounds human audit trail and marks reviewer confirmation.
    """
    path = db_path or DEFAULT_DB_PATH
    existing = get_screening_decision_db(decision_id, db_path=path)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening decision '{decision_id}' not found.",
        )

    updated = update_screening_decision_db(
        decision_id=decision_id,
        disposition=req.disposition.value,
        reviewer_notes=req.reviewer_notes or "",
        reviewer_type=req.reviewer_type.value if req.reviewer_type else ReviewerType.REVIEWER_CONFIRMED.value,
        db_path=path,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update screening decision.",
        )

    new_decision = get_screening_decision_db(decision_id, db_path=path)
    return {
        "status": "confirmed",
        "decision": new_decision,
    }


@router.get("/reviews/{review_id_or_brief_id}/evidence-matrix")
async def get_evidence_matrix(
    review_id_or_brief_id: str,
    db_path: Optional[str] = None,
):
    """Retrieve structured evidence matrix and dialectic contradiction map for included studies."""
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id_or_brief_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id_or_brief_id}' not found.",
        )
    return rev.get("evidence_matrix", {})


@router.get("/reviews/{review_id_or_brief_id}/mermaid", response_class=PlainTextResponse)
async def get_mermaid_flowchart(
    review_id_or_brief_id: str,
    db_path: Optional[str] = None,
):
    """Retrieve raw Mermaid PRISMA 2020 flowchart markdown."""
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id_or_brief_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id_or_brief_id}' not found.",
        )
    return rev.get("mermaid_diagram", "")
