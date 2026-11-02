# Thoth · Developed by Shayan Azmi
import uuid
import datetime
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.memory.db import (
    save_idea_db,
    get_idea_db,
    list_ideas_db,
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

    @property
    def version(self) -> int:
        return self.revision_version

    def to_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["version"] = self.revision_version
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchIdea":
        clean_data = dict(data)
        if "version" in clean_data and "revision_version" not in clean_data:
            clean_data["revision_version"] = clean_data.pop("version")
        return cls(**clean_data)


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


def list_ideas(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> List[ResearchIdea]:
    resolved_db = _resolve_db_path(db_path)
    rows = list_ideas_db(session_id=session_id, status=status, limit=limit, db_path=resolved_db)
    return [ResearchIdea.from_dict(r) for r in rows]


