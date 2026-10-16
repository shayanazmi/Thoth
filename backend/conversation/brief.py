import uuid
import datetime
import json
import re
import threading
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.conversation.mandate import ResearchMandate, synthesize_research_mandate
from backend.intellectual_rigour.matcher import ARCHETYPE_DEFINITIONS
from backend.memory.db import (
    save_brief_db,
    get_brief_db,
    DEFAULT_DB_PATH,
    create_task_atomic_db,
    claim_task_atomic_db,
    update_task_status_db,
    request_task_cancellation_db,
    reconcile_orphaned_tasks_db,
    get_task_db,
    get_active_task_for_brief_db,
    list_tasks_db,
    clear_tasks_db,
)


class BriefApprovalStatus(str):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class ResearchBrief(BaseModel):
    brief_id: str = Field(default_factory=lambda: f"brief-{uuid.uuid4().hex[:12]}")
    session_id: str = Field(default="")
    topic: str = Field(..., description="Research topic or scientific domain")
    version: int = Field(default=1, description="Sequential version; increments on substantive edit")
    research_question: str = Field(..., description="Primary research question to be investigated")
    objectives: List[str] = Field(default_factory=list, description="Concrete investigative objectives")
    hypotheses: List[str] = Field(default_factory=list, description="Testable or competing hypotheses")
    context_and_assumptions: List[str] = Field(default_factory=list, description="Context, axioms, and constraints inherited from dialogue")
    search_scope: str = Field(default="peer-reviewed academic literature", description="Literature discovery scope and domain criteria")
    selection_criteria: List[str] = Field(default_factory=list, description="Methodological boundaries, inclusion/exclusion criteria")
    thinker_context: Optional[Dict[str, Any]] = Field(default=None, description="Thinker ID, archetype, tradition, and dialectic critique focus")
    unresolved_questions: List[str] = Field(default_factory=list, description="Open objections or unresolved questions from sparring")
    approval_status: str = Field(default=BriefApprovalStatus.PENDING_APPROVAL, description="PENDING_APPROVAL, APPROVED, REJECTED, STALE")
    approved_version: Optional[int] = Field(default=None, description="Exact version explicitly approved by the user")
    approved_at: Optional[str] = Field(default=None, description="ISO timestamp of user approval")
    idea_id: Optional[str] = Field(default=None, description="Linked promoted idea artifact ID")
    counter_evidence_queries: List[Any] = Field(default_factory=list, description="Targeted queries to search for contradictory or disconfirming literature")
    falsification_criteria: List[str] = Field(default_factory=list, description="Explicit conditions under which hypothesis would be disproven")
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def is_approved(self) -> bool:
        return (
            self.approval_status == BriefApprovalStatus.APPROVED
            and self.approved_version is not None
            and self.approved_version == self.version
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_mandate(self) -> ResearchMandate:
        obj = "; ".join(self.objectives) if self.objectives else f"Investigate literature for {self.research_question}"
        return ResearchMandate(
            objective=obj,
            primary_question=self.research_question,
            sub_questions=list(self.objectives) + list(self.unresolved_questions),
            hypotheses=list(self.hypotheses),
            constraints=list(self.selection_criteria),
            scope=self.search_scope,
            known_facts=list(self.context_and_assumptions),
            topic=self.topic,
        )

    @classmethod
    def from_mandate(
        cls,
        mandate: ResearchMandate,
        thinker_context: Optional[Dict[str, Any]] = None,
        unresolved_questions: Optional[List[str]] = None,
        session_id: str = "",
        idea_id: Optional[str] = None,
        counter_evidence_queries: Optional[List[str]] = None,
        falsification_criteria: Optional[List[str]] = None,
    ) -> "ResearchBrief":
        return cls(
            session_id=session_id,
            topic=mandate.topic or mandate.primary_question,
            research_question=mandate.primary_question or mandate.objective,
            objectives=list(mandate.sub_questions),
            hypotheses=list(mandate.hypotheses),
            context_and_assumptions=list(mandate.known_facts),
            search_scope=mandate.scope,
            selection_criteria=list(mandate.constraints),
            thinker_context=thinker_context,
            unresolved_questions=list(unresolved_questions or []),
            idea_id=idea_id,
            counter_evidence_queries=list(counter_evidence_queries or []),
            falsification_criteria=list(falsification_criteria or []),
            approval_status=BriefApprovalStatus.PENDING_APPROVAL,
            version=1,
        )


# In-memory storage cache for ultra-fast access and testing
_IN_MEMORY_BRIEFS: Dict[str, ResearchBrief] = {}


class ResearchTaskManager:
    """
    Durable, database-backed execution lifecycle manager.
    Tracks running research tasks, prevents duplicate executions via database constraints,
    revalidates brief authorization at claim time, and supports immediate cooperative cancellation propagation.
    """
    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._cancel_events: Dict[str, threading.Event] = {}
        self._custom_db_path = db_path

    @property
    def db_path(self) -> str:
        if self._custom_db_path is not None:
            return self._custom_db_path
        from backend.memory.db import DEFAULT_DB_PATH
        return DEFAULT_DB_PATH

    def register_task(
        self,
        task_id: str,
        brief_id: str,
        version: int,
        worker_id: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> Tuple[bool, Optional[threading.Event], str]:
        path = db_path or self.db_path
        with self._lock:
            ok, task, msg = create_task_atomic_db(
                task_id=task_id,
                brief_id=brief_id,
                brief_version=version,
                worker_id=worker_id,
                db_path=path,
            )
            if not ok:
                return False, None, msg

            cancel_event = threading.Event()
            self._cancel_events[task_id] = cancel_event
            return True, cancel_event, "Task registered."

    def claim_task(
        self,
        task_id: str,
        worker_id: str,
        db_path: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Atomically claim execution and revalidate brief authorization at claim boundary."""
        path = db_path or self.db_path
        with self._lock:
            ok, task, msg = claim_task_atomic_db(
                task_id=task_id,
                worker_id=worker_id,
                db_path=path,
            )
            if not ok:
                evt = self._cancel_events.get(task_id)
                if evt and task and task.get("status") == "CANCELLED":
                    evt.set()
                return False, task, msg
            return True, task, msg

    def cancel_task(self, identifier: str, db_path: Optional[str] = None) -> bool:
        """Cancel an execution by task_id or brief_id."""
        path = db_path or self.db_path
        with self._lock:
            ok, affected_tids = request_task_cancellation_db(identifier, db_path=path)
            for tid in affected_tids:
                evt = self._cancel_events.get(tid)
                if evt:
                    evt.set()
            return ok

    def record_cancellation(self, task_id: str, db_path: Optional[str] = None) -> bool:
        """Called when cooperative cancellation halts execution in the worker."""
        path = db_path or self.db_path
        with self._lock:
            evt = self._cancel_events.get(task_id)
            if evt:
                evt.set()
            return update_task_status_db(
                task_id=task_id,
                status="CANCELLED",
                error_summary="Task cancelled by user.",
                db_path=path,
            )

    def complete_task(
        self,
        task_id: str,
        final_status: str = "COMPLETED",
        error_code: Optional[str] = None,
        error_summary: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> bool:
        path = db_path or self.db_path
        with self._lock:
            ok = update_task_status_db(
                task_id=task_id,
                status=final_status,
                error_code=error_code,
                error_summary=error_summary,
                db_path=path,
            )
            self._cancel_events.pop(task_id, None)
            return ok

    def get_task(self, task_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        path = db_path or self.db_path
        return get_task_db(task_id, db_path=path)

    def is_running(self, brief_id: str, db_path: Optional[str] = None) -> bool:
        path = db_path or self.db_path
        task = get_active_task_for_brief_db(brief_id, db_path=path)
        return task is not None

    def reconcile_orphaned_tasks(
        self,
        worker_id: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> int:
        path = db_path or self.db_path
        with self._lock:
            return reconcile_orphaned_tasks_db(worker_id=worker_id, db_path=path)

    def clear(self, db_path: Optional[str] = None):
        path = db_path or self.db_path
        with self._lock:
            self._cancel_events.clear()
            clear_tasks_db(db_path=path)


task_manager = ResearchTaskManager()


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    if db_path is not None:
        return db_path
    from backend.memory.db import DEFAULT_DB_PATH
    return DEFAULT_DB_PATH


def prepare_research_brief(
    topic: str,
    research_question: Optional[str] = None,
    objectives: Optional[List[str]] = None,
    chat_turns: Optional[List[Dict[str, Any]]] = None,
    conversation_summary: str = "",
    thinker_id: Optional[str] = None,
    hypothesis: Optional[str] = None,
    constraints: Optional[List[str]] = None,
    selection_criteria: Optional[List[str]] = None,
    unresolved_questions: Optional[List[str]] = None,
    session_id: str = "",
    idea_id: Optional[str] = None,
    counter_evidence_queries: Optional[List[str]] = None,
    falsification_criteria: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> ResearchBrief:
    """
    Synthesize an editable ResearchBrief from conversation, thinker sparring,
    promoted research idea, or explicit user query without launching formal research.
    """
    db_path = _resolve_db_path(db_path)
    if isinstance(topic, dict):
        d = topic
        topic = d.get("topic") or d.get("title") or ""
        research_question = research_question or d.get("primary_question") or d.get("research_question")
        objectives = objectives or d.get("objectives")
        hypothesis = hypothesis or (d.get("hypotheses")[0] if d.get("hypotheses") else None) or d.get("hypothesis")
        thinker_ctx = d.get("thinker_context") or {}
        thinker_id = thinker_id or d.get("thinker_id") or thinker_ctx.get("thinker_id")
        unresolved_questions = unresolved_questions or d.get("unresolved_questions") or thinker_ctx.get("unresolved_objections")
        counter_evidence_queries = counter_evidence_queries or d.get("counter_evidence_queries")
        falsification_criteria = falsification_criteria or d.get("falsification_criteria")
        session_id = session_id or d.get("session_id", "")
    clean_topic = (topic or "").strip()
    turns = chat_turns or []

    # 1. Inherit conversation mandate
    mandate = synthesize_research_mandate(
        user_query=clean_topic,
        chat_turns=turns,
        conversation_summary=conversation_summary,
    )

    resolved_topic = mandate.topic or clean_topic

    # 2. Extract or incorporate hypotheses
    active_hypotheses: List[str] = []
    if hypothesis and hypothesis.strip():
        active_hypotheses.append(hypothesis.strip())
    if mandate.hypotheses:
        for h in mandate.hypotheses:
            if h not in active_hypotheses:
                active_hypotheses.append(h)

    # 3. Incorporate selection criteria and constraints
    active_criteria: List[str] = []
    for c_list in [constraints, selection_criteria, mandate.constraints]:
        if c_list:
            for c in c_list:
                c_str = str(c).strip()
                if c_str and c_str not in active_criteria:
                    active_criteria.append(c_str)

    # 4. Process thinker context if present
    thinker_context = None
    tid = (thinker_id or "").strip().lower()
    if tid and tid in ARCHETYPE_DEFINITIONS:
        meta = ARCHETYPE_DEFINITIONS[tid]
        thinker_context = {
            "thinker_id": tid,
            "thinker_name": meta.get("name", tid.title()),
            "archetype": meta.get("archetype", ""),
            "tradition": meta.get("tradition", ""),
            "perspective": meta.get("perspective", meta.get("description", "")),
            "description": meta.get("description", ""),
            "unresolved_objections": [meta.get("default_opening", "")] if meta.get("default_opening") else [],
        }

    # 5. Extract unresolved questions from dialogue or thinker sparring
    active_unresolved: List[str] = list(unresolved_questions or [])
    if not active_unresolved and turns:
        for t in reversed(turns):
            bot_msg = t.get("assistant") or t.get("assistant_response") or ""
            # Extract questions asked by assistant
            questions = re.findall(r"([^.?!;\n]+\?)", bot_msg)
            for q in questions:
                q_clean = q.strip().lstrip("-*• ")
                if len(q_clean) > 15 and q_clean not in active_unresolved:
                    active_unresolved.append(q_clean)
            if len(active_unresolved) >= 3:
                break

    # 6. Inherit and enforce promotion barrier from linked research idea
    if idea_id:
        from backend.conversation.idea import get_idea, IdeaStatus
        linked_idea = get_idea(idea_id, db_path=db_path)
        if not linked_idea:
            raise ValueError(f"Linked research idea '{idea_id}' not found.")
        if linked_idea.status == IdeaStatus.TENTATIVE:
            raise ValueError(
                f"Promotion Barrier: Cannot build research brief from tentative idea '{idea_id}'. "
                "The user must explicitly promote the idea first."
            )
        if linked_idea.hypothesis and linked_idea.hypothesis not in active_hypotheses:
            active_hypotheses.insert(0, linked_idea.hypothesis)
        if not thinker_context and linked_idea.thinker_id:
            i_tid = linked_idea.thinker_id.lower()
            if i_tid in ARCHETYPE_DEFINITIONS:
                meta = ARCHETYPE_DEFINITIONS[i_tid]
                thinker_context = {
                    "thinker_id": i_tid,
                    "thinker_name": meta.get("name", i_tid.title()),
                    "archetype": meta.get("archetype", ""),
                    "tradition": meta.get("tradition", ""),
                    "perspective": meta.get("perspective", meta.get("description", "")),
                    "description": meta.get("description", ""),
                    "unresolved_objections": list(linked_idea.unresolved_objections),
                }
        for obj in linked_idea.unresolved_objections:
            if obj not in active_unresolved:
                active_unresolved.append(obj)
        if (not resolved_topic or resolved_topic == "Untitled Research Idea") and linked_idea.title:
            resolved_topic = linked_idea.title

    # 7. Formulate counter-evidence queries and falsification criteria
    if counter_evidence_queries is not None:
        active_counter_queries = list(counter_evidence_queries)
    else:
        from backend.intellectual_rigour.counter_evidence import generate_counter_evidence_plan
        primary_hypo = active_hypotheses[0] if active_hypotheses else resolved_topic
        tid_for_plan = (thinker_context.get("thinker_id") if thinker_context else (thinker_id or "popper"))
        ce_plan = generate_counter_evidence_plan(
            hypothesis=primary_hypo,
            thinker_id=tid_for_plan,
            objections=active_unresolved,
            topic=resolved_topic,
        )
        active_counter_queries = [q.to_dict() for q in ce_plan.queries]

    if falsification_criteria is not None:
        active_falsification = list(falsification_criteria)
    else:
        active_falsification = ce_plan.falsification_criteria if 'ce_plan' in locals() else []

    # 8. Formulate research question and objectives
    if research_question and research_question.strip():
        research_q = research_question.strip()
    elif active_hypotheses:
        research_q = f"Does empirical literature corroborate that {active_hypotheses[0]}?"
    else:
        research_q = mandate.primary_question or f"What empirical evidence exists regarding {resolved_topic}?"

    if objectives is not None:
        active_objectives = list(objectives)
    else:
        active_objectives = [
            f"Synthesize foundational theory and mechanisms of {resolved_topic}.",
            f"Evaluate empirical benchmark results and methodologies in recent literature.",
            f"Identify open controversies, contradictions, and boundary conditions."
        ]

    brief = ResearchBrief(
        session_id=session_id,
        topic=resolved_topic,
        version=1,
        research_question=research_q,
        objectives=active_objectives,
        hypotheses=active_hypotheses,
        context_and_assumptions=list(mandate.known_facts),
        search_scope=mandate.scope,
        selection_criteria=active_criteria,
        thinker_context=thinker_context,
        unresolved_questions=active_unresolved[:3],
        idea_id=idea_id,
        counter_evidence_queries=active_counter_queries,
        falsification_criteria=active_falsification,
        approval_status=BriefApprovalStatus.PENDING_APPROVAL,
    )

    # Cache and persist
    _IN_MEMORY_BRIEFS[brief.brief_id] = brief
    try:
        save_brief_db(brief.to_dict(), db_path=db_path)
    except Exception:
        pass

    if idea_id:
        try:
            from backend.conversation.idea import attach_idea_to_brief
            attach_idea_to_brief(idea_id, brief.brief_id, db_path=db_path)
        except Exception:
            pass

    return brief


def update_research_brief(
    brief_id: str,
    updates: Dict[str, Any],
    db_path: Optional[str] = None,
) -> ResearchBrief:
    """
    Apply user modifications to a research brief.
    Modifying substantive fields increments the version and invalidates any previous approval.
    """
    db_path = _resolve_db_path(db_path)
    brief = get_research_brief(brief_id, db_path=db_path)
    if not brief:
        raise ValueError(f"Research brief '{brief_id}' does not exist.")

    substantive_keys = {
        "topic", "research_question", "objectives", "hypotheses",
        "context_and_assumptions", "search_scope", "selection_criteria",
        "thinker_context", "unresolved_questions", "idea_id",
        "counter_evidence_queries", "falsification_criteria"
    }

    substantive_change = False
    for k in substantive_keys:
        if k in updates and updates[k] != getattr(brief, k):
            substantive_change = True
            break

    if substantive_change:
        brief.version += 1
        # Invalidate previous approval
        brief.approval_status = BriefApprovalStatus.PENDING_APPROVAL
        brief.approved_version = None
        brief.approved_at = None

    for k, v in updates.items():
        if hasattr(brief, k) and k not in ("brief_id", "version", "created_at"):
            setattr(brief, k, v)

    brief.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _IN_MEMORY_BRIEFS[brief.brief_id] = brief
    try:
        save_brief_db(brief.to_dict(), db_path=db_path)
    except Exception:
        pass

    return brief


def approve_research_brief(
    brief_id: str,
    version: int,
    db_path: Optional[str] = None,
) -> Tuple[bool, Optional[ResearchBrief], str]:
    """
    Explicitly approve a specific version of a research brief.
    Rejects stale approvals where the approved version does not match the current brief version.
    """
    db_path = _resolve_db_path(db_path)
    brief = get_research_brief(brief_id, db_path=db_path)
    if not brief:
        return False, None, f"Research brief '{brief_id}' not found."

    if brief.version != version:
        return (
            False,
            brief,
            f"Stale approval rejected: Brief is currently at version {brief.version}, but version {version} was submitted for approval."
        )

    brief.approval_status = BriefApprovalStatus.APPROVED
    brief.approved_version = version
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    brief.approved_at = now_iso
    brief.updated_at = now_iso

    _IN_MEMORY_BRIEFS[brief.brief_id] = brief
    try:
        save_brief_db(brief.to_dict(), db_path=db_path)
    except Exception:
        pass

    return True, brief, f"Research brief '{brief_id}' (version {version}) approved successfully."


def get_research_brief(brief_id: str, db_path: Optional[str] = None) -> Optional[ResearchBrief]:
    """Retrieve a research brief by identifier from memory or SQLite database."""
    db_path = _resolve_db_path(db_path)
    if brief_id in _IN_MEMORY_BRIEFS:
        return _IN_MEMORY_BRIEFS[brief_id]

    try:
        data = get_brief_db(brief_id, db_path=db_path)
        if data:
            brief = ResearchBrief(**data)
            _IN_MEMORY_BRIEFS[brief_id] = brief
            return brief
    except Exception:
        pass

    return None


def verify_brief_approval(
    brief_or_id: Any,
    expected_version: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Tuple[bool, Optional[ResearchBrief], str]:
    """
    Enforce the approval barrier.
    Validates that:
    1. A valid brief exists.
    2. The brief has approval_status == APPROVED.
    3. The approved_version matches the current version (no stale approval).
    4. If expected_version is provided, it matches the current brief version.
    """
    db_path = _resolve_db_path(db_path)
    brief: Optional[ResearchBrief] = None
    if isinstance(brief_or_id, str):
        brief = get_research_brief(brief_or_id, db_path=db_path)
    elif isinstance(brief_or_id, dict):
        # Client payloads cannot self-certify approval. Extract brief_id and look up authoritative record.
        brief_id = brief_or_id.get("brief_id")
        if not brief_id:
            return False, None, "No brief_id found in brief payload. Approval requires a persisted, server-verified brief."
        brief = get_research_brief(brief_id, db_path=db_path)
        if not brief:
            return False, None, f"Brief '{brief_id}' does not exist in server storage. Client payload cannot self-certify approval."
    elif isinstance(brief_or_id, ResearchBrief):
        if brief_or_id.brief_id:
            persisted = get_research_brief(brief_or_id.brief_id, db_path=db_path)
            brief = persisted if persisted is not None else brief_or_id
        else:
            brief = brief_or_id

    if not brief:
        return False, None, "No research brief found or provided. Formal research requires an approved Research Brief."

    if brief.approval_status != BriefApprovalStatus.APPROVED:
        return (
            False,
            brief,
            f"Approval Barrier: Brief '{brief.brief_id}' is in state '{brief.approval_status}'. Explicit user approval is required before literature retrieval or report generation can begin."
        )

    if brief.approved_version is None or brief.approved_version != brief.version:
        return (
            False,
            brief,
            f"Stale Approval Barrier: Brief version {brief.approved_version} was approved, but brief has been modified to version {brief.version}. Explicit re-approval of the latest version is required."
        )

    if expected_version is not None and brief.version != expected_version:
        return (
            False,
            brief,
            f"Version Mismatch: Execution requested for version {expected_version}, but brief is at version {brief.version}."
        )

    return True, brief, "Approval verified."


def clear_briefs_cache():
    """Clear in-memory cache of briefs (primarily for testing)."""
    with _IN_MEMORY_BRIEFS_LOCK if "_IN_MEMORY_BRIEFS_LOCK" in globals() else threading.Lock():
        _IN_MEMORY_BRIEFS.clear()
