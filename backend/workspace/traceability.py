"""
THOTH Interactive Evidence Matrix and Record-Level Traceability
Phase 5 — Deliverable D: Connect review-flow information and evidence matrix
to underlying records, decisions, appraisals, source documents, and manuscript claims.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from backend.memory.db import (
    DEFAULT_DB_PATH,
    get_connection,
    get_manuscript_db,
    get_prisma_review_db,
    get_screening_decision_db,
    list_manuscript_claims_db,
    list_prisma_reviews_db,
    list_screening_decisions_db,
)


@dataclass
class StudyDetail:
    study_id: str
    review_id: str
    primary_source_id: str = ""
    source_url: str = ""
    title: str = ""
    reports_count: int = 1
    associated_reports: List[Dict[str, Any]] = field(default_factory=list)
    screening_decisions: List[Dict[str, Any]] = field(default_factory=list)
    synthesized_findings: str = ""
    appraisal: Dict[str, Any] = field(default_factory=dict)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    referenced_claims: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DrillDownResult:
    study: Optional[StudyDetail] = None
    flow_node_id: Optional[str] = None
    records: List[Dict[str, Any]] = field(default_factory=list)
    total_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "study": self.study.to_dict() if self.study else None,
            "flow_node_id": self.flow_node_id,
            "records": self.records,
            "total_count": self.total_count,
        }


def drill_down_study_record(
    study_id: str,
    review_id: Optional[str] = None,
    manuscript_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[StudyDetail]:
    """
    Drill down from an evidence matrix row to underlying records,
    screening decisions, appraisal data, and referencing manuscript claims.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Find candidate review(s)
    target_review = None
    if review_id:
        target_review = get_prisma_review_db(review_id, db_path=db_path)
    else:
        # Search all reviews for this study_id in included_studies
        all_reviews = list_prisma_reviews_db(limit=20, db_path=db_path)
        for rev in all_reviews:
            ev_mat = rev.get("evidence_matrix", {})
            for st in ev_mat.get("included_studies", []):
                if st.get("study_id") == study_id:
                    target_review = rev
                    break
            if target_review:
                break

    # If review not found, search directly in screening decisions
    screening_rows = []
    if target_review:
        rev_id = target_review["review_id"]
        screening_rows = list_screening_decisions_db(review_id=rev_id, db_path=db_path)
    else:
        cursor.execute("SELECT * FROM screening_decisions WHERE study_id = ? OR source_id = ?;", (study_id, study_id))
        raw_rows = cursor.fetchall()
        for r in raw_rows:
            d = dict(r)
            try:
                d["criteria_applied"] = json.loads(d.get("criteria_applied_json") or "[]")
            except Exception:
                d["criteria_applied"] = []
            try:
                d["supporting_passages"] = json.loads(d.get("supporting_passages_json") or "[]")
            except Exception:
                d["supporting_passages"] = []
            screening_rows.append(d)

    # Match screening decisions for this study
    matching_decisions = [
        d for d in screening_rows
        if d.get("study_id") == study_id or d.get("source_id") == study_id
    ]

    # Extract study metadata from evidence matrix if available
    findings = ""
    appraisal = {}
    primary_source_id = ""
    source_url = ""
    title = f"Study {study_id}"
    contradictions = []

    if target_review:
        ev_mat = target_review.get("evidence_matrix", {})
        for st in ev_mat.get("included_studies", []):
            if st.get("study_id") == study_id:
                findings = st.get("synthesized_findings", "")
                primary_source_id = st.get("primary_source_id", "")
                source_url = st.get("source_url", "")
                title = st.get("title", title)
                appraisal = {
                    "methodological_appraisal": st.get("appraisal_notes", ""),
                    "study_design": st.get("study_design", "Observational/Interventional"),
                    "sample_size": st.get("sample_size", "Documented"),
                    "risk_of_bias": st.get("risk_of_bias", "Low"),
                    "validity_rating": st.get("validity_rating", "High"),
                }
                break

        for c in ev_mat.get("dialectical_contradictions", []):
            if c.get("supporting_study_id") == study_id:
                contradictions.append(c)

    # If primary_source_id or source_url still empty, pull from decisions
    if matching_decisions:
        first_d = matching_decisions[0]
        primary_source_id = primary_source_id or first_d.get("source_id", "")
        source_url = source_url or first_d.get("source_url", "")
        title = title if title != f"Study {study_id}" else first_d.get("title", title)

    # Distinct associated reports
    distinct_reports = []
    seen_reports = set()
    for d in matching_decisions:
        sid = d.get("source_id")
        if sid and sid not in seen_reports:
            seen_reports.add(sid)
            distinct_reports.append({
                "source_id": sid,
                "title": d.get("title", ""),
                "source_url": d.get("source_url", ""),
                "stage": d.get("stage", ""),
                "disposition": d.get("disposition", ""),
                "supporting_passages": d.get("supporting_passages", []),
            })

    # Find referencing manuscript claims
    referenced_claims = []
    cursor.execute("""
        SELECT * FROM manuscript_claims
        WHERE supporting_sources_json LIKE ? OR counter_sources_json LIKE ?;
    """, (f"%{study_id}%", f"%{study_id}%"))
    for row in cursor.fetchall():
        rc = dict(row)
        try:
            rc["supporting_sources"] = json.loads(rc.get("supporting_sources_json") or "[]")
        except Exception:
            rc["supporting_sources"] = []
        try:
            rc["counter_sources"] = json.loads(rc.get("counter_sources_json") or "[]")
        except Exception:
            rc["counter_sources"] = []
        if not manuscript_id or rc.get("manuscript_id") == manuscript_id:
            referenced_claims.append(rc)

    return StudyDetail(
        study_id=study_id,
        review_id=target_review["review_id"] if target_review else (matching_decisions[0].get("review_id", "") if matching_decisions else ""),
        primary_source_id=primary_source_id,
        source_url=source_url,
        title=title,
        reports_count=len(distinct_reports) or 1,
        associated_reports=distinct_reports,
        screening_decisions=matching_decisions,
        synthesized_findings=findings,
        appraisal=appraisal,
        contradictions=contradictions,
        referenced_claims=referenced_claims,
    )


def get_flow_node_records(
    flow_node_id: str,
    review_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> DrillDownResult:
    """
    Connect review flow diagram nodes to the underlying records contributing to counts.
    Supported node IDs:
    - 'identification'
    - 'screening'
    - 'screened_excluded'
    - 'eligibility'
    - 'eligibility_excluded'
    - 'included_studies'
    - 'included_reports'
    """
    review = get_prisma_review_db(review_id, db_path=db_path)
    if not review:
        raise ValueError(f"PRISMA review '{review_id}' not found.")

    decisions = list_screening_decisions_db(review_id=review_id, db_path=db_path)
    node = flow_node_id.lower().strip()

    records = []
    if node in ("identification", "retrieved"):
        # Distinct sources across all screening decisions
        seen = set()
        for d in decisions:
            sid = d.get("source_id")
            if sid and sid not in seen:
                seen.add(sid)
                records.append({
                    "source_id": sid,
                    "title": d.get("title", ""),
                    "source_url": d.get("source_url", ""),
                    "disposition": d.get("disposition", ""),
                })
    elif node == "screening":
        # All records screened at title/abstract
        records = [d for d in decisions if d.get("stage") == "TITLE_ABSTRACT"]
    elif node in ("screened_excluded", "screening_excluded"):
        records = [d for d in decisions if d.get("stage") == "TITLE_ABSTRACT" and d.get("disposition") == "EXCLUDED"]
    elif node == "eligibility":
        records = [d for d in decisions if d.get("stage") == "FULL_TEXT_ELIGIBILITY"]
    elif node in ("eligibility_excluded", "full_text_excluded"):
        records = [d for d in decisions if d.get("stage") == "FULL_TEXT_ELIGIBILITY" and d.get("disposition") == "EXCLUDED"]
    elif node == "included_studies":
        ev_mat = review.get("evidence_matrix", {})
        records = ev_mat.get("included_studies", [])
    elif node == "included_reports":
        # Decisions with disposition INCLUDED
        records = [d for d in decisions if d.get("disposition") == "INCLUDED"]
    else:
        # Default fallback to decisions matching node as disposition or stage
        records = [
            d for d in decisions
            if d.get("stage", "").lower() == node or d.get("disposition", "").lower() == node
        ]

    return DrillDownResult(
        flow_node_id=flow_node_id,
        records=records,
        total_count=len(records),
    )


def get_claim_traceability(
    claim_id: str,
    manuscript_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Bidirectional navigation from manuscript claim to underlying studies,
    screening decisions, and dialectic contradictions.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    if manuscript_id:
        cursor.execute("SELECT * FROM manuscript_claims WHERE claim_id = ? AND manuscript_id = ?;", (claim_id, manuscript_id))
    else:
        cursor.execute("SELECT * FROM manuscript_claims WHERE claim_id = ?;", (claim_id,))

    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Claim '{claim_id}' not found.")

    claim_dict = dict(row)
    for jfield in ["supporting_sources_json", "counter_sources_json"]:
        k = jfield.replace("_json", "")
        try:
            claim_dict[k] = json.loads(claim_dict.get(jfield) or "[]")
        except Exception:
            claim_dict[k] = []

    # Resolve each supporting study
    resolved_studies = []
    for s in claim_dict.get("supporting_sources", []):
        sid = s.get("study_id") or s.get("source_id")
        if sid:
            st_detail = drill_down_study_record(sid, manuscript_id=manuscript_id, db_path=db_path)
            if st_detail:
                resolved_studies.append(st_detail.to_dict())

    return {
        "claim": claim_dict,
        "resolved_supporting_studies": resolved_studies,
        "counter_evidence": claim_dict.get("counter_sources", []),
        "evidence_status": claim_dict.get("evidence_status", "UNVERIFIED"),
        "confidence": claim_dict.get("confidence", 0.0),
        "reasoning": claim_dict.get("reasoning", ""),
        "uncertainties": claim_dict.get("uncertainties", ""),
    }
