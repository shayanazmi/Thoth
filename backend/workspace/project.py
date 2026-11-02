# Thoth · Developed by Shayan Azmi
"""Project records: create, look up and list the threads and projects shown in the sidebar."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

def _path(db_path: Optional[str]) -> str:
    """The DB path at call time: a default bound at import time would point at whichever database was
    configured when this module was first imported."""
    from backend.memory import db as _db
    return db_path or _db.DEFAULT_DB_PATH


from backend.memory.db import list_projects_db, save_project_db


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


def create_project(
    title: str,
    description: str = "",
    session_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> ResearchProject:
    """Create a new research project workspace."""
    db_path = _path(db_path)
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


def list_projects(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[ResearchProject]:
    """List projects filtered by optional session_id or status."""
    db_path = _path(db_path)
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
