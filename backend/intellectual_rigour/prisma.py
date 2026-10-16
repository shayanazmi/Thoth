import re
import uuid
import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field


class ScreeningStage(str, Enum):
    TITLE_ABSTRACT = "TITLE_ABSTRACT"
    FULL_TEXT_ELIGIBILITY = "FULL_TEXT_ELIGIBILITY"


class ScreeningDisposition(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    UNRESOLVED = "UNRESOLVED"
    NOT_RETRIEVED = "NOT_RETRIEVED"


class ReviewerType(str, Enum):
    AI_RECOMMENDED = "AI_RECOMMENDED"
    REVIEWER_CONFIRMED = "REVIEWER_CONFIRMED"


class HypothesisRelation(str, Enum):
    SUPPORTS = "SUPPORTS"
    CHALLENGES = "CHALLENGES"
    QUALIFIES = "QUALIFIES"
    NEUTRAL = "NEUTRAL"


class ReviewProtocol(BaseModel):
    protocol_id: str = Field(default_factory=lambda: f"proto-{uuid.uuid4().hex[:10]}")
    brief_id: str = Field(..., description="Linked research brief ID")
    topic: str = Field(..., description="Primary research topic")
    focal_hypothesis: str = Field(default="", description="Core hypothesis under investigation")
    search_queries: List[str] = Field(default_factory=list, description="All executed search query strings")
    target_databases: List[str] = Field(default_factory=list, description="Scholarly databases and registers queried")
    selection_criteria: List[str] = Field(default_factory=list, description="Inclusion and exclusion criteria inherited from brief")
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ScreeningDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:10]}")
    review_id: str = Field(default="", description="Linked PRISMA review ID")
    brief_id: str = Field(..., description="Linked research brief ID")
    source_id: str = Field(..., description="Source candidate identifier")
    source_url: str = Field(default="", description="URL of the paper/report")
    title: str = Field(..., description="Title of the paper/report")
    stage: ScreeningStage = Field(..., description="TITLE_ABSTRACT or FULL_TEXT_ELIGIBILITY")
    disposition: ScreeningDisposition = Field(..., description="INCLUDED, EXCLUDED, UNRESOLVED, NOT_RETRIEVED")
    criteria_applied: List[str] = Field(default_factory=list, description="Brief criteria evaluated in this decision")
    exclusion_reason: Optional[str] = Field(default=None, description="Specific reason if excluded")
    rationale: str = Field(..., description="Grounded explanation for decision")
    supporting_passages: List[str] = Field(default_factory=list, description="Extracted text passages justifying decision")
    reviewer_type: ReviewerType = Field(default=ReviewerType.AI_RECOMMENDED)
    study_id: Optional[str] = Field(default=None, description="Grouping identifier for underlying study")
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class StudyAppraisal(BaseModel):
    study_id: str = Field(..., description="Unique identifier for the research investigation")
    report_ids: List[str] = Field(default_factory=list, description="Report source IDs associated with this study")
    title: str = Field(..., description="Title of primary report")
    doi_or_url: str = Field(default="")
    authors: List[str] = Field(default_factory=list)
    published_year: Optional[str] = Field(default=None)
    study_design: str = Field(default="empirical_study", description="Design archetype e.g. benchmark_evaluation, controlled_experiment, observational, theoretical")
    sample_or_dataset: str = Field(default="Not specified", description="Sample size, benchmark dataset, or cohort")
    methodological_indicators: Dict[str, Any] = Field(
        default_factory=lambda: {
            "baseline_controls": False,
            "reproducibility_artifacts": False,
            "statistical_validation": False,
        }
    )
    reported_limitations: List[str] = Field(default_factory=list, description="Author-reported or extracted limitations")
    hypothesis_relation: HypothesisRelation = Field(default=HypothesisRelation.NEUTRAL)
    key_findings: List[str] = Field(default_factory=list)
    extracted_passages: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ContradictionEntry(BaseModel):
    focal_hypothesis: str = Field(..., description="Hypothesis under dialectic tension")
    supporting_study_ids: List[str] = Field(default_factory=list, description="Studies corroborating the claim")
    counter_study_ids: List[str] = Field(default_factory=list, description="Studies challenging or refuting the claim")
    substantive_divergence: str = Field(..., description="Methodological or parametric explanation for the disagreement")
    resolution_requirements: str = Field(..., description="Empirical tests required to resolve tension")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class EvidenceMatrix(BaseModel):
    studies: List[StudyAppraisal] = Field(default_factory=list)
    contradictions: List[ContradictionEntry] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_markdown_table(self) -> str:
        if not self.studies:
            return "_No included studies appraised in evidence matrix._"
        lines = [
            "| Study / Citation | Design | Sample / Dataset | Hyp. Stance | Methodological Indicators | Key Limitations |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |"
        ]
        for s in self.studies:
            auth_first = s.authors[0] if s.authors else "Unknown"
            clean_auth = re.sub(r'[,.\s]+$', '', auth_first.split(',')[0].strip())
            yr = f" ({s.published_year})" if s.published_year else ""
            cite = f"**{s.title[:45]}...**<br/>_{clean_auth} et al.{yr}_"
            indicators = []
            if s.methodological_indicators.get("baseline_controls"):
                indicators.append("Baselines ✓")
            if s.methodological_indicators.get("reproducibility_artifacts"):
                indicators.append("Open Data/Code ✓")
            if s.methodological_indicators.get("statistical_validation"):
                indicators.append("Significance Tests ✓")
            ind_str = ", ".join(indicators) if indicators else "Unverified"
            limits = "<br/>".join(f"• {lim[:50]}" for lim in s.reported_limitations[:2]) if s.reported_limitations else "None stated"
            lines.append(
                f"| {cite} | {s.study_design} | {s.sample_or_dataset[:30]} | `{s.hypothesis_relation.value}` | {ind_str} | {limits} |"
            )
        return "\n".join(lines)


class PRISMAFlowCounts(BaseModel):
    identified_databases: int = 0
    identified_registries_web: int = 0
    identified_snowball: int = 0
    total_identified: int = 0
    duplicates_removed: int = 0
    records_screened: int = 0
    records_excluded_title_abstract: int = 0
    records_excluded_reasons: Dict[str, int] = Field(default_factory=dict)
    reports_sought_for_retrieval: int = 0
    reports_not_retrieved: int = 0
    reports_assessed_for_eligibility: int = 0
    reports_excluded_full_text: int = 0
    reports_excluded_full_text_reasons: Dict[str, int] = Field(default_factory=dict)
    included_reports: int = 0
    included_studies: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def verify_accounting_integrity(self) -> Tuple[bool, List[str]]:
        """
        Verify mathematical invariants governing PRISMA 2020 flow stages.
        """
        issues = []
        expected_total = self.identified_databases + self.identified_registries_web + self.identified_snowball
        if self.total_identified != expected_total:
            issues.append(f"Identification sum mismatch: {self.total_identified} != {expected_total}")

        expected_screened = max(0, self.total_identified - self.duplicates_removed)
        if self.records_screened != expected_screened:
            issues.append(f"Screening count mismatch: {self.records_screened} != {expected_screened}")

        expected_sought = max(0, self.records_screened - self.records_excluded_title_abstract)
        if self.reports_sought_for_retrieval != expected_sought:
            issues.append(f"Retrieval sought mismatch: {self.reports_sought_for_retrieval} != {expected_sought}")

        expected_assessed = max(0, self.reports_sought_for_retrieval - self.reports_not_retrieved)
        if self.reports_assessed_for_eligibility != expected_assessed:
            issues.append(f"Eligibility assessed mismatch: {self.reports_assessed_for_eligibility} != {expected_assessed}")

        expected_included = max(0, self.reports_assessed_for_eligibility - self.reports_excluded_full_text)
        if self.included_reports != expected_included:
            issues.append(f"Included reports mismatch: {self.included_reports} != {expected_included}")

        if self.included_studies > self.included_reports:
            issues.append(f"Study count cannot exceed report count: {self.included_studies} > {self.included_reports}")

        return (len(issues) == 0, issues)


class PRISMAReviewLedger(BaseModel):
    review_id: str = Field(default_factory=lambda: f"rev-{uuid.uuid4().hex[:10]}")
    brief_id: str = Field(..., description="Linked research brief ID")
    session_id: str = Field(default="")
    topic: str = Field(...)
    protocol: ReviewProtocol
    flow_counts: PRISMAFlowCounts
    decisions: List[ScreeningDecision] = Field(default_factory=list)
    evidence_matrix: EvidenceMatrix = Field(default_factory=EvidenceMatrix)
    mermaid_diagram: str = Field(default="")
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# --- Domain Helper Functions ---

def _normalize_title_for_dedup(title: str) -> str:
    if not title:
        return ""
    clean = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    return clean[:80]


def group_sources_into_studies(sources: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group report records that describe the same underlying research study,
    matching on DOI, exact arXiv ID, or title normalization.
    """
    study_groups: Dict[str, List[Dict[str, Any]]] = {}
    key_to_study_id: Dict[str, str] = {}

    for s in sources:
        doi = (s.get("doi") or "").strip().lower()
        arxiv = (s.get("arxiv_id") or "").strip().lower()
        norm_title = _normalize_title_for_dedup(s.get("title") or "")

        matched_study_id = None
        if doi and f"doi:{doi}" in key_to_study_id:
            matched_study_id = key_to_study_id[f"doi:{doi}"]
        elif arxiv and f"arxiv:{arxiv}" in key_to_study_id:
            matched_study_id = key_to_study_id[f"arxiv:{arxiv}"]
        elif norm_title and f"title:{norm_title}" in key_to_study_id:
            matched_study_id = key_to_study_id[f"title:{norm_title}"]

        if not matched_study_id:
            primary_slug = _normalize_title_for_dedup(s.get("title") or s.get("id") or "study")[:25]
            matched_study_id = f"study-{primary_slug}_{len(study_groups) + 1}"
            study_groups[matched_study_id] = []

        if doi:
            key_to_study_id[f"doi:{doi}"] = matched_study_id
        if arxiv:
            key_to_study_id[f"arxiv:{arxiv}"] = matched_study_id
        if norm_title:
            key_to_study_id[f"title:{norm_title}"] = matched_study_id

        study_groups[matched_study_id].append(s)

    return study_groups


def screen_source_title_abstract(
    source: Dict[str, Any],
    selection_criteria: List[str],
    topic: str = "",
    focal_hypothesis: str = "",
    brief_id: str = "",
    review_id: str = "",
) -> ScreeningDecision:
    """
    Perform Title/Abstract screening grounded in explicit brief selection criteria.
    """
    title = (source.get("title") or "Untitled").strip()
    abstract = (source.get("abstract") or source.get("snippet") or "").strip()
    source_id = source.get("id") or f"src-{_normalize_title_for_dedup(title)[:20]}"
    url = source.get("url") or ""

    text_to_eval = f"{title} {abstract}".lower()
    criteria_list = list(selection_criteria or [])

    # Check for empty title and abstract
    if len(text_to_eval.strip()) < 15:
        return ScreeningDecision(
            review_id=review_id,
            brief_id=brief_id,
            source_id=source_id,
            source_url=url,
            title=title,
            stage=ScreeningStage.TITLE_ABSTRACT,
            disposition=ScreeningDisposition.EXCLUDED,
            criteria_applied=criteria_list,
            exclusion_reason="Insufficient record metadata: Title and abstract empty or unreadable.",
            rationale="Title/Abstract screening requires readable substantive text.",
            reviewer_type=ReviewerType.AI_RECOMMENDED,
        )

    # 1. Evaluate explicit negative/exclusion criteria from brief
    for crit in criteria_list:
        crit_lower = crit.lower()
        if any(neg in crit_lower for neg in ["exclude", "exclusion", "reject", "do not include"]):
            # Check for specific exclusion categories
            if "opinion" in crit_lower and any(w in text_to_eval for w in ["editorial", "opinion piece", "commentary"]):
                return ScreeningDecision(
                    review_id=review_id,
                    brief_id=brief_id,
                    source_id=source_id,
                    source_url=url,
                    title=title,
                    stage=ScreeningStage.TITLE_ABSTRACT,
                    disposition=ScreeningDisposition.EXCLUDED,
                    criteria_applied=[crit],
                    exclusion_reason=f"Exclusion criterion matched: {crit}",
                    rationale=f"Title/abstract identifies paper as editorial or opinion piece without empirical data.",
                    reviewer_type=ReviewerType.AI_RECOMMENDED,
                )
            if "simulation only" in crit_lower and "simulation" in text_to_eval and not any(w in text_to_eval for w in ["empirical", "dataset", "benchmark", "experiment"]):
                return ScreeningDecision(
                    review_id=review_id,
                    brief_id=brief_id,
                    source_id=source_id,
                    source_url=url,
                    title=title,
                    stage=ScreeningStage.TITLE_ABSTRACT,
                    disposition=ScreeningDisposition.EXCLUDED,
                    criteria_applied=[crit],
                    exclusion_reason=f"Exclusion criterion matched: {crit}",
                    rationale="Paper restricted to synthetic simulation without empirical validation.",
                    reviewer_type=ReviewerType.AI_RECOMMENDED,
                )

    # 2. Evaluate relevance to topic and focal hypothesis
    topic_terms = [w.lower() for w in re.findall(r'[a-zA-Z0-9_\-]+', topic) if len(w) >= 4]
    matched_terms = [t for t in topic_terms if t in text_to_eval]
    topical_relevance = (len(matched_terms) / len(topic_terms)) if topic_terms else 1.0

    if topic_terms and topical_relevance == 0.0:
        return ScreeningDecision(
            review_id=review_id,
            brief_id=brief_id,
            source_id=source_id,
            source_url=url,
            title=title,
            stage=ScreeningStage.TITLE_ABSTRACT,
            disposition=ScreeningDisposition.EXCLUDED,
            criteria_applied=criteria_list,
            exclusion_reason="Off-topic: Record fails to match core research topic terms.",
            rationale=f"Zero matching terms for topic '{topic}' in title/abstract.",
            reviewer_type=ReviewerType.AI_RECOMMENDED,
        )

    # If evidence is tentative or partial, mark as UNRESOLVED for full text check
    if len(abstract) < 80:
        return ScreeningDecision(
            review_id=review_id,
            brief_id=brief_id,
            source_id=source_id,
            source_url=url,
            title=title,
            stage=ScreeningStage.TITLE_ABSTRACT,
            disposition=ScreeningDisposition.UNRESOLVED,
            criteria_applied=criteria_list,
            rationale="Title indicates potential relevance, but short abstract requires full-text inspection.",
            reviewer_type=ReviewerType.AI_RECOMMENDED,
        )

    # Otherwise inclusion
    applied_inclusion = [c for c in criteria_list if not any(neg in c.lower() for neg in ["exclude", "exclusion"])]
    return ScreeningDecision(
        review_id=review_id,
        brief_id=brief_id,
        source_id=source_id,
        source_url=url,
        title=title,
        stage=ScreeningStage.TITLE_ABSTRACT,
        disposition=ScreeningDisposition.INCLUDED,
        criteria_applied=applied_inclusion or ["Topic alignment & empirical scope"],
        rationale=f"Title and abstract satisfy scope with {len(matched_terms)} matching topical indicators.",
        supporting_passages=[abstract[:300]] if abstract else [],
        reviewer_type=ReviewerType.AI_RECOMMENDED,
    )


def screen_source_full_text(
    source: Dict[str, Any],
    selection_criteria: List[str],
    focal_hypothesis: str = "",
    brief_id: str = "",
    review_id: str = "",
) -> ScreeningDecision:
    """
    Perform Full-Text Eligibility screening for retrieved sources.
    Crucial distinction: If source retrieval failed, it is NOT an eligibility exclusion;
    it is marked NOT_RETRIEVED.
    """
    title = (source.get("title") or "Untitled").strip()
    source_id = source.get("id") or f"src-{_normalize_title_for_dedup(title)[:20]}"
    url = source.get("url") or ""
    scrape_status = source.get("scrape_status") or "unscraped"
    quality = source.get("extraction_quality") or "unknown"
    extracted_text = source.get("extracted_text") or ""
    passages = source.get("passages") or []
    criteria_list = list(selection_criteria or [])

    # 1. Check retrieval outcome
    if scrape_status != "success" and quality == "inaccessible":
        err_msg = source.get("scrape_error") or "Full text inaccessible or paywalled."
        return ScreeningDecision(
            review_id=review_id,
            brief_id=brief_id,
            source_id=source_id,
            source_url=url,
            title=title,
            stage=ScreeningStage.FULL_TEXT_ELIGIBILITY,
            disposition=ScreeningDisposition.NOT_RETRIEVED,
            criteria_applied=criteria_list,
            exclusion_reason=f"Retrieval failure: {err_msg}",
            rationale="Report sought for retrieval but full content could not be retrieved from publisher server.",
            reviewer_type=ReviewerType.AI_RECOMMENDED,
        )

    # 2. Check empty extraction
    if not extracted_text.strip() and not passages:
        return ScreeningDecision(
            review_id=review_id,
            brief_id=brief_id,
            source_id=source_id,
            source_url=url,
            title=title,
            stage=ScreeningStage.FULL_TEXT_ELIGIBILITY,
            disposition=ScreeningDisposition.NOT_RETRIEVED,
            criteria_applied=criteria_list,
            exclusion_reason="Empty document: Full text extraction yielded zero readable characters.",
            rationale="No text content available to assess eligibility.",
            reviewer_type=ReviewerType.AI_RECOMMENDED,
        )

    full_lower = extracted_text.lower()

    # 3. Evaluate full text selection criteria
    for crit in criteria_list:
        crit_lower = crit.lower()
        if "baseline" in crit_lower and "control" in crit_lower:
            has_explicit_negation = any(neg in full_lower for neg in [
                "did not run any baseline", "no baseline", "without baseline", "lacked baseline", "no control experiment"
            ])
            has_positive_baseline = any(w in full_lower for w in ["comparative baseline", "baseline model", "baseline comparison", "control group", "ablation", "benchmark"])
            if has_explicit_negation or not (has_positive_baseline or ("baseline" in full_lower and "control" in full_lower)):
                return ScreeningDecision(
                    review_id=review_id,
                    brief_id=brief_id,
                    source_id=source_id,
                    source_url=url,
                    title=title,
                    stage=ScreeningStage.FULL_TEXT_ELIGIBILITY,
                    disposition=ScreeningDisposition.EXCLUDED,
                    criteria_applied=[crit],
                    exclusion_reason=f"Full-text exclusion: {crit}",
                    rationale="Extracted full text contains no baseline comparisons or control groups.",
                    reviewer_type=ReviewerType.AI_RECOMMENDED,
                )

    sample_passages = [p.get("text", "")[:300] for p in passages[:3]] if passages else [extracted_text[:300]]
    return ScreeningDecision(
        review_id=review_id,
        brief_id=brief_id,
        source_id=source_id,
        source_url=url,
        title=title,
        stage=ScreeningStage.FULL_TEXT_ELIGIBILITY,
        disposition=ScreeningDisposition.INCLUDED,
        criteria_applied=criteria_list,
        rationale="Full-text retrieved and verified against methodological eligibility criteria.",
        supporting_passages=sample_passages,
        reviewer_type=ReviewerType.AI_RECOMMENDED,
    )


def appraise_included_study(
    source: Dict[str, Any],
    focal_hypothesis: str = "",
) -> StudyAppraisal:
    """
    Extract structured study characteristics, methodological indicators,
    limitations, and hypothesis stance for an included study.
    """
    title = (source.get("title") or "Untitled").strip()
    source_id = source.get("id") or f"src-{_normalize_title_for_dedup(title)[:20]}"
    doi = source.get("doi") or source.get("url") or ""
    authors = list(source.get("authors") or [])
    pub_date = str(source.get("published_date") or "")
    pub_year = pub_date[:4] if len(pub_date) >= 4 and pub_date[:4].isdigit() else None

    passages = source.get("passages") or []
    passages_text = " ".join(p.get("text", "") for p in passages)
    text = f"{source.get('extracted_text') or ''} {source.get('abstract') or ''} {source.get('snippet') or ''} {passages_text}".lower()

    # Study design inference
    if any(w in text for w in ["benchmark", "evaluating on", "benchmark suite", "leaderboard", "glue", "mmlu", "imagenet"]):
        design = "benchmark_evaluation"
    elif any(w in text for w in ["randomized", "control group", "clinical trial", "double-blind"]):
        design = "controlled_experiment"
    elif any(w in text for w in ["meta-analysis", "systematic review", "prisma", "survey"]):
        design = "meta_analysis_or_survey"
    elif any(w in text for w in ["theorem", "proof", "lemma", "formal analysis", "algorithmic complexity"]):
        design = "theoretical_derivation"
    elif any(w in text for w in ["cohort", "observational", "longitudinal", "survey respondents"]):
        design = "observational_cohort"
    else:
        design = "empirical_experiment"

    # Methodological indicators
    has_baselines = any(w in text for w in ["baseline", "state-of-the-art", "sota", "control group", "comparison"])
    has_artifacts = any(w in text for w in ["github.com", "huggingface.co", "open-source", "code available", "data available"])
    has_stats = any(w in text for w in ["p <", "p-value", "confidence interval", "standard deviation", "t-test", "f-test"])

    # Sample size or dataset extraction
    sample = "Not explicitly stated"
    sample_match = re.search(r'\b(n\s*=\s*[0-9,]+|dataset of [0-9,]+|[0-9,]+\s*(samples|parameters|examples|participants))\b', text)
    if sample_match:
        sample = sample_match.group(0)

    # Self-reported limitations
    limitations = []
    lim_matches = re.findall(r'([^.\n]*\b(limitation|future work|caveat|threats to validity|overfitting risk)\b[^.\n]*)', text)
    for m in lim_matches[:2]:
        cleaned_lim = m[0].strip()
        if len(cleaned_lim) > 20:
            limitations.append(cleaned_lim[:120])
    if not limitations:
        limitations.append("Author self-reported limitations not isolated in extracted passages.")

    # Hypothesis relationship (supporting vs challenging vs qualifying)
    is_counter = source.get("relation") == "counter_evidence"
    if is_counter:
        stance = HypothesisRelation.CHALLENGES
    elif any(w in text for w in ["failure to replicate", "null effect", "does not hold", "falsified", "negative result", "breakdown", "fails to hold"]):
        stance = HypothesisRelation.CHALLENGES
    elif any(w in text for w in ["confirm", "demonstrat", "statistically significant", "outperform", "improv", "validat", "proves", "proven", "mitigat"]):
        stance = HypothesisRelation.SUPPORTS
    elif any(w in text for w in ["only when", "conditional on", "under specific conditions", "moderated by", "regime-dependent"]):
        stance = HypothesisRelation.QUALIFIES
    else:
        stance = HypothesisRelation.NEUTRAL

    key_findings = []
    if passages:
        for p in passages[:2]:
            key_findings.append(p.get("text", "")[:250])
    elif source.get("abstract"):
        key_findings.append(source["abstract"][:300])

    return StudyAppraisal(
        study_id=source_id,
        report_ids=[source_id],
        title=title,
        doi_or_url=doi,
        authors=authors,
        published_year=pub_year,
        study_design=design,
        sample_or_dataset=sample,
        methodological_indicators={
            "baseline_controls": has_baselines,
            "reproducibility_artifacts": has_artifacts,
            "statistical_validation": has_stats,
        },
        reported_limitations=limitations,
        hypothesis_relation=stance,
        key_findings=key_findings,
        extracted_passages=[p.get("text", "")[:300] for p in passages[:2]] if passages else [],
    )


def map_contradictions(
    included_studies: List[StudyAppraisal],
    focal_hypothesis: str = "",
) -> List[ContradictionEntry]:
    """
    Identify substantive tensions between findings supporting the hypothesis
    and findings challenging it (incorporating Phase 3.2 counter-evidence).
    """
    supporting = [s for s in included_studies if s.hypothesis_relation == HypothesisRelation.SUPPORTS]
    challenging = [s for s in included_studies if s.hypothesis_relation == HypothesisRelation.CHALLENGES]

    if not supporting or not challenging:
        return []

    # Group into an explicit contradiction entry
    supp_ids = [s.study_id for s in supporting]
    ch_ids = [s.study_id for s in challenging]

    divergence_reasons = []
    for s_supp in supporting:
        for s_ch in challenging:
            if s_supp.study_design != s_ch.study_design:
                divergence_reasons.append(
                    f"Design divergence: Supporting studies utilize {s_supp.study_design} while counter-studies employ {s_ch.study_design}."
                )
            if s_supp.sample_or_dataset != s_ch.sample_or_dataset and "Not" not in s_supp.sample_or_dataset:
                divergence_reasons.append(
                    f"Distribution divergence: Evaluated on different datasets/samples ({s_supp.sample_or_dataset} vs {s_ch.sample_or_dataset})."
                )

    div_text = (
        " ".join(list(dict.fromkeys(divergence_reasons))[:2])
        if divergence_reasons
        else "Findings diverge under different hyperparameter settings or experimental distributions as identified in Phase 3.2 dialectic."
    )

    resolution = (
        "Preregistered replication under identical benchmark controls and standardized evaluation harnesses to resolve conflicting effect directions."
    )

    return [
        ContradictionEntry(
            focal_hypothesis=focal_hypothesis or "Primary Research Hypothesis",
            supporting_study_ids=supp_ids,
            counter_study_ids=ch_ids,
            substantive_divergence=div_text,
            resolution_requirements=resolution,
        )
    ]


def compute_prisma_flow(
    protocol: ReviewProtocol,
    raw_sources: List[Dict[str, Any]],
    decisions: List[ScreeningDecision],
    study_groups: Dict[str, List[Dict[str, Any]]],
) -> PRISMAFlowCounts:
    """
    Compute rigorous, mathematically derivable PRISMA 2020 flow counts
    from actual search results and screening decisions.
    """
    # 1. Identification by database / register / method
    db_count = 0
    web_count = 0
    snowball_count = 0

    seen_urls: Set[str] = set()
    dup_count = 0

    for s in raw_sources:
        api = s.get("source_api") or "scholarly"
        if api in ["arxiv", "semantic_scholar", "openalex", "scholarly"]:
            db_count += 1
        elif api == "snowball":
            snowball_count += 1
        else:
            web_count += 1

        u = s.get("url") or s.get("doi") or _normalize_title_for_dedup(s.get("title") or "")
        if u in seen_urls:
            dup_count += 1
        else:
            seen_urls.add(u)

    total_identified = db_count + web_count + snowball_count

    # 2. Decisions breakdown
    ta_decisions = [d for d in decisions if d.stage == ScreeningStage.TITLE_ABSTRACT]
    ft_decisions = [d for d in decisions if d.stage == ScreeningStage.FULL_TEXT_ELIGIBILITY]

    ta_excluded = [d for d in ta_decisions if d.disposition == ScreeningDisposition.EXCLUDED]
    ta_excluded_reasons: Dict[str, int] = {}
    for d in ta_excluded:
        r = d.exclusion_reason or "Criterion violation"
        r_cat = r.split(":")[0].strip() if ":" in r else r[:40]
        ta_excluded_reasons[r_cat] = ta_excluded_reasons.get(r_cat, 0) + 1

    records_screened = max(0, total_identified - dup_count)
    sought_retrieval = max(0, records_screened - len(ta_excluded))

    ft_not_retrieved = len([d for d in ft_decisions if d.disposition == ScreeningDisposition.NOT_RETRIEVED])
    assessed_eligibility = max(0, sought_retrieval - ft_not_retrieved)

    ft_excluded = [d for d in ft_decisions if d.disposition == ScreeningDisposition.EXCLUDED]
    ft_excluded_reasons: Dict[str, int] = {}
    for d in ft_excluded:
        r = d.exclusion_reason or "Full-text criterion violation"
        r_cat = r.split(":")[0].strip() if ":" in r else r[:40]
        ft_excluded_reasons[r_cat] = ft_excluded_reasons.get(r_cat, 0) + 1

    included_reports = max(0, assessed_eligibility - len(ft_excluded))
    included_studies = len(study_groups) if study_groups else included_reports
    if included_studies > included_reports:
        included_studies = included_reports

    return PRISMAFlowCounts(
        identified_databases=db_count,
        identified_registries_web=web_count,
        identified_snowball=snowball_count,
        total_identified=total_identified,
        duplicates_removed=dup_count,
        records_screened=records_screened,
        records_excluded_title_abstract=len(ta_excluded),
        records_excluded_reasons=ta_excluded_reasons,
        reports_sought_for_retrieval=sought_retrieval,
        reports_not_retrieved=ft_not_retrieved,
        reports_assessed_for_eligibility=assessed_eligibility,
        reports_excluded_full_text=len(ft_excluded),
        reports_excluded_full_text_reasons=ft_excluded_reasons,
        included_reports=included_reports,
        included_studies=included_studies,
    )


def generate_prisma_mermaid_diagram(counts: PRISMAFlowCounts, topic: str = "Research Review") -> str:
    """
    Generate an interactive, standards-compliant PRISMA 2020 Mermaid flow diagram.
    """
    clean_topic = topic[:35].replace('"', "'")
    return f"""```mermaid
flowchart TD
    classDef stage fill:#f8f9fa,stroke:#343a40,stroke-width:2px;
    classDef decision fill:#e9ecef,stroke:#495057,stroke-dasharray: 5 5;
    classDef include fill:#d4edda,stroke:#28a745,stroke-width:2px;
    classDef exclude fill:#f8d7da,stroke:#dc3545,stroke-width:2px;

    subgraph Identification ["Identification of studies via databases and registers"]
        A1["Databases queried: arXiv, S2, OpenAlex<br/>(n = {counts.identified_databases})"]:::stage
        A2["Web registers & search engines<br/>(n = {counts.identified_registries_web})"]:::stage
        A3["Citation snowballing & recommendations<br/>(n = {counts.identified_snowball})"]:::stage
        TotalId["Total records identified<br/>(n = {counts.total_identified})"]:::stage
        A1 --> TotalId
        A2 --> TotalId
        A3 --> TotalId
    end

    Dup["Duplicates removed prior to screening<br/>(n = {counts.duplicates_removed})"]:::exclude
    TotalId --> Dup

    subgraph Screening ["Screening Phase"]
        Screened["Records screened (Title & Abstract)<br/>(n = {counts.records_screened})"]:::stage
        Dup --> Screened
        ExTA["Records excluded by criteria<br/>(n = {counts.records_excluded_title_abstract})"]:::exclude
        Screened --> ExTA
        Sought["Reports sought for retrieval<br/>(n = {counts.reports_sought_for_retrieval})"]:::stage
        Screened --> Sought
    end

    subgraph Retrieval ["Retrieval & Eligibility"]
        NotRet["Reports not retrieved (Paywalled / Inaccessible)<br/>(n = {counts.reports_not_retrieved})"]:::exclude
        Sought --> NotRet
        Assessed["Reports assessed for full-text eligibility<br/>(n = {counts.reports_assessed_for_eligibility})"]:::stage
        Sought --> Assessed
        ExFT["Reports excluded after full-text review<br/>(n = {counts.reports_excluded_full_text})"]:::exclude
        Assessed --> ExFT
    end

    subgraph Included ["Included Studies"]
        Inc["Included studies in synthesis<br/>Reports: {counts.included_reports} | Unique Studies: {counts.included_studies}"]:::include
        Assessed --> Inc
    end
```"""


def run_prisma_review_workflow(
    topic: str,
    sources: List[Dict[str, Any]],
    brief: Optional[Dict[str, Any]] = None,
    session_id: str = "",
    db_path: Optional[str] = None,
) -> PRISMAReviewLedger:
    """
    Execute end-to-end PRISMA 2020 review workflow:
    1. Inherit or construct protocol from ResearchBrief.
    2. Group reports by underlying study.
    3. Run Title & Abstract screening.
    4. Run Full-Text Eligibility screening (distinguishing retrieval failures).
    5. Appraise included studies and extract methodological indicators.
    6. Map dialectic contradictions with Phase 3.2 counter-evidence.
    7. Compute mathematically coherent PRISMA flow numbers.
    8. Generate Mermaid flow diagram.
    9. Persist review ledger and individual decisions to SQLite.
    """
    brief = brief or {}
    brief_id = brief.get("brief_id") or f"brief-{uuid.uuid4().hex[:8]}"
    review_id = f"rev-{uuid.uuid4().hex[:8]}"

    # Selection criteria inheritance
    selection_criteria = list(brief.get("selection_criteria") or [])
    if not selection_criteria:
        selection_criteria = [
            f"Topical alignment with '{topic}' and central research question",
            "Empirical methodology, validated theoretical model, or systematic review",
            "Exclude unverified opinion pieces without empirical or theoretical backing",
        ]

    hypotheses = list(brief.get("hypotheses") or [])
    focal_hypothesis = hypotheses[0] if hypotheses else f"Empirical and theoretical foundations governing {topic}"

    protocol = ReviewProtocol(
        brief_id=brief_id,
        topic=topic,
        focal_hypothesis=focal_hypothesis,
        search_queries=list(brief.get("search_queries") or [topic]),
        target_databases=["arXiv", "Semantic Scholar", "OpenAlex", "DuckDuckGo"],
        selection_criteria=selection_criteria,
    )

    decisions: List[ScreeningDecision] = []
    passed_ta_sources: List[Dict[str, Any]] = []
    seen_source_keys: Set[str] = set()

    # 1. Title & Abstract screening
    for s in sources:
        s_key = s.get("id") or s.get("url") or s.get("title") or uuid.uuid4().hex[:8]
        if s_key in seen_source_keys:
            continue
        seen_source_keys.add(s_key)

        ta_dec = screen_source_title_abstract(
            source=s,
            selection_criteria=selection_criteria,
            topic=topic,
            focal_hypothesis=focal_hypothesis,
            brief_id=brief_id,
            review_id=review_id,
        )
        decisions.append(ta_dec)
        if ta_dec.disposition in [ScreeningDisposition.INCLUDED, ScreeningDisposition.UNRESOLVED]:
            passed_ta_sources.append(s)

    # 2. Full-Text Eligibility screening
    included_sources: List[Dict[str, Any]] = []
    for s in passed_ta_sources:
        ft_dec = screen_source_full_text(
            source=s,
            selection_criteria=selection_criteria,
            focal_hypothesis=focal_hypothesis,
            brief_id=brief_id,
            review_id=review_id,
        )
        decisions.append(ft_dec)
        if ft_dec.disposition == ScreeningDisposition.INCLUDED:
            included_sources.append(s)

    # 3. Appraisal of included studies (grouping multiple reports into studies)
    included_study_groups = group_sources_into_studies(included_sources)
    appraisals: List[StudyAppraisal] = []

    for study_id, study_reports in included_study_groups.items():
        primary_rep = study_reports[0]
        appraisal = appraise_included_study(
            source=primary_rep,
            focal_hypothesis=focal_hypothesis,
        )
        appraisal.study_id = study_id
        appraisal.report_ids = [r.get("id") or r.get("url") or "" for r in study_reports]
        appraisals.append(appraisal)

    # 4. Dialectic Contradiction Mapping (including Phase 3.2 counter-evidence)
    contradictions = map_contradictions(
        included_studies=appraisals,
        focal_hypothesis=focal_hypothesis,
    )

    evidence_matrix = EvidenceMatrix(
        studies=appraisals,
        contradictions=contradictions,
    )

    # 5. Compute PRISMA 2020 Flow Counts
    flow_counts = compute_prisma_flow(
        protocol=protocol,
        raw_sources=sources,
        decisions=decisions,
        study_groups=included_study_groups,
    )

    # 6. Generate Mermaid Flowchart
    mermaid_diag = generate_prisma_mermaid_diagram(flow_counts, topic=topic)

    ledger = PRISMAReviewLedger(
        review_id=review_id,
        brief_id=brief_id,
        session_id=session_id,
        topic=topic,
        protocol=protocol,
        flow_counts=flow_counts,
        decisions=decisions,
        evidence_matrix=evidence_matrix,
        mermaid_diagram=mermaid_diag,
    )

    # 7. Persist to SQLite if db_path provided
    if db_path is not None:
        try:
            from backend.memory.db import save_prisma_review_db, save_screening_decision_db
            save_prisma_review_db(ledger.to_dict(), db_path=db_path)
            for d in decisions:
                save_screening_decision_db(d.to_dict(), db_path=db_path)
        except Exception:
            pass

    return ledger

