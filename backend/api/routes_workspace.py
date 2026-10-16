"""
THOTH Workspace & Manuscript Engine REST API Router
Phase 5: Persistent Research Workspace, Manuscript Evolution, Multi-Format Export,
and Interactive Evidence Matrix Traceability.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.core.logging import get_logger
from backend.workspace.project import (
    ResearchProject,
    ProjectWorkspace,
    create_project,
    get_project,
    list_projects,
    archive_project,
    delete_project,
    associate_artifact,
    load_project_workspace,
    verify_project_access,
)
from backend.workspace.manuscript import (
    create_manuscript,
    create_manuscript_from_brief_and_review,
    save_manuscript_revision,
    get_manuscript,
    get_manuscript_revision,
    list_manuscripts,
    list_manuscript_revisions,
    propose_claim_qualifications_from_evidence,
)
from backend.workspace.exporter import (
    ExportFormat,
    ExportResult,
    export_manuscript,
)
from backend.workspace.traceability import (
    drill_down_study_record,
    get_flow_node_records,
    get_claim_traceability,
)
from backend.memory.db import get_manuscript_export_db, list_manuscript_exports_db

logger = get_logger("WorkspaceAPI")
router = APIRouter(prefix="/api", tags=["Workspace & Manuscripts"])


# ==========================================
# Pydantic Schemas
# ==========================================

class ProjectCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Title of research project")
    description: str = Field("", description="Detailed scope or description")
    session_id: str = Field("", description="Session context / owner")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArtifactAssociationRequest(BaseModel):
    artifact_type: str = Field(..., description="One of: brief, idea, prisma_review, report")
    artifact_id: str = Field(..., min_length=1, description="Artifact identifier")


class ManuscriptCreateRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    brief_id: Optional[str] = None
    review_id: Optional[str] = None
    sections: Optional[Dict[str, Any]] = None
    claims: Optional[List[Dict[str, Any]]] = None
    references: Optional[List[Dict[str, Any]]] = None
    evidence_matrix: Optional[Dict[str, Any]] = None
    author_notes: str = "Initial manuscript draft"


class ManuscriptFromReviewRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    brief_id: str = Field(..., min_length=1)
    review_id: str = Field(..., min_length=1)
    title: Optional[str] = None


class ManuscriptRevisionSaveRequest(BaseModel):
    title: str = Field(..., min_length=1)
    sections: Dict[str, Any] = Field(default_factory=dict)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    references: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_matrix: Optional[Dict[str, Any]] = None
    author_notes: str = ""
    base_version: Optional[int] = None


class QualificationProposalsRequest(BaseModel):
    new_evidence: List[Dict[str, Any]] = Field(..., description="List of new evidence findings to test claims against")


class ManuscriptExportRequest(BaseModel):
    format: str = Field(..., description="markdown, latex, bibtex, or html")
    version: Optional[int] = None


# ==========================================
# 1. Projects Endpoints (Deliverable A)
# ==========================================

@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def api_create_project(req: ProjectCreateRequest):
    try:
        proj = create_project(
            title=req.title,
            description=req.description,
            session_id=req.session_id,
            metadata=req.metadata,
        )
        return {"status": "success", "project": proj.to_dict()}
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
async def api_list_projects(
    session_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    try:
        projects = list_projects(session_id=session_id, status=status_filter)
        return {"status": "success", "projects": [p.to_dict() for p in projects]}
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}")
async def api_get_project_workspace(
    project_id: str,
    session_id: Optional[str] = Query(None),
):
    try:
        workspace = load_project_workspace(project_id=project_id, session_id=session_id)
        return {"status": "success", "workspace": workspace.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error loading project workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/associate")
async def api_associate_artifact(project_id: str, req: ArtifactAssociationRequest):
    try:
        ok = associate_artifact(
            project_id=project_id,
            artifact_type=req.artifact_type,
            artifact_id=req.artifact_id,
        )
        return {"status": "success", "associated": ok}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error associating artifact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/archive")
async def api_archive_project(project_id: str):
    ok = archive_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return {"status": "success", "archived": True}


@router.delete("/projects/{project_id}")
async def api_delete_project(project_id: str):
    ok = delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return {"status": "success", "deleted": True}


# ==========================================
# 2. Manuscripts & Revisions (Deliverable B)
# ==========================================

@router.post("/manuscripts", status_code=status.HTTP_201_CREATED)
async def api_create_manuscript(req: ManuscriptCreateRequest):
    try:
        ms, rev = create_manuscript(
            project_id=req.project_id,
            title=req.title,
            brief_id=req.brief_id,
            review_id=req.review_id,
            initial_sections=req.sections,
            initial_claims=req.claims,
            initial_references=req.references,
            initial_evidence_matrix=req.evidence_matrix,
            author_notes=req.author_notes,
        )
        return {
            "status": "success",
            "manuscript": ms.to_dict(),
            "revision": rev.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error creating manuscript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manuscripts/from-review", status_code=status.HTTP_201_CREATED)
async def api_create_manuscript_from_review(req: ManuscriptFromReviewRequest):
    try:
        ms, rev = create_manuscript_from_brief_and_review(
            project_id=req.project_id,
            brief_id=req.brief_id,
            review_id=req.review_id,
            title=req.title,
        )
        return {
            "status": "success",
            "manuscript": ms.to_dict(),
            "revision": rev.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating manuscript from review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manuscripts")
async def api_list_manuscripts(project_id: Optional[str] = Query(None)):
    try:
        items = list_manuscripts(project_id=project_id)
        return {"status": "success", "manuscripts": [m.to_dict() for m in items]}
    except Exception as e:
        logger.error(f"Error listing manuscripts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manuscripts/{manuscript_id}")
async def api_get_manuscript(manuscript_id: str):
    ms = get_manuscript(manuscript_id)
    if not ms:
        raise HTTPException(status_code=404, detail=f"Manuscript '{manuscript_id}' not found.")
    rev = get_manuscript_revision(manuscript_id, ms.current_version)
    return {
        "status": "success",
        "manuscript": ms.to_dict(),
        "current_revision": rev.to_dict() if rev else None,
    }


@router.get("/manuscripts/{manuscript_id}/revisions")
async def api_list_revisions(manuscript_id: str):
    ms = get_manuscript(manuscript_id)
    if not ms:
        raise HTTPException(status_code=404, detail=f"Manuscript '{manuscript_id}' not found.")
    revs = list_manuscript_revisions(manuscript_id)
    return {"status": "success", "revisions": revs}


@router.get("/manuscripts/{manuscript_id}/revisions/{version}")
async def api_get_revision(manuscript_id: str, version: int):
    rev = get_manuscript_revision(manuscript_id, version=version)
    if not rev:
        raise HTTPException(status_code=404, detail=f"Manuscript '{manuscript_id}' version {version} not found.")
    return {"status": "success", "revision": rev.to_dict()}


@router.post("/manuscripts/{manuscript_id}/revisions", status_code=status.HTTP_201_CREATED)
async def api_save_revision(manuscript_id: str, req: ManuscriptRevisionSaveRequest):
    try:
        rev = save_manuscript_revision(
            manuscript_id=manuscript_id,
            title=req.title,
            sections=req.sections,
            claims=req.claims,
            references=req.references,
            evidence_matrix=req.evidence_matrix,
            author_notes=req.author_notes,
            base_version=req.base_version,
        )
        return {"status": "success", "revision": rev.to_dict()}
    except ValueError as e:
        # Detect conflict or stale edit
        if "Stale edit conflict" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving manuscript revision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manuscripts/{manuscript_id}/qualifications/propose")
async def api_propose_qualifications(manuscript_id: str, req: QualificationProposalsRequest):
    try:
        proposals = propose_claim_qualifications_from_evidence(
            manuscript_id=manuscript_id,
            new_evidence_items=req.new_evidence,
        )
        return {"status": "success", "proposals": proposals}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error proposing qualifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 3. Multi-Format Exports (Deliverable C)
# ==========================================

@router.post("/manuscripts/{manuscript_id}/export")
async def api_export_manuscript(manuscript_id: str, req: ManuscriptExportRequest):
    try:
        res = export_manuscript(
            manuscript_id=manuscript_id,
            format_type=req.format,
            version=req.version,
            save_to_db=True,
        )
        return {"status": "success", "export": res.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting manuscript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manuscripts/{manuscript_id}/exports")
async def api_list_exports(
    manuscript_id: str,
    version: Optional[int] = Query(None),
    format_filter: Optional[str] = Query(None, alias="format"),
):
    try:
        items = list_manuscript_exports_db(
            manuscript_id=manuscript_id,
            version=version,
            format=format_filter,
        )
        return {"status": "success", "exports": items}
    except Exception as e:
        logger.error(f"Error listing exports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exports/{export_id}")
async def api_get_export(export_id: str):
    res = get_manuscript_export_db(export_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Export artifact '{export_id}' not found.")
    return {"status": "success", "export": res}


# ==========================================
# 4. Interactive Traceability (Deliverable D)
# ==========================================

@router.get("/traceability/studies/{study_id}")
async def api_drill_down_study(
    study_id: str,
    review_id: Optional[str] = Query(None),
    manuscript_id: Optional[str] = Query(None),
):
    detail = drill_down_study_record(study_id=study_id, review_id=review_id, manuscript_id=manuscript_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Study record '{study_id}' not found.")
    return {"status": "success", "study": detail.to_dict()}


@router.get("/traceability/flow-nodes/{review_id}/{flow_node_id}")
async def api_drill_down_flow_node(review_id: str, flow_node_id: str):
    try:
        res = get_flow_node_records(flow_node_id=flow_node_id, review_id=review_id)
        return {"status": "success", "drill_down": res.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error drilling down flow node: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traceability/claims/{claim_id}")
async def api_get_claim_traceability(
    claim_id: str,
    manuscript_id: Optional[str] = Query(None),
):
    try:
        res = get_claim_traceability(claim_id=claim_id, manuscript_id=manuscript_id)
        return {"status": "success", "traceability": res}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving claim traceability: {e}")
        raise HTTPException(status_code=500, detail=str(e))
