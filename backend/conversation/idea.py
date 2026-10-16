import uuid
import datetime
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.memory.db import (
    save_idea_db,
    get_idea_db,
    list_ideas_db,
    get_idea_history_db,
    DEFAULT_DB_PATH,
)


class IdeaStatus(str):
    TENTATIVE = "TENTATIVE"
    PROMOTED = "PROMOTED"
    REVISED = "REVISED"
    ABANDONED = "ABANDONED"


class ResearchIdea(BaseModel):
    idea_id: str = Field(default_factory=lambda: f"idea-{uuid.uuid4().hex[:12]}")
    session_id: str = Field(default="")
    title: str = Field(..., description="Short descriptive title of the idea")
    description: str = Field(default="", description="Detailed context or exploratory rationale")
    hypothesis: str = Field(..., description="Testable scientific or epistemic hypothesis")
    status: str = Field(default=IdeaStatus.TENTATIVE, description="TENTATIVE, PROMOTED, REVISED, ABANDONED")
    thinker_id: Optional[str] = Field(default=None, description="Originating or primary sparring thinker ID")
    thinker_critique: Optional[str] = Field(default=None, description="Substantive critique or dialectic feedback")
    unresolved_objections: List[str] = Field(default_factory=list, description="Open counter-arguments or falsification criteria")
    parent_idea_id: Optional[str] = Field(default=None, description="Parent idea ID if this is a revision")
    revision_version: int = Field(default=1, description="Sequential version in revision lineage")
    revision_notes: Optional[str] = Field(default=None, description="Rationale for this revision")
    brief_id: Optional[str] = Field(default=None, description="Linked research brief ID if promoted to brief")
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchIdea":
        return cls(**data)


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    if db_path is not None:
        return db_path
    return DEFAULT_DB_PATH


def create_tentative_idea(
    title: str,
    hypothesis: str,
    description: str = "",
    session_id: str = "",
    thinker_id: Optional[str] = None,
    thinker_critique: Optional[str] = None,
    unresolved_objections: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> ResearchIdea:
    """
    Formulate a tentative research idea from dialogue or thinker sparring.
    Crucial guarantee: All new ideas begin in TENTATIVE status and are NOT persisted
    as approved research artifacts until explicit user consent is given.
    """
    clean_title = (title or "").strip()
    clean_hypothesis = (hypothesis or "").strip()
    if not clean_title:
        clean_title = "Untitled Research Idea"
    if not clean_hypothesis:
        clean_hypothesis = "Hypothesis under active exploratory formulation."

    idea = ResearchIdea(
        session_id=session_id,
        title=clean_title,
        description=description.strip(),
        hypothesis=clean_hypothesis,
        status=IdeaStatus.TENTATIVE,
        thinker_id=thinker_id.strip() if thinker_id else None,
        thinker_critique=thinker_critique.strip() if thinker_critique else None,
        unresolved_objections=list(unresolved_objections or []),
        revision_version=1,
    )
    resolved_db = _resolve_db_path(db_path)
    save_idea_db(idea.to_dict(), db_path=resolved_db)
    return idea


def promote_idea_to_artifact(
    idea_id: str,
    user_approved: bool = False,
    db_path: Optional[str] = None,
) -> Tuple[bool, Optional[ResearchIdea], str]:
    """
    Explicit promotion barrier: A tentative idea cannot become an active, persistent
    research artifact without explicit user approval.
    """
    resolved_db = _resolve_db_path(db_path)
    data = get_idea_db(idea_id, db_path=resolved_db)
    if not data:
        return False, None, f"Research idea '{idea_id}' not found."

    idea = ResearchIdea.from_dict(data)

    if not user_approved:
        return (
            False,
            idea,
            f"Promotion Barrier: Explicit user approval is required before promoting idea '{idea_id}' into persistent project storage.",
        )

    if idea.status == IdeaStatus.PROMOTED:
        return True, idea, f"Idea '{idea_id}' is already promoted."

    if idea.status == IdeaStatus.ABANDONED:
        return False, idea, f"Cannot promote abandoned idea '{idea_id}'."

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    idea.status = IdeaStatus.PROMOTED
    idea.updated_at = now_iso

    save_idea_db(idea.to_dict(), db_path=resolved_db)
    return True, idea, f"Idea '{idea_id}' successfully promoted to persistent research artifact."


def revise_idea(
    idea_id: str,
    new_hypothesis: str,
    revision_notes: str = "",
    new_title: Optional[str] = None,
    thinker_id: Optional[str] = None,
    thinker_critique: Optional[str] = None,
    unresolved_objections: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> Tuple[bool, Optional[ResearchIdea], str]:
    """
    Traceable revision: Ideas and hypotheses must never be silently overwritten.
    Creates a new revision child pointing to the parent idea, while marking the
    parent idea as REVISED, preserving the full immutable intellectual lineage.
    """
    resolved_db = _resolve_db_path(db_path)
    data = get_idea_db(idea_id, db_path=resolved_db)
    if not data:
        return False, None, f"Parent research idea '{idea_id}' not found."

    parent = ResearchIdea.from_dict(data)
    if parent.status == IdeaStatus.ABANDONED:
        return False, None, f"Cannot revise abandoned idea '{idea_id}'."

    clean_hypo = (new_hypothesis or "").strip()
    if not clean_hypo:
        return False, None, "Revision requires a non-empty hypothesis."

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1. Update parent to REVISED (preserving its historical hypothesis unchanged)
    parent.status = IdeaStatus.REVISED
    parent.updated_at = now_iso
    save_idea_db(parent.to_dict(), db_path=resolved_db)

    # 2. Formulate child revision
    child_status = IdeaStatus.PROMOTED if parent.status in (IdeaStatus.PROMOTED, IdeaStatus.REVISED) else IdeaStatus.TENTATIVE
    active_objections = unresolved_objections if unresolved_objections is not None else list(parent.unresolved_objections)

    child = ResearchIdea(
        session_id=parent.session_id,
        title=(new_title or parent.title).strip(),
        description=parent.description,
        hypothesis=clean_hypo,
        status=child_status,
        thinker_id=thinker_id or parent.thinker_id,
        thinker_critique=thinker_critique or parent.thinker_critique,
        unresolved_objections=active_objections,
        parent_idea_id=parent.idea_id,
        revision_version=parent.revision_version + 1,
        revision_notes=(revision_notes or "").strip(),
        brief_id=parent.brief_id,
        created_at=now_iso,
        updated_at=now_iso,
    )

    save_idea_db(child.to_dict(), db_path=resolved_db)
    return True, child, f"Idea revision v{child.revision_version} created successfully (parent: {parent.idea_id})."


def abandon_idea(
    idea_id: str,
    reason: str = "",
    db_path: Optional[str] = None,
) -> Tuple[bool, Optional[ResearchIdea], str]:
    """
    Explicitly shelve or abandon an idea without destroying its historical record.
    """
    resolved_db = _resolve_db_path(db_path)
    data = get_idea_db(idea_id, db_path=resolved_db)
    if not data:
        return False, None, f"Research idea '{idea_id}' not found."

    idea = ResearchIdea.from_dict(data)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    idea.status = IdeaStatus.ABANDONED
    if reason:
        idea.revision_notes = f"Abandoned: {reason.strip()}"
    idea.updated_at = now_iso

    save_idea_db(idea.to_dict(), db_path=resolved_db)
    return True, idea, f"Idea '{idea_id}' marked as abandoned."


def attach_idea_to_brief(
    idea_id: str,
    brief_id: str,
    db_path: Optional[str] = None,
) -> Tuple[bool, Optional[ResearchIdea], str]:
    """
    Link a promoted idea to a research brief.
    Enforces that unapproved (tentative) ideas cannot be linked to formal research briefs.
    """
    resolved_db = _resolve_db_path(db_path)
    data = get_idea_db(idea_id, db_path=resolved_db)
    if not data:
        return False, None, f"Research idea '{idea_id}' not found."

    idea = ResearchIdea.from_dict(data)
    if idea.status == IdeaStatus.TENTATIVE:
        return (
            False,
            idea,
            f"Promotion Barrier: Idea '{idea_id}' is tentative. It must be promoted with user approval before attaching to a research brief.",
        )

    idea.brief_id = brief_id
    idea.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_idea_db(idea.to_dict(), db_path=resolved_db)
    return True, idea, f"Idea '{idea_id}' successfully attached to brief '{brief_id}'."


def get_idea(idea_id: str, db_path: Optional[str] = None) -> Optional[ResearchIdea]:
    resolved_db = _resolve_db_path(db_path)
    data = get_idea_db(idea_id, db_path=resolved_db)
    return ResearchIdea.from_dict(data) if data else None


def list_ideas(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> List[ResearchIdea]:
    resolved_db = _resolve_db_path(db_path)
    rows = list_ideas_db(session_id=session_id, status=status, limit=limit, db_path=resolved_db)
    return [ResearchIdea.from_dict(r) for r in rows]


def get_idea_history(idea_id: str, db_path: Optional[str] = None) -> List[ResearchIdea]:
    resolved_db = _resolve_db_path(db_path)
    rows = get_idea_history_db(idea_id, db_path=resolved_db)
    return [ResearchIdea.from_dict(r) for r in rows]
