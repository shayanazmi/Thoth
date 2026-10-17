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
from backend.intellectual_rigour.snowball import (
    SnowballConfig,
    run_recursive_snowball,
)
from backend.scholarly import SourceCandidate
from backend.memory.db import (
    DEFAULT_DB_PATH,
    get_prisma_review_db,
    list_prisma_reviews_db,
    save_prisma_review_db,
    get_screening_decision_db,
    list_screening_decisions_db,
    update_screening_decision_db,
    get_brief_db,
    list_snowball_runs_db,
    get_snowball_run_db,
    list_snowball_candidates_db,
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


# ==============================================================================
# Phase 6: Recursive Citation Snowballing Endpoints
# ==============================================================================

class SnowballExecutionRequest(BaseModel):
    seeds: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional seed papers. Defaults to review's screened or matrix studies.")
    max_depth: int = Field(default=3, ge=1, le=10)
    max_candidates: int = Field(default=50, ge=1, le=500)
    marginal_yield_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    enable_backward: bool = True
    enable_forward: bool = True
    limit_per_paper: int = Field(default=5, ge=1, le=20)


@router.post("/reviews/{review_id}/snowball", status_code=status.HTTP_201_CREATED)
async def execute_snowball_for_review(
    review_id: str,
    req: SnowballExecutionRequest,
    db_path: Optional[str] = None,
):
    """
    Execute recursive backward and forward citation snowballing for an existing PRISMA review.
    Discovered candidates enter screening decisions and update PRISMA flow accounting.
    """
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id}' not found.",
        )

    brief_id = rev.get("brief_id") or ""
    seed_candidates: List[SourceCandidate] = []
    if req.seeds:
        for s in req.seeds:
            seed_candidates.append(
                SourceCandidate(
                    title=s.get("title") or "Untitled",
                    authors=s.get("authors") or [],
                    doi=s.get("doi"),
                    paper_id=s.get("paper_id") or s.get("study_id"),
                    url=s.get("url") or "",
                    abstract=s.get("abstract") or "",
                )
            )
    else:
        # Extract seeds from evidence matrix studies
        ev_matrix = rev.get("evidence_matrix") or {}
        for study in ev_matrix.get("studies", []):
            seed_candidates.append(
                SourceCandidate(
                    title=study.get("title") or "Untitled",
                    authors=study.get("authors") or [],
                    doi=study.get("doi_or_url") if study.get("doi_or_url", "").startswith("10.") else None,
                    paper_id=study.get("study_id"),
                    url=study.get("doi_or_url") or "",
                )
            )
        # Fallback to screening decisions if matrix is empty
        if not seed_candidates:
            decisions = list_screening_decisions_db(review_id, db_path=path)
            for d in decisions[:5]:
                seed_candidates.append(
                    SourceCandidate(
                        title=d.get("title") or "Untitled",
                        paper_id=d.get("source_id"),
                        url=d.get("source_url") or "",
                    )
                )

    if not seed_candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No seed papers found in review or request to start citation snowballing.",
        )

    config = SnowballConfig(
        max_depth=req.max_depth,
        max_candidates=req.max_candidates,
        marginal_yield_threshold=req.marginal_yield_threshold,
        enable_backward=req.enable_backward,
        enable_forward=req.enable_forward,
        limit_per_paper=req.limit_per_paper,
    )

    result = await run_recursive_snowball(
        seeds=seed_candidates,
        review_id=review_id,
        brief_id=brief_id,
        config=config,
        db_path=path,
    )
    return {"status": "success", "snowball_result": result.to_dict()}


@router.get("/reviews/{review_id}/snowball")
async def list_snowball_runs_for_review(
    review_id: str,
    db_path: Optional[str] = None,
):
    """List historical snowball traversal runs and stopping summaries for a PRISMA review."""
    path = db_path or DEFAULT_DB_PATH
    runs = list_snowball_runs_db(review_id, db_path=path)
    return {"status": "success", "runs": runs}


@router.get("/reviews/snowball-runs/{run_id}/candidates")
async def list_snowball_candidates_for_run(
    run_id: str,
    db_path: Optional[str] = None,
):
    """Retrieve all discovered candidates and parent-child provenance for a specific snowball run."""
    path = db_path or DEFAULT_DB_PATH
    run = get_snowball_run_db(run_id, db_path=path)
    if not run:
        raise HTTPException(status_code=404, detail=f"Snowball run '{run_id}' not found.")
    candidates = list_snowball_candidates_db(run_id, db_path=path)
    return {"status": "success", "run": run, "candidates": candidates}


# ==============================================================================
# Phase 7: Literature Clustering & Citation Network Graph Endpoints
# ==============================================================================

class LiteratureClusteringRequest(BaseModel):
    n_clusters: Optional[int] = Field(default=None, ge=1, le=20, description="Optional target number of thematic clusters")


@router.post("/reviews/{review_id}/cluster", status_code=status.HTTP_201_CREATED)
async def execute_clustering_for_review(
    review_id: str,
    req: LiteratureClusteringRequest = LiteratureClusteringRequest(),
    db_path: Optional[str] = None,
):
    """
    Execute semantic thematic clustering and citation network graph analysis for a PRISMA review.
    Computes betweenness centrality, bridge papers, structural holes, and 2D force-directed layout.
    """
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id}' not found.",
        )

    from backend.intellectual_rigour.clustering import run_literature_clustering_and_graph
    result = run_literature_clustering_and_graph(
        review_id=review_id,
        project_id=rev.get("project_id"),
        n_clusters=req.n_clusters,
        db_path=path,
    )
    return {"status": "success", "clustering": result.to_dict()}


@router.get("/reviews/{review_id}/cluster")
async def get_clustering_for_review(
    review_id: str,
    auto_generate: bool = True,
    db_path: Optional[str] = None,
):
    """Retrieve the latest thematic clustering result for a review. Automatically generates if missing."""
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id}' not found.",
        )

    from backend.memory.db import get_literature_clustering_db
    clustering = get_literature_clustering_db(review_id, db_path=path)
    if not clustering and auto_generate:
        from backend.intellectual_rigour.clustering import run_literature_clustering_and_graph
        res = run_literature_clustering_and_graph(
            review_id=review_id,
            project_id=rev.get("project_id"),
            db_path=path,
        )
        clustering = res.to_dict()

    if not clustering:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No literature clustering found for review '{review_id}'.",
        )

    return {"status": "success", "clustering": clustering}


@router.get("/reviews/{review_id}/citation-graph")
async def get_citation_graph_for_review(
    review_id: str,
    auto_generate: bool = True,
    db_path: Optional[str] = None,
):
    """Retrieve the 2D layout citation graph and centrality metrics for a review."""
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id}' not found.",
        )

    from backend.memory.db import get_citation_graph_db
    graph = get_citation_graph_db(review_id, db_path=path)
    if not graph and auto_generate:
        from backend.intellectual_rigour.clustering import run_literature_clustering_and_graph
        res = run_literature_clustering_and_graph(
            review_id=review_id,
            project_id=rev.get("project_id"),
            db_path=path,
        )
        graph = res.graph.to_dict()

    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No citation graph found for review '{review_id}'.",
        )

    return {"status": "success", "citation_graph": graph}


@router.get("/reviews/{review_id}/citation-graph/mermaid")
async def get_citation_graph_mermaid_for_review(
    review_id: str,
    max_nodes: int = 25,
    db_path: Optional[str] = None,
):
    """Generate Mermaid flowchart markdown for the review's citation network graph."""
    path = db_path or DEFAULT_DB_PATH
    rev = get_prisma_review_db(review_id, db_path=path)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRISMA review '{review_id}' not found.",
        )

    from backend.intellectual_rigour.clustering import (
        LiteratureCitationGraph,
        generate_citation_network_mermaid,
        run_literature_clustering_and_graph,
    )
    from backend.memory.db import get_citation_graph_db

    graph_dict = get_citation_graph_db(review_id, db_path=path)
    if not graph_dict:
        res = run_literature_clustering_and_graph(
            review_id=review_id,
            project_id=rev.get("project_id"),
            db_path=path,
        )
        mermaid = generate_citation_network_mermaid(res.graph, max_nodes=max_nodes)
    else:
        graph = LiteratureCitationGraph(**graph_dict)
        mermaid = generate_citation_network_mermaid(graph, max_nodes=max_nodes)

    return {"status": "success", "review_id": review_id, "mermaid": mermaid}


