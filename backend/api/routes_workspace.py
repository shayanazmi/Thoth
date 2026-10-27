"""
THOTH Workspace & Manuscript Engine REST API Router
Phase 5: Persistent Research Workspace, Manuscript Evolution, Multi-Format Export,
and Interactive Evidence Matrix Traceability.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator

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
from backend.memory.db import DEFAULT_DB_PATH, get_manuscript_export_db, list_manuscript_exports_db
from backend.collaboration.membership import (
    ProjectRole,
    ProjectPermission,
    add_project_member,
    list_project_members,
    remove_project_member,
    verify_project_access as verify_collaboration_access,
)
from backend.collaboration.sync import (
    replay_sync_outbox,
    get_project_sync_status,
)

logger = get_logger("WorkspaceAPI")
router = APIRouter(prefix="/api", tags=["Workspace & Manuscripts"])


# ==========================================
# Pydantic Schemas
# ==========================================

class ProjectCreateRequest(BaseModel):
    """Vision §10: forgive callers who use the common field name.
    Accept either ``title`` (canonical) or ``name`` (alias) on input.
    """
    title: str = Field(..., min_length=1, description="Title of research project")
    description: str = Field("", description="Detailed scope or description")
    session_id: str = Field("", description="Session context / owner")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _accept_name_alias(cls, data):
        if isinstance(data, dict) and "title" not in data and "name" in data:
            return {**data, "title": data["name"]}
        return data


class ProjectMemberAddRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="Collaborator user ID")
    role: str = Field("VIEWER", description="OWNER, EDITOR, or VIEWER")
    inviter_id: Optional[str] = None


class SyncReplayRequest(BaseModel):
    limit: int = Field(50, ge=1, le=500)


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
    format: str = Field(..., description="markdown, latex, bibtex, html, or pdf")
    version: Optional[int] = None
    engine: str = Field("auto", description="PDF engine: auto, latex/pdflatex, or reportlab")


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
        # A chat is a thread until a hypothesis is accepted (docs/features/02).
        from backend.conversation.projects import kind
        return {"status": "success", "projects": [{**p.to_dict(), "kind": kind(p.project_id)} for p in projects]}
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
async def api_delete_project(project_id: str, confirm: bool = Query(False)):
    """Deletes the project and everything it holds (docs/features/02 § Retention). Without ?confirm=true it
    deletes nothing and answers 409 with the counts the researcher must see first."""
    from backend.conversation import projects as project_state
    if not project_state.exists(project_id):
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    if not confirm:
        raise HTTPException(status_code=409, detail=project_state.footprint(project_id))
    return {"status": "success", "deleted": True, "removed": project_state.delete(project_id)}


# ==========================================
# 1.1 Project Collaboration & Synchronization (Phase 6 Deliverable C)
# ==========================================

@router.post("/projects/{project_id}/members", status_code=status.HTTP_201_CREATED)
async def api_add_project_member(project_id: str, req: ProjectMemberAddRequest):
    try:
        member = add_project_member(
            project_id=project_id,
            user_id=req.user_id,
            role=req.role,
            inviter_id=req.inviter_id,
        )
        return {"status": "success", "member": member.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding project member: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/members")
async def api_list_project_members(project_id: str):
    try:
        members = list_project_members(project_id)
        return {"status": "success", "members": [m.to_dict() for m in members]}
    except Exception as e:
        logger.error(f"Error listing project members: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}/members/{user_id}")
async def api_remove_project_member(
    project_id: str,
    user_id: str,
    remover_id: Optional[str] = Query(None),
):
    try:
        ok = remove_project_member(project_id=project_id, user_id=user_id, remover_id=remover_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Member '{user_id}' not found in project '{project_id}'.")
        return {"status": "success", "removed": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing project member: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/sync/status")
async def api_get_project_sync_status(project_id: str):
    try:
        status_info = get_project_sync_status(project_id=project_id)
        return {"status": "success", "sync": status_info}
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/sync/replay")
async def api_replay_project_sync(project_id: str, req: SyncReplayRequest):
    try:
        replay_res = replay_sync_outbox(
            supabase_client=None,  # Offline-first default or injected provider
            project_id=project_id,
            limit=req.limit,
        )
        return {"status": "success", "replay": replay_res}
    except Exception as e:
        logger.error(f"Error replaying outbox sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))



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


@router.get("/manuscripts/journal-presets")
async def api_list_journal_presets():
    """List all supported academic publisher presets, documentclasses, and venue guidelines."""
    from backend.workspace.journal_formatter import PRESET_CATALOG
    presets = [meta.to_dict() for meta in PRESET_CATALOG.values()]
    return {"status": "success", "presets": presets}


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
            pdf_engine=req.engine,
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
async def api_get_export(export_id: str, db_path: Optional[str] = Query(None)):
    path = db_path or DEFAULT_DB_PATH
    res = get_manuscript_export_db(export_id, db_path=path)
    if not res:
        raise HTTPException(status_code=404, detail=f"Export artifact '{export_id}' not found.")
    return {"status": "success", "export": res}


@router.get("/exports/{export_id}/download")
async def api_download_export(export_id: str, db_path: Optional[str] = Query(None)):
    import base64
    from fastapi.responses import Response
    path = db_path or DEFAULT_DB_PATH
    res = get_manuscript_export_db(export_id, db_path=path)
    if not res:
        raise HTTPException(status_code=404, detail=f"Export artifact '{export_id}' not found.")

    fmt = res["format"].lower()
    meta = res.get("metadata") or {}
    filename = meta.get("filename") or f"{export_id}.{fmt}"

    if fmt == "pdf":
        raw_b64 = res["content"]
        try:
            pdf_bytes = base64.b64decode(raw_b64)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to decode binary PDF: {e}")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    elif fmt == "html":
        return Response(
            content=res["content"],
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        return Response(
            content=res["content"],
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


# ==========================================
# 3.1 Automated Journal Submission Engine (Phase 7 Deliverable B)
# ==========================================

class JournalSubmissionRequest(BaseModel):
    preset: str = Field(..., description="Target journal preset: acm, ieee, nature, neurips")
    version: Optional[int] = Field(default=None, description="Manuscript revision version. Defaults to latest.")
    anonymize: bool = Field(default=False, description="Enable double-blind author and affiliation suppression.")


@router.post("/manuscripts/{manuscript_id}/journal-submission")
async def api_create_journal_submission(
    manuscript_id: str,
    req: JournalSubmissionRequest,
    db_path: Optional[str] = Query(None),
):
    """
    Generate an authoritative journal submission package (.zip) for ACM, IEEE, Nature, or NeurIPS.
    Includes customized LaTeX source, verified BibTeX, publisher compliance checklist, and compiled PDF.
    """
    path = db_path or DEFAULT_DB_PATH
    from backend.workspace.journal_formatter import build_journal_submission_package
    try:
        pkg = build_journal_submission_package(
            manuscript_id=manuscript_id,
            preset_name=req.preset,
            version=req.version,
            anonymize=req.anonymize,
            db_path=path,
        )
        return {"status": "success", "submission": pkg}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating journal submission package: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manuscripts/{manuscript_id}/journal-submissions")
async def api_list_manuscript_journal_submissions(
    manuscript_id: str,
    db_path: Optional[str] = Query(None),
):
    """List historical journal submission packages generated for a manuscript."""
    path = db_path or DEFAULT_DB_PATH
    from backend.workspace.journal_formatter import list_journal_submissions_db
    submissions = list_journal_submissions_db(manuscript_id=manuscript_id, db_path=path)
    return {"status": "success", "submissions": submissions}


@router.get("/submissions/{submission_id}")
async def api_get_journal_submission(
    submission_id: str,
    db_path: Optional[str] = Query(None),
):
    """Retrieve details and checklist for a specific journal submission package."""
    path = db_path or DEFAULT_DB_PATH
    from backend.workspace.journal_formatter import get_journal_submission_db
    sub = get_journal_submission_db(submission_id, db_path=path)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Submission package '{submission_id}' not found.")
    return {"status": "success", "submission": sub}


@router.get("/submissions/{submission_id}/download")
async def api_download_journal_submission_zip(
    submission_id: str,
    db_path: Optional[str] = Query(None),
):
    """Download the full journal submission ZIP archive containing .tex, .bib, checklist, and .pdf."""
    path = db_path or DEFAULT_DB_PATH
    from backend.workspace.journal_formatter import get_journal_submission_db
    sub = get_journal_submission_db(submission_id, db_path=path)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Submission package '{submission_id}' not found.")

    pkg_filename = sub.get("package_filename", f"{submission_id}.zip")
    import base64
    disk_path = os.path.join(os.path.dirname(os.path.abspath(path)), "..", "vault", "submissions", pkg_filename)

    if os.path.exists(disk_path):
        with open(disk_path, "rb") as f:
            zip_bytes = f.read()
    else:
        # Re-generate package on the fly
        from backend.workspace.journal_formatter import build_journal_submission_package
        pkg = build_journal_submission_package(
            manuscript_id=sub["manuscript_id"],
            preset_name=sub["preset"],
            version=sub["version"],
            anonymize=bool(sub.get("is_anonymized")),
            db_path=path,
        )
        zip_bytes = base64.b64decode(pkg["zip_base64"])

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{pkg_filename}"'},
    )




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


# ==========================================
# 5. Project Literature Map (Phase 7 Deliverable)
# ==========================================

@router.get("/projects/{project_id}/literature-map")
async def api_get_project_literature_map(
    project_id: str,
    db_path: Optional[str] = Query(None),
):
    """Retrieve aggregated literature clusters and citation networks across all reviews in a project."""
    path = db_path or DEFAULT_DB_PATH
    from backend.memory.db import get_project_literature_map_db, get_project_db
    proj = get_project_db(project_id, db_path=path)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    lit_map = get_project_literature_map_db(project_id, db_path=path)
    return {"status": "success", "literature_map": lit_map}

