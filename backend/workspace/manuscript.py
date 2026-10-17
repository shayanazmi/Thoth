"""
THOTH Manuscript Engine with Claim-Level Revision History
Phase 5 — Deliverable B: Turn THOTH's research synthesis into a structured,
editable, versioned manuscript whose claims remain connected to their sources
and whose evolution can be inspected across drafts.
"""

from __future__ import annotations

import datetime
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.memory.db import (
    DEFAULT_DB_PATH,
    get_brief_db,
    get_connection,
    get_manuscript_db,
    get_manuscript_revision_db,
    get_prisma_review_db,
    list_manuscript_claims_db,
    list_manuscript_revisions_db,
    list_manuscripts_db,
    save_manuscript_claims_batch_db,
    save_manuscript_db,
    save_manuscript_revision_db,
)


@dataclass
class ManuscriptClaim:
    claim_id: str
    manuscript_id: str
    revision_id: str
    section: str
    claim_text: str
    evidence_status: str = "UNVERIFIED"  # SUPPORTED, QUALIFIED, CHALLENGED, UNVERIFIED
    supporting_sources: List[Dict[str, Any]] = field(default_factory=list)
    counter_sources: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    uncertainties: str = ""
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ManuscriptSection:
    heading: str
    content: str
    order: int
    section_type: str = "standard"  # standard, methodology, results, discussion, references, evidence_matrix

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ManuscriptRevision:
    revision_id: str
    manuscript_id: str
    version: int
    title: str
    author_notes: str = ""
    sections: Dict[str, Any] = field(default_factory=dict)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    references: List[Dict[str, Any]] = field(default_factory=list)
    evidence_matrix: Dict[str, Any] = field(default_factory=dict)
    diff_summary: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Manuscript:
    manuscript_id: str
    project_id: str
    title: str
    current_version: int = 1
    brief_id: Optional[str] = None
    review_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def create_manuscript(
    project_id: str,
    title: str,
    brief_id: Optional[str] = None,
    review_id: Optional[str] = None,
    initial_sections: Optional[Dict[str, Any]] = None,
    initial_claims: Optional[List[Dict[str, Any]]] = None,
    initial_references: Optional[List[Dict[str, Any]]] = None,
    initial_evidence_matrix: Optional[Dict[str, Any]] = None,
    author_notes: str = "Initial draft creation",
    manuscript_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Tuple[Manuscript, ManuscriptRevision]:
    """
    Create a new persistent structured manuscript with initial version (v1).
    """
    mid = manuscript_id or f"ms_{uuid.uuid4().hex[:12]}"
    rev_id = f"rev_{uuid.uuid4().hex[:12]}"

    # Save manuscript entity
    res_m = save_manuscript_db(
        manuscript_id=mid,
        project_id=project_id,
        title=title,
        current_version=1,
        brief_id=brief_id,
        review_id=review_id,
        db_path=db_path,
    )

    sec = initial_sections or _default_academic_sections(title)
    claims = initial_claims or []
    refs = initial_references or []
    ev_mat = initial_evidence_matrix or {}

    # Attach manuscript_id & revision_id to claims
    persisted_claims = []
    for c in claims:
        cid = c.get("claim_id") or f"clm_{uuid.uuid4().hex[:10]}"
        persisted_claims.append({
            "claim_id": cid,
            "manuscript_id": mid,
            "revision_id": rev_id,
            "section": c.get("section", "Findings"),
            "claim_text": c.get("claim_text", ""),
            "evidence_status": c.get("evidence_status", "UNVERIFIED"),
            "supporting_sources": c.get("supporting_sources", []),
            "counter_sources": c.get("counter_sources", []),
            "confidence": float(c.get("confidence", 0.0)),
            "reasoning": c.get("reasoning", ""),
            "uncertainties": c.get("uncertainties", ""),
        })

    if persisted_claims:
        save_manuscript_claims_batch_db(persisted_claims, db_path=db_path)

    # Initial diff summary has all sections/claims added
    diff_summary = {
        "base_version": 0,
        "new_version": 1,
        "added_sections": list(sec.keys()),
        "modified_sections": [],
        "removed_sections": [],
        "added_claims_count": len(persisted_claims),
        "modified_claims_count": 0,
        "removed_claims_count": 0,
        "evidence_status_changes": {},
    }

    res_rev = save_manuscript_revision_db(
        revision_id=rev_id,
        manuscript_id=mid,
        version=1,
        title=title,
        author_notes=author_notes,
        sections=sec,
        claims=persisted_claims,
        references=refs,
        evidence_matrix=ev_mat,
        diff_summary=diff_summary,
        db_path=db_path,
    )

    ms = Manuscript(
        manuscript_id=res_m["manuscript_id"],
        project_id=res_m["project_id"],
        title=res_m["title"],
        current_version=1,
        brief_id=res_m.get("brief_id"),
        review_id=res_m.get("review_id"),
        created_at=res_m["created_at"],
        updated_at=res_m["updated_at"],
    )

    rev = ManuscriptRevision(
        revision_id=res_rev["revision_id"],
        manuscript_id=res_rev["manuscript_id"],
        version=1,
        title=res_rev["title"],
        author_notes=res_rev["author_notes"],
        sections=res_rev["sections"],
        claims=res_rev["claims"],
        references=res_rev["references"],
        evidence_matrix=res_rev["evidence_matrix"],
        diff_summary=res_rev["diff_summary"],
        created_at=res_rev["created_at"],
    )

    return ms, rev


def save_manuscript_revision(
    manuscript_id: str,
    title: str,
    sections: Dict[str, Any],
    claims: List[Dict[str, Any]],
    references: List[Dict[str, Any]],
    evidence_matrix: Optional[Dict[str, Any]] = None,
    author_notes: str = "",
    base_version: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> ManuscriptRevision:
    """
    Save a new non-destructive revision of an existing manuscript.
    Verifies base_version to guard against stale edits or collisions.
    Calculates detailed diff across sections, claims, and evidential status.
    """
    ms_dict = get_manuscript_db(manuscript_id, db_path=db_path)
    if not ms_dict:
        raise ValueError(f"Manuscript '{manuscript_id}' not found.")

    curr_ver = ms_dict["current_version"]
    if base_version is not None and base_version != curr_ver:
        raise ValueError(
            f"Stale edit conflict: manuscript '{manuscript_id}' is at version {curr_ver}, "
            f"but edit was based on version {base_version}."
        )

    prev_rev = get_manuscript_revision_db(manuscript_id, curr_ver, db_path=db_path)
    next_ver = curr_ver + 1
    rev_id = f"rev_{uuid.uuid4().hex[:12]}"

    # Diff analysis against previous revision
    diff_summary = _compute_revision_diff(
        prev_sections=prev_rev.get("sections", {}) if prev_rev else {},
        next_sections=sections,
        prev_claims=prev_rev.get("claims", []) if prev_rev else [],
        next_claims=claims,
        prev_refs=prev_rev.get("references", []) if prev_rev else [],
        next_refs=references,
        base_version=curr_ver,
        next_version=next_ver,
    )

    # Batch save claims
    persisted_claims = []
    for c in claims:
        cid = c.get("claim_id") or f"clm_{uuid.uuid4().hex[:10]}"
        persisted_claims.append({
            "claim_id": cid,
            "manuscript_id": manuscript_id,
            "revision_id": rev_id,
            "section": c.get("section", "Findings"),
            "claim_text": c.get("claim_text", ""),
            "evidence_status": c.get("evidence_status", "UNVERIFIED"),
            "supporting_sources": c.get("supporting_sources", []),
            "counter_sources": c.get("counter_sources", []),
            "confidence": float(c.get("confidence", 0.0)),
            "reasoning": c.get("reasoning", ""),
            "uncertainties": c.get("uncertainties", ""),
        })

    if persisted_claims:
        save_manuscript_claims_batch_db(persisted_claims, db_path=db_path)

    res_rev = save_manuscript_revision_db(
        revision_id=rev_id,
        manuscript_id=manuscript_id,
        version=next_ver,
        title=title,
        author_notes=author_notes,
        sections=sections,
        claims=persisted_claims,
        references=references,
        evidence_matrix=evidence_matrix or (prev_rev.get("evidence_matrix", {}) if prev_rev else {}),
        diff_summary=diff_summary,
        db_path=db_path,
    )

    return ManuscriptRevision(
        revision_id=res_rev["revision_id"],
        manuscript_id=res_rev["manuscript_id"],
        version=next_ver,
        title=res_rev["title"],
        author_notes=res_rev["author_notes"],
        sections=res_rev["sections"],
        claims=res_rev["claims"],
        references=res_rev["references"],
        evidence_matrix=res_rev["evidence_matrix"],
        diff_summary=res_rev["diff_summary"],
        created_at=res_rev["created_at"],
    )


def get_manuscript(manuscript_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Manuscript]:
    res = get_manuscript_db(manuscript_id, db_path=db_path)
    if not res:
        return None
    return Manuscript(
        manuscript_id=res["manuscript_id"],
        project_id=res["project_id"],
        title=res["title"],
        current_version=res["current_version"],
        brief_id=res.get("brief_id"),
        review_id=res.get("review_id"),
        created_at=res.get("created_at", ""),
        updated_at=res.get("updated_at", ""),
    )


def get_manuscript_revision(
    manuscript_id: str,
    version: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[ManuscriptRevision]:
    ms = get_manuscript(manuscript_id, db_path=db_path)
    if not ms:
        return None
    ver = version if version is not None else ms.current_version
    res = get_manuscript_revision_db(manuscript_id, ver, db_path=db_path)
    if not res:
        return None
    return ManuscriptRevision(
        revision_id=res["revision_id"],
        manuscript_id=res["manuscript_id"],
        version=res["version"],
        title=res["title"],
        author_notes=res.get("author_notes", ""),
        sections=res.get("sections", {}),
        claims=res.get("claims", []),
        references=res.get("references", []),
        evidence_matrix=res.get("evidence_matrix", {}),
        diff_summary=res.get("diff_summary", {}),
        created_at=res.get("created_at", ""),
    )


def list_manuscripts(project_id: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> List[Manuscript]:
    rows = list_manuscripts_db(project_id=project_id, db_path=db_path)
    return [
        Manuscript(
            manuscript_id=r["manuscript_id"],
            project_id=r["project_id"],
            title=r["title"],
            current_version=r["current_version"],
            brief_id=r.get("brief_id"),
            review_id=r.get("review_id"),
            created_at=r.get("created_at", ""),
            updated_at=r.get("updated_at", ""),
        )
        for r in rows
    ]


def list_manuscript_revisions(manuscript_id: str, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    return list_manuscript_revisions_db(manuscript_id, db_path=db_path)


def create_manuscript_from_brief_and_review(
    project_id: str,
    brief_id: str,
    review_id: str,
    title: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Tuple[Manuscript, ManuscriptRevision]:
    """
    Instantiate an academic manuscript populated with sections, claims,
    and citations from an approved research brief and PRISMA review.
    """
    brief = get_brief_db(brief_id, db_path=db_path)
    if not brief:
        raise ValueError(f"Brief '{brief_id}' not found.")

    review = get_prisma_review_db(review_id, db_path=db_path)
    if not review:
        raise ValueError(f"PRISMA review '{review_id}' not found.")

    ms_title = title or f"Systematic Review & Synthesis: {brief.get('topic', 'Academic Research')}"
    ev_matrix = review.get("evidence_matrix", {})
    studies = ev_matrix.get("studies") or ev_matrix.get("included_studies", [])
    contradictions = ev_matrix.get("contradictions") or ev_matrix.get("dialectical_contradictions", [])

    # Build initial sections
    sections = {
        "abstract": {
            "heading": "Abstract",
            "content": f"This manuscript provides an evidence-based systematic investigation into '{brief.get('topic', '')}'. Synthesizing {len(studies)} peer-reviewed studies under PRISMA 2020 protocol.",
            "order": 1,
            "section_type": "standard",
        },
        "introduction": {
            "heading": "Introduction & Research Question",
            "content": f"Research Question: {brief.get('topic', '')}\n\nObjectives:\n" + "\n".join(f"- {o}" for o in brief.get("objectives", [])) + "\n\nCore Hypotheses:\n" + "\n".join(f"- {h}" for h in brief.get("hypotheses", [])),
            "order": 2,
            "section_type": "standard",
        },
        "methodology": {
            "heading": "Methodology & PRISMA Review Protocol",
            "content": "Protocol Design:\n"
            f"- Databases Searched: {json.dumps(review.get('protocol', {}).get('databases', ['PubMed', 'ArXiv', 'Europe PMC']))}\n"
            f"- Eligibility Criteria: {json.dumps(review.get('protocol', {}).get('eligibility_criteria', []))}\n"
            f"- Screening Protocol: Double-pass title/abstract screening followed by full-text appraisal.",
            "order": 3,
            "section_type": "methodology",
        },
        "results": {
            "heading": "Evidence-Based Results & Study Appraisal",
            "content": f"A total of {len(studies)} studies met all inclusion criteria. Appraisals evaluated methodological rigor, sample validity, and risk of bias across reports.",
            "order": 4,
            "section_type": "results",
        },
        "discussion": {
            "heading": "Dialectical Discussion & Counter-Evidence",
            "content": "Synthesis of findings alongside counter-evidence identified during screening.\n\nContradiction Analyses:\n"
            + "\n".join(
                f"- Hypothesis: {c.get('focal_hypothesis') or c.get('hypothesis')}\n  Supporting: {c.get('supporting_study_ids') or c.get('supporting_study_id')} | Opposing: {c.get('counter_study_ids')} | Divergence: {c.get('substantive_divergence') or c.get('opposing_finding')} | Resolution: {c.get('resolution_requirements') or c.get('synthesis_notes')}"
                for c in contradictions
            ) if contradictions else "No direct dialectical contradictions detected across included studies.",
            "order": 5,
            "section_type": "discussion",
        },
        "limitations": {
            "heading": "Limitations & Unresolved Questions",
            "content": "Known uncertainties and methodological boundaries:\n"
            + "\n".join(f"- {q}" for q in brief.get("unresolved_questions", []))
            + "\n- Non-retrieved preprints and grey literature could present unobserved confounding effects.",
            "order": 6,
            "section_type": "standard",
        },
        "conclusion": {
            "heading": "Conclusion & Future Research",
            "content": "Synthesized evidence substantiates conditional adoption of hypotheses while mandating follow-up empirical validation on unobserved edge cases.",
            "order": 7,
            "section_type": "standard",
        },
    }

    # Build claims from brief hypotheses and study evidence
    claims = []
    references = []
    seen_sources = set()

    # Create claims for each hypothesis
    for idx, hyp in enumerate(brief.get("hypotheses", [])):
        cid = f"clm_hyp_{idx+1}"
        supp_sources = []
        counter_sources = []

        # Find matching studies from evidence matrix
        for s in studies:
            sid = s.get("study_id", "")
            finding_text = (
                s.get("synthesized_findings")
                or ("; ".join(s.get("key_findings", [])) if s.get("key_findings") else "")
                or s.get("title", "")
            )
            doi_val = s.get("doi") or s.get("doi_or_url", "")
            src_url = s.get("source_url") or (doi_val if "http" in doi_val else "")
            rel = str(s.get("hypothesis_relation", "")).upper()

            if "CHALLENGE" in rel or "CONTRADICT" in rel:
                counter_sources.append({
                    "study_id": sid,
                    "source_id": s.get("report_ids", [sid])[0] if s.get("report_ids") else s.get("primary_source_id", sid),
                    "citation_key": sid.replace("-", "_").replace(" ", "_"),
                    "counter_finding": finding_text,
                })
            else:
                supp_sources.append({
                    "study_id": sid,
                    "source_id": s.get("report_ids", [sid])[0] if s.get("report_ids") else s.get("primary_source_id", sid),
                    "citation_key": sid.replace("-", "_").replace(" ", "_"),
                    "finding": finding_text,
                })

            if sid not in seen_sources:
                seen_sources.add(sid)
                pub_yr = s.get("published_year") or s.get("year")
                year_int = int(pub_yr) if pub_yr and str(pub_yr).isdigit() else datetime.datetime.now().year
                references.append({
                    "citation_key": sid.replace("-", "_").replace(" ", "_"),
                    "title": s.get("title") or finding_text[:80] or f"Study {sid}",
                    "authors": s.get("authors") or ["THOTH Research Synthesis"],
                    "year": year_int,
                    "study_id": sid,
                    "doi": doi_val,
                    "source_url": src_url,
                    "verified": bool(doi_val),
                })

        # Match contradiction / counter-evidence from explicit contradiction entries
        for c in contradictions:
            focal_hyp = c.get("focal_hypothesis") or c.get("hypothesis", "")
            if focal_hyp and (focal_hyp.strip().lower() in hyp.strip().lower() or hyp.strip().lower() in focal_hyp.strip().lower()):
                opposing_id = (
                    ", ".join(c.get("counter_study_ids", []))
                    if isinstance(c.get("counter_study_ids"), list)
                    else c.get("supporting_study_id", "")
                )
                counter_sources.append({
                    "study_id": opposing_id,
                    "counter_finding": c.get("substantive_divergence") or c.get("opposing_finding", ""),
                    "dialectic_note": c.get("resolution_requirements") or c.get("synthesis_notes", ""),
                })

        status = "QUALIFIED" if counter_sources else ("SUPPORTED" if supp_sources else "UNVERIFIED")

        claims.append({
            "claim_id": cid,
            "section": "results",
            "claim_text": hyp,
            "evidence_status": status,
            "supporting_sources": supp_sources,
            "counter_sources": counter_sources,
            "confidence": 0.85 if supp_sources and not counter_sources else 0.65,
            "reasoning": "Derived from approved research brief and substantiated by PRISMA 2020 included studies.",
            "uncertainties": "Subject to limitations outlined in PRISMA appraisal matrix.",
        })

    return create_manuscript(
        project_id=project_id,
        title=ms_title,
        brief_id=brief_id,
        review_id=review_id,
        initial_sections=sections,
        initial_claims=claims,
        initial_references=references,
        initial_evidence_matrix=ev_matrix,
        author_notes=f"Generated from research brief '{brief_id}' and PRISMA review '{review_id}'",
        db_path=db_path,
    )


def propose_claim_qualifications_from_evidence(
    manuscript_id: str,
    new_evidence_items: List[Dict[str, Any]],
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Inspect manuscript claims against newly discovered counter-evidence or opposing findings.
    Proposes claim qualifications without silently rewriting author's text.
    """
    ms = get_manuscript(manuscript_id, db_path=db_path)
    if not ms:
        raise ValueError(f"Manuscript '{manuscript_id}' not found.")

    rev = get_manuscript_revision(manuscript_id, ms.current_version, db_path=db_path)
    if not rev:
        return []

    proposals = []
    for claim in rev.claims:
        cid = claim.get("claim_id")
        ctext = claim.get("claim_text", "").lower()
        current_status = claim.get("evidence_status", "UNVERIFIED")

        matched_evidence = []
        for ev in new_evidence_items:
            # Direct target match by claim_id
            if ev.get("claim_id") and ev.get("claim_id") == cid:
                matched_evidence.append(ev)
                continue

            ev_summary = ev.get("finding", "") or ev.get("opposing_finding", "") or ev.get("excerpt", "") or ev.get("qualification", "")
            # Semantic keyword overlap
            ev_words = [w for w in re.findall(r'\b\w{4,}\b', ev_summary.lower())]
            if any(w in ctext for w in ev_words):
                matched_evidence.append(ev)

        if matched_evidence:
            qual_text = matched_evidence[0].get("qualification") or (
                f"Newly identified findings indicate counter-evidence or conditional boundary: "
                f"{matched_evidence[0].get('finding', 'opposing finding')}"
            )
            proposals.append({
                "claim_id": cid,
                "claim_text": claim.get("claim_text"),
                "current_status": current_status,
                "proposed_status": "QUALIFIED" if current_status == "SUPPORTED" else "CHALLENGED",
                "matched_counter_evidence": matched_evidence,
                "qualification": qual_text,
                "qualification_rationale": qual_text,
                "suggested_qualification_text": (
                    f"{claim.get('claim_text')} However, this effect is qualified under conditions noted in "
                    f"{[e.get('study_id', e.get('counter_source_id', 'new evidence')) for e in matched_evidence]}."
                ),
            })

    return proposals


def _compute_revision_diff(
    prev_sections: Dict[str, Any],
    next_sections: Dict[str, Any],
    prev_claims: List[Dict[str, Any]],
    next_claims: List[Dict[str, Any]],
    prev_refs: List[Dict[str, Any]],
    next_refs: List[Dict[str, Any]],
    base_version: int,
    next_version: int,
) -> Dict[str, Any]:
    """Compute detailed diff across sections, claims, and references."""
    prev_sec_keys = set(prev_sections.keys())
    next_sec_keys = set(next_sections.keys())

    added_sec = list(next_sec_keys - prev_sec_keys)
    removed_sec = list(prev_sec_keys - next_sec_keys)
    modified_sec = []
    for k in next_sec_keys.intersection(prev_sec_keys):
        p_c = prev_sections[k].get("content", "") if isinstance(prev_sections[k], dict) else str(prev_sections[k])
        n_c = next_sections[k].get("content", "") if isinstance(next_sections[k], dict) else str(next_sections[k])
        if p_c != n_c:
            modified_sec.append(k)

    # Claim tracking by claim_id
    prev_claims_by_id = {c["claim_id"]: c for c in prev_claims if "claim_id" in c}
    next_claims_by_id = {c["claim_id"]: c for c in next_claims if "claim_id" in c}

    added_claims = [c for cid, c in next_claims_by_id.items() if cid not in prev_claims_by_id]
    removed_claims = [c for cid, c in prev_claims_by_id.items() if cid not in next_claims_by_id]
    wording_changed_only = []
    evidence_changed = []
    status_changes = {}

    for cid, n_c in next_claims_by_id.items():
        if cid in prev_claims_by_id:
            p_c = prev_claims_by_id[cid]
            p_text = p_c.get("claim_text", "")
            n_text = n_c.get("claim_text", "")
            p_supp = p_c.get("supporting_sources", [])
            n_supp = n_c.get("supporting_sources", [])
            p_counter = p_c.get("counter_sources", [])
            n_counter = n_c.get("counter_sources", [])
            p_stat = p_c.get("evidence_status", "UNVERIFIED")
            n_stat = n_c.get("evidence_status", "UNVERIFIED")

            if p_stat != n_stat:
                status_changes[cid] = {"from": p_stat, "to": n_stat}

            ev_diff = (p_supp != n_supp) or (p_counter != n_counter)
            text_diff = (p_text != n_text)

            if text_diff and not ev_diff:
                wording_changed_only.append(cid)
            elif ev_diff:
                evidence_changed.append(cid)

    # Citations diff
    prev_cite_keys = {r.get("citation_key") for r in prev_refs if r.get("citation_key")}
    next_cite_keys = {r.get("citation_key") for r in next_refs if r.get("citation_key")}

    return {
        "base_version": base_version,
        "new_version": next_version,
        "added_sections": added_sec,
        "modified_sections": modified_sec,
        "removed_sections": removed_sec,
        "added_claims_count": len(added_claims),
        "removed_claims_count": len(removed_claims),
        "wording_changed_claims": wording_changed_only,
        "evidence_changed_claims": evidence_changed,
        "evidence_status_changes": status_changes,
        "citations_added": list(next_cite_keys - prev_cite_keys),
        "citations_removed": list(prev_cite_keys - next_cite_keys),
    }


def _default_academic_sections(title: str) -> Dict[str, Any]:
    return {
        "abstract": {
            "heading": "Abstract",
            "content": f"Executive abstract for manuscript: {title}.",
            "order": 1,
            "section_type": "standard",
        },
        "introduction": {
            "heading": "Introduction",
            "content": "Contextual introduction and research questions.",
            "order": 2,
            "section_type": "standard",
        },
        "methodology": {
            "heading": "Methodology",
            "content": "Protocol, selection criteria, and review methodology.",
            "order": 3,
            "section_type": "methodology",
        },
        "results": {
            "heading": "Results",
            "content": "Empirical results and synthesized evidence matrix findings.",
            "order": 4,
            "section_type": "results",
        },
        "discussion": {
            "heading": "Discussion",
            "content": "Critical discussion, counter-evidence, and dialectic appraisal.",
            "order": 5,
            "section_type": "discussion",
        },
        "conclusion": {
            "heading": "Conclusion",
            "content": "Summary of findings and future research directions.",
            "order": 6,
            "section_type": "standard",
        },
    }
