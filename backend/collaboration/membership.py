"""
THOTH Project Collaboration & Role-Based Access Control (RBAC)
Phase 6 — Deliverable C: Multi-tenant project collaboration and access boundaries.

Defines roles (OWNER, EDITOR, VIEWER), fine-grained project permissions,
and boundary verification helpers for multi-tenant collaborative research.
"""

from __future__ import annotations

import datetime
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from backend.core.logging import get_logger
from backend.memory.db import (
    DEFAULT_DB_PATH,
    add_project_member_db,
    delete_project_member_db,
    get_project_db,
    get_project_member_db,
    list_project_members_db,
)

logger = get_logger("CollaborationMembership")


class ProjectRole(str, Enum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class ProjectPermission(str, Enum):
    READ_PROJECT = "READ_PROJECT"
    EDIT_PROJECT = "EDIT_PROJECT"
    MANAGE_MEMBERS = "MANAGE_MEMBERS"
    CREATE_MANUSCRIPT = "CREATE_MANUSCRIPT"
    EDIT_MANUSCRIPT = "EDIT_MANUSCRIPT"
    EXPORT_MANUSCRIPT = "EXPORT_MANUSCRIPT"
    RUN_RESEARCH = "RUN_RESEARCH"
    DELETE_PROJECT = "DELETE_PROJECT"


# Role-to-Permissions Mapping
ROLE_PERMISSIONS: Dict[ProjectRole, Set[ProjectPermission]] = {
    ProjectRole.OWNER: {
        ProjectPermission.READ_PROJECT,
        ProjectPermission.EDIT_PROJECT,
        ProjectPermission.MANAGE_MEMBERS,
        ProjectPermission.CREATE_MANUSCRIPT,
        ProjectPermission.EDIT_MANUSCRIPT,
        ProjectPermission.EXPORT_MANUSCRIPT,
        ProjectPermission.RUN_RESEARCH,
        ProjectPermission.DELETE_PROJECT,
    },
    ProjectRole.EDITOR: {
        ProjectPermission.READ_PROJECT,
        ProjectPermission.EDIT_PROJECT,
        ProjectPermission.CREATE_MANUSCRIPT,
        ProjectPermission.EDIT_MANUSCRIPT,
        ProjectPermission.EXPORT_MANUSCRIPT,
        ProjectPermission.RUN_RESEARCH,
    },
    ProjectRole.VIEWER: {
        ProjectPermission.READ_PROJECT,
        ProjectPermission.EXPORT_MANUSCRIPT,
    },
}


class ProjectMember(BaseModel):
    membership_id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:10]}")
    project_id: str
    user_id: str
    role: ProjectRole = ProjectRole.VIEWER
    invited_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    accepted_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def can_user_perform(role: ProjectRole | str, permission: ProjectPermission) -> bool:
    """Checks whether the given role has permission to execute an action."""
    try:
        r = ProjectRole(role) if isinstance(role, str) else role
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(r, set())


def add_project_member(
    project_id: str,
    user_id: str,
    role: str = "VIEWER",
    inviter_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> ProjectMember:
    """
    Adds or updates a collaborator in a research project.
    If inviter_id is specified, verifies that inviter has MANAGE_MEMBERS permission.
    """
    proj = get_project_db(project_id, db_path=db_path)
    if not proj:
        raise ValueError(f"Project '{project_id}' not found.")

    if inviter_id:
        has_perm, inv_role = verify_project_access(
            project_id=project_id,
            user_id=inviter_id,
            required_permission=ProjectPermission.MANAGE_MEMBERS,
            db_path=db_path,
        )
        if not has_perm:
            raise PermissionError(f"User '{inviter_id}' lacks permission to manage members in project '{project_id}'.")

    # Validate role
    role_enum = ProjectRole(role.upper())
    membership_id = f"mem_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    rec = add_project_member_db(
        membership_id=membership_id,
        project_id=project_id,
        user_id=user_id,
        role=role_enum.value,
        invited_at=now_iso,
        accepted_at=now_iso,
        db_path=db_path,
    )

    return ProjectMember(
        membership_id=rec["membership_id"],
        project_id=rec["project_id"],
        user_id=rec["user_id"],
        role=ProjectRole(rec["role"]),
        invited_at=rec.get("invited_at", now_iso),
        accepted_at=rec.get("accepted_at"),
        created_at=rec.get("created_at", now_iso),
    )


def get_project_member(
    project_id: str,
    user_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[ProjectMember]:
    rec = get_project_member_db(project_id, user_id, db_path=db_path)
    if not rec:
        return None
    return ProjectMember(
        membership_id=rec["membership_id"],
        project_id=rec["project_id"],
        user_id=rec["user_id"],
        role=ProjectRole(rec["role"]),
        invited_at=rec.get("invited_at", ""),
        accepted_at=rec.get("accepted_at"),
        created_at=rec.get("created_at", ""),
    )


def list_project_members(
    project_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> List[ProjectMember]:
    rows = list_project_members_db(project_id, db_path=db_path)
    return [
        ProjectMember(
            membership_id=r["membership_id"],
            project_id=r["project_id"],
            user_id=r["user_id"],
            role=ProjectRole(r["role"]),
            invited_at=r.get("invited_at", ""),
            accepted_at=r.get("accepted_at"),
            created_at=r.get("created_at", ""),
        )
        for r in rows
    ]


def remove_project_member(
    project_id: str,
    user_id: str,
    remover_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Removes a member from a project with permission verification."""
    proj = get_project_db(project_id, db_path=db_path)
    if not proj:
        raise ValueError(f"Project '{project_id}' not found.")

    # Project owner cannot be removed as a member
    if proj.get("session_id") == user_id:
        raise ValueError(f"Cannot remove project owner '{user_id}' from project '{project_id}'.")

    if remover_id and remover_id != user_id:
        has_perm, _ = verify_project_access(
            project_id=project_id,
            user_id=remover_id,
            required_permission=ProjectPermission.MANAGE_MEMBERS,
            db_path=db_path,
        )
        if not has_perm:
            raise PermissionError(f"User '{remover_id}' lacks permission to remove members from project '{project_id}'.")

    return delete_project_member_db(project_id, user_id, db_path=db_path)


def verify_project_access(
    project_id: str,
    user_id: str,
    required_permission: ProjectPermission,
    db_path: str = DEFAULT_DB_PATH,
) -> Tuple[bool, Optional[ProjectRole]]:
    """
    Verifies that user_id has the required permission in project_id.
    Returns (has_access: bool, user_role: Optional[ProjectRole]).
    """
    proj = get_project_db(project_id, db_path=db_path)
    if not proj:
        return False, None

    # Project creator / owner via session_id has OWNER role
    if proj.get("session_id") == user_id:
        return True, ProjectRole.OWNER

    # Check project_members table
    member = get_project_member(project_id, user_id, db_path=db_path)
    if not member:
        return False, None

    has_perm = can_user_perform(member.role, required_permission)
    return has_perm, member.role
