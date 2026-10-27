"""
THOTH Recursive Citation Snowballing Engine
Phase 6 — Deliverable B: Backward and Forward Citation Discovery with Stopping Criteria & PRISMA Accounting.

Extends literature discovery through recursive citation network traversal:
- Backward snowballing (cited references).
- Forward snowballing (citing papers).
- Explicit recursive rounds, parent-child lineage, and source provenance.
- Defensible stopping criteria (marginal yield decay, recursion depth, candidate limits, zero-yield bounds).
- Cycle detection and deduplication.
- Safe integration with PRISMA review screening ledgers and flow accounting.
"""

from __future__ import annotations

import asyncio
import datetime
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from backend.core.logging import get_logger
from backend.intellectual_rigour.prisma import (
    HypothesisRelation,
    PRISMAFlowCounts,
    ReviewerType,
    ScreeningDecision,
    ScreeningDisposition,
    ScreeningStage,
)
from backend.memory.db import (
    DEFAULT_DB_PATH,
    add_snowball_candidate_db,
    get_prisma_review_db,
    save_prisma_review_db,
    save_screening_decision_db,
    save_snowball_run_db,
)
from backend.scholarly import (
    SourceCandidate,
    get_paper_citations,
    get_paper_references,
)

logger = get_logger("SnowballEngine")


class SnowballDirection(str, Enum):
    BACKWARD = "BACKWARD"  # Cited references
    FORWARD = "FORWARD"    # Citing papers


class StoppingReason(str, Enum):
    MAX_DEPTH_REACHED = "MAX_DEPTH_REACHED"
    MAX_CANDIDATES_REACHED = "MAX_CANDIDATES_REACHED"
    MARGINAL_YIELD_DECAY = "MARGINAL_YIELD_DECAY"
    CONSECUTIVE_ZERO_YIELD = "CONSECUTIVE_ZERO_YIELD"
    NO_FURTHER_SEEDS = "NO_FURTHER_SEEDS"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    USER_INTERRUPTED = "USER_INTERRUPTED"


class SnowballConfig(BaseModel):
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum recursion rounds")
    max_candidates: int = Field(default=50, ge=1, le=500, description="Maximum total candidates to identify")
    marginal_yield_threshold: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Minimum ratio of (new unique candidates / lookups executed) to continue",
    )
    max_consecutive_zero_yield_rounds: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Consecutive rounds with 0 new candidates before stopping",
    )
    enable_backward: bool = Field(default=True, description="Enable backward citation discovery (cited references)")
    enable_forward: bool = Field(default=True, description="Enable forward citation discovery (citing papers)")
    limit_per_paper: int = Field(default=5, ge=1, le=20, description="Lookup result limit per paper per direction")
    rate_limit_delay_seconds: float = Field(default=0.05, ge=0.0, description="Cooperative delay between network calls")


@dataclass
class SnowballCandidateItem:
    candidate_id: str
    paper_id: str
    parent_paper_id: str
    title: str
    authors: List[str]
    doi: Optional[str]
    direction: SnowballDirection
    round_number: int
    provider: str
    abstract: str = ""
    url: str = ""
    published_date: Optional[str] = None
    citation_count: Optional[int] = None
    lookup_params: Dict[str, Any] = field(default_factory=dict)
    is_duplicate: bool = False
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "paper_id": self.paper_id,
            "parent_paper_id": self.parent_paper_id,
            "title": self.title,
            "authors": self.authors,
            "doi": self.doi,
            "direction": self.direction.value,
            "round_number": self.round_number,
            "provider": self.provider,
            "abstract": self.abstract,
            "url": self.url,
            "published_date": self.published_date,
            "citation_count": self.citation_count,
            "lookup_params": self.lookup_params,
            "is_duplicate": self.is_duplicate,
            "created_at": self.created_at,
        }


@dataclass
class SnowballRoundSummary:
    round_number: int
    seed_paper_count: int
    queries_executed: int
    candidates_retrieved: int
    new_unique_candidates: int
    duplicates_identified: int
    marginal_yield: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "seed_paper_count": self.seed_paper_count,
            "queries_executed": self.queries_executed,
            "candidates_retrieved": self.candidates_retrieved,
            "new_unique_candidates": self.new_unique_candidates,
            "duplicates_identified": self.duplicates_identified,
            "marginal_yield": round(self.marginal_yield, 4),
        }


@dataclass
class SnowballResult:
    run_id: str
    review_id: str
    brief_id: str
    config: SnowballConfig
    stopping_reason: StoppingReason
    total_rounds: int
    total_candidates: int
    unique_candidates: int
    duplicates_count: int
    candidates: List[SnowballCandidateItem]
    rounds_summary: List[SnowballRoundSummary]
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "review_id": self.review_id,
            "brief_id": self.brief_id,
            "config": self.config.model_dump(),
            "stopping_reason": self.stopping_reason.value,
            "total_rounds": self.total_rounds,
            "total_candidates": self.total_candidates,
            "unique_candidates": self.unique_candidates,
            "duplicates_count": self.duplicates_count,
            "candidates": [c.to_dict() for c in self.candidates],
            "rounds_summary": [r.to_dict() for r in self.rounds_summary],
            "created_at": self.created_at,
        }


def _normalize_identifier(paper: SourceCandidate) -> str:
    """Produces canonical key for cycle prevention and deduplication."""
    if paper.doi:
        return f"doi:{paper.doi.strip().lower()}"
    if paper.paper_id:
        return f"s2:{paper.paper_id.strip()}"
    if paper.arxiv_id:
        return f"arxiv:{paper.arxiv_id.strip().lower()}"
    # Conservative fallback title hash
    clean_title = re.sub(r"[^\w\s]", "", paper.title.lower()).strip()
    return f"title:{clean_title}"


async def run_recursive_snowball(
    seeds: List[SourceCandidate],
    review_id: str,
    brief_id: str,
    config: Optional[SnowballConfig] = None,
    citations_fn: Optional[Callable] = None,
    references_fn: Optional[Callable] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> SnowballResult:
    """
    Executes bounded recursive backward and forward citation snowballing.
    Tracks lineage provenance, eliminates cycles, computes marginal yield decay,
    and updates PRISMA review screening accounting.
    """
    cfg = config or SnowballConfig()
    fetch_citations = citations_fn or get_paper_citations
    fetch_references = references_fn or get_paper_references

    run_id = f"snb_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Track seen papers (canonical keys) to avoid infinite loops and duplicate work
    visited_keys: Set[str] = set()
    for s in seeds:
        key = _normalize_identifier(s)
        visited_keys.add(key)

    all_candidates: List[SnowballCandidateItem] = []
    rounds_summary: List[SnowballRoundSummary] = []

    current_seeds: List[SourceCandidate] = list(seeds)
    stopping_reason = StoppingReason.NO_FURTHER_SEEDS
    consecutive_zero_yield_count = 0

    total_unique_discovered = 0
    total_duplicates_discovered = 0

    for round_num in range(1, cfg.max_depth + 1):
        if not current_seeds:
            stopping_reason = StoppingReason.NO_FURTHER_SEEDS
            break

        round_retrieved_count = 0
        round_unique_count = 0
        round_duplicate_count = 0
        round_queries_count = 0
        next_round_seeds: List[SourceCandidate] = []

        for seed in current_seeds:
            # Check candidate limits
            if total_unique_discovered >= cfg.max_candidates:
                stopping_reason = StoppingReason.MAX_CANDIDATES_REACHED
                break

            seed_ident = seed.paper_id or (seed.doi if seed.doi else seed.title)
            if not seed_ident:
                continue

            async def _invoke_provider(fn, ident, lim):
                if asyncio.iscoroutinefunction(fn):
                    return await fn(ident, limit=lim)
                res = fn(ident, limit=lim)
                if asyncio.iscoroutine(res):
                    return await res
                return res

            # 1. Backward Snowballing (Cited References)
            if cfg.enable_backward:
                round_queries_count += 1
                try:
                    refs = await _invoke_provider(fetch_references, seed_ident, cfg.limit_per_paper)
                    if cfg.rate_limit_delay_seconds > 0:
                        await asyncio.sleep(cfg.rate_limit_delay_seconds)
                except Exception as e:
                    logger.warning(f"Backward snowballing lookup failed for {seed_ident}: {e}")
                    refs = []

                for r in refs:
                    round_retrieved_count += 1
                    r_key = _normalize_identifier(r)
                    is_dup = r_key in visited_keys

                    c_item = SnowballCandidateItem(
                        candidate_id=f"c_{uuid.uuid4().hex[:8]}",
                        paper_id=r.paper_id or r_key,
                        parent_paper_id=seed_ident,
                        title=r.title,
                        authors=r.authors,
                        doi=r.doi,
                        direction=SnowballDirection.BACKWARD,
                        round_number=round_num,
                        provider=r.source_api or "semantic_scholar_references",
                        abstract=r.abstract,
                        url=r.url,
                        published_date=r.published_date,
                        citation_count=r.citation_count,
                        lookup_params={"parent": seed_ident, "direction": "BACKWARD", "limit": cfg.limit_per_paper},
                        is_duplicate=is_dup,
                        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    all_candidates.append(c_item)

                    if is_dup:
                        round_duplicate_count += 1
                        total_duplicates_discovered += 1
                    else:
                        visited_keys.add(r_key)
                        round_unique_count += 1
                        total_unique_discovered += 1
                        next_round_seeds.append(r)

            # 2. Forward Snowballing (Citing Papers)
            if cfg.enable_forward and total_unique_discovered < cfg.max_candidates:
                round_queries_count += 1
                try:
                    cites = await _invoke_provider(fetch_citations, seed_ident, cfg.limit_per_paper)
                    if cfg.rate_limit_delay_seconds > 0:
                        await asyncio.sleep(cfg.rate_limit_delay_seconds)
                except Exception as e:
                    logger.warning(f"Forward snowballing lookup failed for {seed_ident}: {e}")
                    cites = []

                for c in cites:
                    round_retrieved_count += 1
                    c_key = _normalize_identifier(c)
                    is_dup = c_key in visited_keys

                    c_item = SnowballCandidateItem(
                        candidate_id=f"c_{uuid.uuid4().hex[:8]}",
                        paper_id=c.paper_id or c_key,
                        parent_paper_id=seed_ident,
                        title=c.title,
                        authors=c.authors,
                        doi=c.doi,
                        direction=SnowballDirection.FORWARD,
                        round_number=round_num,
                        provider=c.source_api or "semantic_scholar_citations",
                        abstract=c.abstract,
                        url=c.url,
                        published_date=c.published_date,
                        citation_count=c.citation_count,
                        lookup_params={"parent": seed_ident, "direction": "FORWARD", "limit": cfg.limit_per_paper},
                        is_duplicate=is_dup,
                        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    all_candidates.append(c_item)

                    if is_dup:
                        round_duplicate_count += 1
                        total_duplicates_discovered += 1
                    else:
                        visited_keys.add(c_key)
                        round_unique_count += 1
                        total_unique_discovered += 1
                        next_round_seeds.append(c)

        # Compute marginal yield for this round
        # marginal_yield = newly discovered unique candidates / total lookups executed in round
        marginal_yield = (round_unique_count / round_queries_count) if round_queries_count > 0 else 0.0

        r_summary = SnowballRoundSummary(
            round_number=round_num,
            seed_paper_count=len(current_seeds),
            queries_executed=round_queries_count,
            candidates_retrieved=round_retrieved_count,
            new_unique_candidates=round_unique_count,
            duplicates_identified=round_duplicate_count,
            marginal_yield=marginal_yield,
        )
        rounds_summary.append(r_summary)

        # Check stopping criteria
        if round_unique_count == 0:
            consecutive_zero_yield_count += 1
        else:
            consecutive_zero_yield_count = 0

        if total_unique_discovered >= cfg.max_candidates:
            stopping_reason = StoppingReason.MAX_CANDIDATES_REACHED
            break

        if consecutive_zero_yield_count >= cfg.max_consecutive_zero_yield_rounds:
            stopping_reason = StoppingReason.CONSECUTIVE_ZERO_YIELD
            break

        if round_num > 1 and marginal_yield < cfg.marginal_yield_threshold:
            stopping_reason = StoppingReason.MARGINAL_YIELD_DECAY
            break

        if round_num == cfg.max_depth:
            stopping_reason = StoppingReason.MAX_DEPTH_REACHED
            break

        current_seeds = next_round_seeds

    # Persist snowball run and candidate records to database
    save_snowball_run_db(
        run_id=run_id,
        review_id=review_id,
        brief_id=brief_id,
        config=cfg.model_dump(),
        stopping_reason=stopping_reason.value,
        total_rounds=len(rounds_summary),
        total_candidates=len(all_candidates),
        unique_candidates=total_unique_discovered,
        rounds_summary=[r.to_dict() for r in rounds_summary],
        db_path=db_path,
    )

    for cand in all_candidates:
        add_snowball_candidate_db(
            candidate_id=cand.candidate_id,
            run_id=run_id,
            review_id=review_id,
            parent_paper_id=cand.parent_paper_id,
            paper_id=cand.paper_id,
            title=cand.title,
            doi=cand.doi or "",
            direction=cand.direction.value,
            round_number=cand.round_number,
            provider=cand.provider,
            lookup_params=cand.lookup_params,
            is_duplicate=cand.is_duplicate,
            db_path=db_path,
        )

    # Register unique discovered candidates into PRISMA review accounting
    review_record = get_prisma_review_db(review_id, db_path=db_path)
    if review_record:
        flow_counts_dict = review_record.get("flow_counts") or {}
        flow = PRISMAFlowCounts(**flow_counts_dict) if flow_counts_dict else PRISMAFlowCounts()

        # Update identified_snowball count and recalculate flow invariants
        flow.identified_snowball += total_unique_discovered
        flow.duplicates_removed += total_duplicates_discovered
        flow.total_identified = flow.identified_databases + flow.identified_registries_web + flow.identified_snowball
        flow.records_screened = max(0, flow.total_identified - flow.duplicates_removed)

        # Ingest unique candidates into screening_decisions table as TITLE_ABSTRACT with UNRESOLVED disposition
        for cand in all_candidates:
            if not cand.is_duplicate:
                save_screening_decision_db(
                    decision_data={
                        "decision_id": f"dec_{cand.candidate_id}",
                        "review_id": review_id,
                        "brief_id": brief_id,
                        "source_id": cand.paper_id,
                        "source_url": cand.url,
                        "title": cand.title,
                        "stage": ScreeningStage.TITLE_ABSTRACT.value,
                        "disposition": ScreeningDisposition.UNRESOLVED.value,
                        "criteria_applied": ["snowball_discovery"],
                        "rationale": f"Discovered via {cand.direction.value.lower()} snowballing in round {cand.round_number} from parent {cand.parent_paper_id}.",
                        "supporting_passages": [cand.abstract[:300]] if cand.abstract else [],
                        "reviewer_type": ReviewerType.AI_RECOMMENDED.value,
                        "study_id": cand.doi or cand.paper_id,
                    },
                    db_path=db_path,
                )

        save_prisma_review_db(
            review_data={
                "review_id": review_id,
                "brief_id": brief_id,
                "session_id": review_record.get("session_id", ""),
                "topic": review_record.get("topic", "Research Topic"),
                "protocol": review_record.get("protocol") or {},
                "flow_counts": flow.to_dict(),
                "evidence_matrix": review_record.get("evidence_matrix") or {},
                "mermaid_diagram": review_record.get("mermaid_diagram", ""),
            },
            db_path=db_path,
        )

    return SnowballResult(
        run_id=run_id,
        review_id=review_id,
        brief_id=brief_id,
        config=cfg,
        stopping_reason=stopping_reason,
        total_rounds=len(rounds_summary),
        total_candidates=len(all_candidates),
        unique_candidates=total_unique_discovered,
        duplicates_count=total_duplicates_discovered,
        candidates=all_candidates,
        rounds_summary=rounds_summary,
        created_at=now_iso,
    )
