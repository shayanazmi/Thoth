"""
THOTH Project-Scoped Persistent Research Workspace
Phase 5 — Deliverable A: Project-scoped persistence connecting ideas,
briefs, PRISMA review ledgers, evidence matrices, reports, and manuscripts.
"""

from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.memory.db import (
    DEFAULT_DB_PATH,
    associate_artifact_to_project_db,
    delete_project_db,
    get_connection,
    get_idea_history_db,
    get_project_db,
    list_manuscript_exports_db,
    list_manuscript_revisions_db,
    list_manuscripts_db,
    list_projects_db,
    save_project_db,
)


@dataclass
class ResearchProject:
    project_id: str
    title: str
    description: str = ""
    session_id: str = ""
    status: str = "ACTIVE"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "session_id": self.session_id,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ProjectWorkspace:
    project: ResearchProject
    ideas: List[Dict[str, Any]] = field(default_factory=list)
    briefs: List[Dict[str, Any]] = field(default_factory=list)
    prisma_reviews: List[Dict[str, Any]] = field(default_factory=list)
    reports: List[Dict[str, Any]] = field(default_factory=list)
    manuscripts: List[Dict[str, Any]] = field(default_factory=list)
    exports: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project": self.project.to_dict(),
            "ideas": self.ideas,
            "briefs": self.briefs,
            "prisma_reviews": self.prisma_reviews,
            "reports": self.reports,
            "manuscripts": self.manuscripts,
            "exports": self.exports,
        }


def create_project(
    title: str,
    description: str = "",
    session_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> ResearchProject:
    """Create a new research project workspace."""
    pid = project_id or f"proj_{uuid.uuid4().hex[:12]}"
    res = save_project_db(
        project_id=pid,
        title=title,
        description=description,
        session_id=session_id,
        status="ACTIVE",
        metadata=metadata or {},
        db_path=db_path,
    )
    return ResearchProject(
        project_id=res["project_id"],
        title=res["title"],
        description=res["description"],
        session_id=res["session_id"],
        status=res["status"],
        metadata=res["metadata"],
        created_at=res["created_at"],
        updated_at=res["updated_at"],
    )


def get_project(project_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[ResearchProject]:
    """Retrieve a project by its identifier."""
    res = get_project_db(project_id, db_path=db_path)
    if not res:
        return None
    return ResearchProject(
        project_id=res["project_id"],
        title=res["title"],
        description=res.get("description", ""),
        session_id=res.get("session_id", ""),
        status=res.get("status", "ACTIVE"),
        metadata=res.get("metadata", {}),
        created_at=res.get("created_at", ""),
        updated_at=res.get("updated_at", ""),
    )


def list_projects(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> List[ResearchProject]:
    """List projects filtered by optional session_id or status."""
    rows = list_projects_db(session_id=session_id, status=status, db_path=db_path)
    return [
        ResearchProject(
            project_id=r["project_id"],
            title=r["title"],
            description=r.get("description", ""),
            session_id=r.get("session_id", ""),
            status=r.get("status", "ACTIVE"),
            metadata=r.get("metadata", {}),
            created_at=r.get("created_at", ""),
            updated_at=r.get("updated_at", ""),
        )
        for r in rows
    ]


def archive_project(project_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Archive an existing project without deleting data."""
    proj = get_project(project_id, db_path=db_path)
    if not proj:
        return False
    save_project_db(
        project_id=proj.project_id,
        title=proj.title,
        description=proj.description,
        session_id=proj.session_id,
        status="ARCHIVED",
        metadata=proj.metadata,
        db_path=db_path,
    )
    return True


def delete_project(project_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Delete a project record."""
    return delete_project_db(project_id, db_path=db_path)


def associate_artifact(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """
    Associate an existing research artifact with a project.
    Supported types: 'brief', 'idea', 'prisma_review', 'report'.
    """
    proj = get_project(project_id, db_path=db_path)
    if not proj:
        raise ValueError(f"Project '{project_id}' does not exist.")
    return associate_artifact_to_project_db(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        project_id=project_id,
        db_path=db_path,
    )


def verify_project_access(
    project_id: str,
    session_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """
    Verify meaningful project boundaries and access constraints.
    If session_id is provided, ensures the project belongs to the caller's session scope.
    """
    proj = get_project(project_id, db_path=db_path)
    if not proj:
        return False
    if session_id and proj.session_id and proj.session_id != session_id:
        return False
    return True


def load_project_workspace(
    project_id: str,
    session_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> ProjectWorkspace:
    """
    Load the consolidated intellectual workspace connecting ideas, briefs,
    reviews, reports, manuscripts, revisions, and exports.
    """
    proj = get_project(project_id, db_path=db_path)
    if not proj:
        raise ValueError(f"Project '{project_id}' not found.")

    if session_id and proj.session_id and proj.session_id != session_id:
        raise PermissionError(f"Access denied: project '{project_id}' does not belong to session '{session_id}'.")

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 1. Associated Ideas + Lineage
    cursor.execute("SELECT * FROM research_ideas WHERE project_id = ? ORDER BY created_at ASC;", (project_id,))
    idea_rows = cursor.fetchall()
    ideas = []
    for r in idea_rows:
        d = dict(r)
        d["revisions"] = get_idea_history_db(d["idea_id"], db_path=db_path)
        try:
            d["tags"] = json.loads(d.get("tags_json") or "[]")
        except Exception:
            d["tags"] = []
        ideas.append(d)

    # 2. Associated Research Briefs
    cursor.execute("SELECT * FROM research_briefs WHERE project_id = ? ORDER BY updated_at DESC;", (project_id,))
    brief_rows = cursor.fetchall()
    briefs = []
    brief_ids = set()
    for r in brief_rows:
        d = dict(r)
        brief_ids.add(d["brief_id"])
        for jfield in ["objectives_json", "hypotheses_json", "assumptions_json", "selection_criteria_json", "unresolved_questions_json", "counter_evidence_queries_json", "falsification_criteria_json"]:
            k = jfield.replace("_json", "")
            try:
                d[k] = json.loads(d.get(jfield) or "[]")
            except Exception:
                d[k] = []
        briefs.append(d)

    # 3. Associated PRISMA Reviews
    # Either linked directly via project_id OR associated via briefs belonging to this project
    review_rows = []
    cursor.execute("SELECT * FROM prisma_reviews WHERE project_id = ? ORDER BY updated_at DESC;", (project_id,))
    review_rows.extend(cursor.fetchall())
    if brief_ids:
        placeholders = ",".join("?" for _ in brief_ids)
        cursor.execute(f"SELECT * FROM prisma_reviews WHERE brief_id IN ({placeholders}) AND (project_id IS NULL OR project_id != ?) ORDER BY updated_at DESC;", (*brief_ids, project_id))
        review_rows.extend(cursor.fetchall())

    seen_reviews = set()
    reviews = []
    review_ids = set()
    for r in review_rows:
        d = dict(r)
        if d["review_id"] in seen_reviews:
            continue
        seen_reviews.add(d["review_id"])
        review_ids.add(d["review_id"])
        for fld in ["protocol_json", "flow_counts_json", "evidence_matrix_json"]:
            k = fld.replace("_json", "")
            try:
                d[k] = json.loads(d.get(fld) or "{}")
            except Exception:
                d[k] = {}
        reviews.append(d)

    # 4. Associated Reports
    cursor.execute("SELECT * FROM reports WHERE project_id = ? ORDER BY created_at DESC;", (project_id,))
    reports = [dict(r) for r in cursor.fetchall()]

    # 5. Manuscripts and Revisions
    manuscript_rows = list_manuscripts_db(project_id=project_id, db_path=db_path)
    manuscripts = []
    all_exports = []
    for m in manuscript_rows:
        mid = m["manuscript_id"]
        m["revisions"] = list_manuscript_revisions_db(mid, db_path=db_path)
        exports = list_manuscript_exports_db(mid, db_path=db_path)
        m["exports"] = exports
        all_exports.extend(exports)
        manuscripts.append(m)

    return ProjectWorkspace(
        project=proj,
        ideas=ideas,
        briefs=briefs,
        prisma_reviews=reviews,
        reports=reports,
        manuscripts=manuscripts,
        exports=all_exports,
    )
