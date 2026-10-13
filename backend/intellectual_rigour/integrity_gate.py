"""
Thoth Research Integrity Gate
Deterministic provenance checks, quantitative-evidence validation,
and fail-closed integrity decision engine.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Set

from backend.agents import (
    ReportClaim,
    EvidencePassage,
    ReportIntegrityResult,
    VerificationResult,
    FactVerificationReport,
    safe_extract_json,
    strip_chain_of_thought
)

logger = logging.getLogger("ThothIntegrityGate")


def normalize_text(text: str) -> str:
    """Standardize punctuation, dashes, quotes, and whitespace for deterministic quote searching."""
    if not text:
        return ""
    t = str(text)
    t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = t.replace("—", "-").replace("–", "-")
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


def _resolve_source_record(source_id: str, cumulative_sources: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Resolve a source ID to its matching record in cumulative_sources."""
    if not source_id or not cumulative_sources:
        return None

    sid_clean = source_id.strip("[] ").lower()
    sid_under = sid_clean.replace("-", "_")
    sid_dash = sid_clean.replace("_", "-")

    for s in cumulative_sources:
        s_id = (s.get("id") or "").strip().lower()
        if not s_id:
            s_title = s.get("title") or s.get("url") or ""
            from backend.orchestrator import _slugify
            s_id = f"src-{_slugify(s_title, 35)}".lower()

        s_under = s_id.replace("-", "_")
        s_dash = s_id.replace("_", "-")

        if sid_clean == s_id or sid_under == s_under or sid_dash == s_dash:
            return s
        if sid_clean.startswith("src-") and s_id == sid_clean[4:]:
            return s
        if not sid_clean.startswith("src-") and s_id == f"src-{sid_clean}":
            return s

    return None


def verify_source_identity(
    cited_source_ids: List[str],
    cumulative_sources: List[Dict[str, Any]]
) -> Tuple[bool, List[str]]:
    """
    Verify that every referenced source ID resolves to an actual source record
    retained in the research state.
    """
    errors = []
    if not cited_source_ids:
        return True, errors

    for sid in cited_source_ids:
        clean_sid = sid.strip("[] ")
        if not clean_sid:
            continue
        record = _resolve_source_record(clean_sid, cumulative_sources)
        if record is None:
            errors.append(f"Unknown or fabricated source ID: '{clean_sid}'")

    return len(errors) == 0, errors


def verify_quote_provenance(
    quote: str,
    source_id: str,
    cumulative_sources: List[Dict[str, Any]]
) -> Tuple[bool, str]:
    """
    Verify that a claimed evidence quote actually appears within the retained text
    (extracted text, abstract, or snippet) of that exact source.
    Search ONLY within the appropriate source's retained text.
    """
    if not quote or not quote.strip():
        return False, "Empty or missing quoted evidence."

    record = _resolve_source_record(source_id, cumulative_sources)
    if not record:
        return False, f"Source '{source_id}' not found in retained research sources."

    retained_parts = [
        record.get("extracted_text") or "",
        record.get("abstract") or "",
        record.get("snippet") or ""
    ]
    retained_combined = " ".join(retained_parts)

    if not retained_combined.strip():
        status = record.get("scrape_status", "unscraped")
        return False, f"Source '{source_id}' has no substantive retained text (status: {status})."

    norm_quote = normalize_text(quote)
    norm_retained = normalize_text(retained_combined)

    if norm_quote in norm_retained:
        return True, ""

    # Substring search with punctuation-stripped word sequences for minor variations
    words_quote = re.findall(r"\w+", norm_quote)
    words_retained = re.findall(r"\w+", norm_retained)

    if len(words_quote) >= 4:
        seq_len = min(len(words_quote), 8)
        target_seq = words_quote[:seq_len]
        matched = False
        for i in range(len(words_retained) - seq_len + 1):
            if words_retained[i:i + seq_len] == target_seq:
                matched = True
                break
        if matched:
            return True, ""

    return False, f"Quoted evidence could not be located in retained text for source '{source_id}'."


def verify_identifier_consistency(
    claim_text: str,
    source_id: str,
    cumulative_sources: List[Dict[str, Any]]
) -> Tuple[bool, List[str]]:
    """
    When a report or claim attributes a DOI, arXiv ID, or PMID to a source,
    ensure it matches the corresponding source record and does not conflict.
    """
    errors = []
    record = _resolve_source_record(source_id, cumulative_sources)
    if not record:
        return True, errors

    # Check DOI consistency
    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", claim_text)
    if doi_match:
        claimed_doi = doi_match.group(0).rstrip(".,;")
        actual_doi = record.get("doi")
        if actual_doi and actual_doi.strip().lower() != claimed_doi.lower():
            errors.append(
                f"DOI conflict for source '{source_id}': claim cites DOI '{claimed_doi}', "
                f"but retained record contains DOI '{actual_doi}'."
            )

    # Check arXiv consistency
    arxiv_match = re.search(r"(?i)\barxiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", claim_text)
    if arxiv_match:
        claimed_arxiv = arxiv_match.group(1)
        actual_arxiv = record.get("arxiv_id")
        if actual_arxiv and actual_arxiv.strip().lower() != claimed_arxiv.lower():
            errors.append(
                f"arXiv ID conflict for source '{source_id}': claim cites arXiv '{claimed_arxiv}', "
                f"but retained record contains arXiv '{actual_arxiv}'."
            )

    # Check PMID consistency
    pmid_match = re.search(r"(?i)\bpmid:\s*([0-9]+)", claim_text)
    if pmid_match:
        claimed_pmid = pmid_match.group(1)
        actual_pmid = record.get("pmid")
        if actual_pmid and str(actual_pmid).strip() != claimed_pmid:
            errors.append(
                f"PMID conflict for source '{source_id}': claim cites PMID '{claimed_pmid}', "
                f"but retained record contains PMID '{actual_pmid}'."
            )

    return len(errors) == 0, errors


def verify_quantitative_claim(
    claim_text: str,
    source_id: str,
    cumulative_sources: List[Dict[str, Any]],
    quoted_passage: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """
    Conservative quantitative-evidence check.
    Returns (status, reason) where status is one of:
      - 'SUPPORTED'
      - 'CONTRADICTED'
      - 'UNSUPPORTED'
      - 'NOT_APPLICABLE' (no quantitative assertion)
    """
    record = _resolve_source_record(source_id, cumulative_sources)
    if not record:
        return "UNSUPPORTED", f"Source '{source_id}' not found for quantitative claim verification."

    retained_text = " ".join([
        quoted_passage or "",
        record.get("extracted_text") or "",
        record.get("abstract") or "",
        record.get("snippet") or ""
    ]).lower()

    if not retained_text.strip():
        return "UNSUPPORTED", f"Source '{source_id}' has no substantive text to verify quantitative claim."

    # 1. Correlation checks (e.g. r = 0.48 vs r = -0.12)
    corr_match = re.search(r"\b(?:r\s*=\s*|correlation\s*(?:of|is|=)?\s*)([-+]?\d*\.?\d+)", claim_text.lower())
    if corr_match:
        claimed_val = float(corr_match.group(1))

        # Look for correlation in source text
        source_corr_matches = re.findall(r"\b(?:r\s*=\s*|correlation\s*(?:of|is|=)?\s*)([-+]?\d*\.?\d+)", retained_text)
        if source_corr_matches:
            found_vals = [float(v) for v in source_corr_matches]
            # Check sign contradiction
            if any((claimed_val > 0 and v < 0) or (claimed_val < 0 and v > 0) for v in found_vals):
                opp_val = next(v for v in found_vals if (claimed_val > 0 and v < 0) or (claimed_val < 0 and v > 0))
                return (
                    "CONTRADICTED",
                    f"Contradictory correlation direction: claim asserts r = {claimed_val}, "
                    f"but source reports r = {opp_val}."
                )
            if not any(abs(v - claimed_val) < 0.05 for v in found_vals):
                return (
                    "UNSUPPORTED",
                    f"Reported correlation r = {claimed_val} does not match reported values in source: {found_vals}."
                )
            return "SUPPORTED", None
        else:
            # Check if the number appears under a completely different metric (e.g. p = 0.48 or accuracy = 0.48)
            num_str = corr_match.group(1)
            wrong_metric_matches = re.findall(
                rf"\b(p|p-value|std|accuracy|auc|alpha)\s*=\s*{re.escape(num_str)}",
                retained_text
            )
            if wrong_metric_matches:
                metric_name = wrong_metric_matches[0]
                return (
                    "UNSUPPORTED",
                    f"Metric mismatch: claimed value {num_str} appears in source as '{metric_name}', not as correlation."
                )

            # Number does not appear in connection with correlation
            return (
                "UNSUPPORTED",
                f"Quantitative correlation claim (r = {claimed_val}) lacks supporting evidence in source."
            )

    # 2. AUC checks (e.g. AUC of 0.82-0.89 or AUC = 0.85)
    auc_match = re.search(r"\bauc\s*(?:of|is|=|values of)?\s*(\d*\.?\d+)(?:\s*[-–]\s*(\d*\.?\d+))?", claim_text.lower())
    if auc_match:
        claimed_low = auc_match.group(1)
        claimed_high = auc_match.group(2)
        if "auc" not in retained_text and claimed_low not in retained_text:
            return (
                "UNSUPPORTED",
                f"AUC assertion ({claimed_low}" + (f"-{claimed_high}" if claimed_high else "") + ") has no evidence in source."
            )
        return "SUPPORTED", None

    # 3. Basis point / alpha checks (e.g. 3-7 basis points / 3-7 bps)
    bps_match = re.search(r"(\d+(?:\s*[-–]\s*\d+)?)\s*(?:basis\s*points|bps)", claim_text.lower())
    if bps_match:
        bps_val = bps_match.group(1)
        if "basis point" not in retained_text and "bps" not in retained_text and bps_val not in retained_text:
            return (
                "UNSUPPORTED",
                f"Quantitative basis-point assertion ({bps_val} bps) has no supporting evidence in source."
            )
        return "SUPPORTED", None

    return "NOT_APPLICABLE", None


def verify_claim_coverage(
    report_text: str,
    audited_claims: List[Dict[str, Any]]
) -> Tuple[bool, List[str]]:
    """
    Check that material empirical findings and citations in the report
    are accounted for in the audited claims.
    """
    errors = []
    if not report_text or not report_text.strip():
        return True, errors

    # Extract all inline citations [[src-...]] or [src-...] from report
    cited_ids = set(re.findall(r"\[\[(src-[a-zA-Z0-9_\-]+)\]\]", report_text))
    cited_ids.update(re.findall(r"\[(src-[a-zA-Z0-9_\-]+)\]", report_text))

    audited_source_ids = set()
    for c in audited_claims:
        sids = c.get("source_ids") or []
        for s in sids:
            audited_source_ids.add(s.strip("[] "))
        if c.get("supporting_source_id"):
            audited_source_ids.add(c["supporting_source_id"].strip("[] "))

    # Check for cited sources in the report that were completely omitted from claim audit
    missing_sources = cited_ids - audited_source_ids
    if missing_sources:
        for ms in sorted(missing_sources):
            errors.append(f"Report cites source '{ms}', but no claims attributed to it were included in the audit.")

    # Check if report has substantive Key Findings but zero audited claims
    if "## Key Findings" in report_text and len(audited_claims) == 0:
        errors.append("Report contains Key Findings section, but zero claims were audited.")

    return len(errors) == 0, errors


def audit_report_integrity(
    report_text: str,
    cumulative_sources: List[Dict[str, Any]],
    raw_verifier_response: Any
) -> ReportIntegrityResult:
    """
    End-to-end evaluation combining semantic verification with deterministic
    provenance, identifier, and quantitative checks.
    """
    parsed = None
    if isinstance(raw_verifier_response, str):
        cleaned = strip_chain_of_thought(raw_verifier_response)
        parsed = safe_extract_json(cleaned, default=None)
        if parsed is None:
            parsed = safe_extract_json(raw_verifier_response, default=None)
    elif isinstance(raw_verifier_response, dict):
        parsed = raw_verifier_response

    # If verifier output could not be parsed at all, mark INCOMPLETE / FAILED
    if not parsed or not isinstance(parsed, dict) or "results" not in parsed:
        error_msg = f"Verifier output was malformed or failed structured JSON parsing: {str(raw_verifier_response)[:200]}"
        return ReportIntegrityResult(
            status="INCOMPLETE",
            total_claims=0,
            provenance_errors=[error_msg],
            failure_explanations=[error_msg],
            is_verified=False
        )

    raw_results = parsed.get("results", [])
    if not isinstance(raw_results, list) or len(raw_results) == 0:
        # Check if report had substantive text
        if len(report_text.strip()) > 200:
            msg = "Verifier returned zero audited claims for a substantive report."
            return ReportIntegrityResult(
                status="INCOMPLETE",
                total_claims=0,
                failure_explanations=[msg],
                is_verified=False
            )
        return ReportIntegrityResult(status="PASSED", total_claims=0, is_verified=True)

    audited_claims: List[ReportClaim] = []
    directly_supported = 0
    qualified = 0
    unsupported_or_contradicted = 0
    unresolved = 0
    provenance_errors: List[str] = []
    failure_explanations: List[str] = []

    for idx, r in enumerate(raw_results, 1):
        claim_text = r.get("claim", f"Claim #{idx}").strip()
        claim_id = r.get("claim_id") or f"claim-{idx}"
        claim_type = r.get("claim_type") or "factual_finding"

        # Resolve source IDs
        s_ids = r.get("source_ids") or []
        if isinstance(s_ids, str):
            s_ids = [s_ids]
        if r.get("supporting_source_id") and r["supporting_source_id"] not in s_ids:
            s_ids.append(r["supporting_source_id"])

        s_ids = [s.strip("[] ") for s in s_ids if s.strip("[] ")]
        quoted_evidence = r.get("quoted_evidence", "")
        raw_status = (r.get("verification_status") or "").upper()
        is_valid = r.get("is_valid", False)
        reason = r.get("reason_if_failed", "")

        # Default mapping from legacy is_valid
        if not raw_status:
            if is_valid:
                raw_status = "DIRECTLY_SUPPORTED"
            else:
                raw_status = "CONTRADICTED" if ("contradict" in reason.lower() or "false" in reason.lower()) else "UNSUPPORTED"

        current_status = raw_status
        disposition = "retain" if is_valid else "remove"
        provenance_verified = True

        # 1. Deterministic check: Source identity
        if not s_ids and current_status in ("DIRECTLY_SUPPORTED", "QUALIFIED_SUPPORT"):
            current_status = "UNSUPPORTED"
            is_valid = False
            disposition = "remove"
            reason = "Claim has no source attribution."
            provenance_errors.append(f"Claim '{claim_text[:40]}...': missing source attribution.")
        else:
            id_ok, id_errs = verify_source_identity(s_ids, cumulative_sources)
            if not id_ok:
                current_status = "UNSUPPORTED"
                is_valid = False
                disposition = "remove"
                provenance_verified = False
                reason = "; ".join(id_errs)
                provenance_errors.extend(id_errs)

        # 2. Deterministic check: Quote provenance
        primary_sid = s_ids[0] if s_ids else ""
        if quoted_evidence and primary_sid:
            q_ok, q_err = verify_quote_provenance(quoted_evidence, primary_sid, cumulative_sources)
            if not q_ok:
                provenance_verified = False
                current_status = "UNSUPPORTED"
                is_valid = False
                disposition = "unresolved"
                reason = q_err
                provenance_errors.append(f"Quote provenance failure for '{primary_sid}': {q_err}")

        # 3. Deterministic check: Identifier consistency
        if primary_sid:
            ident_ok, ident_errs = verify_identifier_consistency(claim_text, primary_sid, cumulative_sources)
            if not ident_ok:
                current_status = "CONTRADICTED"
                is_valid = False
                disposition = "remove"
                provenance_verified = False
                reason = "; ".join(ident_errs)
                provenance_errors.extend(ident_errs)

        # 4. Deterministic check: Quantitative evidence
        if primary_sid:
            q_status, q_reason = verify_quantitative_claim(claim_text, primary_sid, cumulative_sources, quoted_evidence)
            if q_status == "CONTRADICTED":
                current_status = "CONTRADICTED"
                is_valid = False
                disposition = "remove"
                reason = q_reason or "Contradictory quantitative evidence."
                failure_explanations.append(reason)
            elif q_status == "UNSUPPORTED":
                current_status = "UNSUPPORTED"
                is_valid = False
                disposition = "qualify"
                reason = q_reason or "Unsupported quantitative assertion."
                failure_explanations.append(reason)

        # 5. Theoretical synthesis handling
        if claim_type == "theoretical_synthesis":
            if current_status == "DIRECTLY_SUPPORTED":
                current_status = "QUALIFIED_SUPPORT"
                disposition = "qualify"

        # Update counters
        if current_status == "DIRECTLY_SUPPORTED":
            directly_supported += 1
            disposition = "retain"
        elif current_status == "QUALIFIED_SUPPORT":
            qualified += 1
            disposition = "qualify"
        elif current_status in ("UNSUPPORTED", "CONTRADICTED"):
            unsupported_or_contradicted += 1
            disposition = "remove" if current_status == "CONTRADICTED" else "qualify"
            if reason and reason not in failure_explanations:
                failure_explanations.append(f"[{claim_id}] {reason}")
        else:
            unresolved += 1
            disposition = "unresolved"
            if reason and reason not in failure_explanations:
                failure_explanations.append(f"[{claim_id}] Unresolved: {reason}")

        audited_claims.append(ReportClaim(
            claim_id=claim_id,
            claim=claim_text,
            claim_type=claim_type,
            source_ids=s_ids,
            verification_status=current_status,
            disposition=disposition,
            reason=reason,
            quoted_evidence=quoted_evidence,
            provenance_verified=provenance_verified
        ))

    # 6. Check report claim coverage
    cov_ok, cov_errs = verify_claim_coverage(report_text, [c.model_dump() for c in audited_claims])
    if not cov_ok:
        provenance_errors.extend(cov_errs)
        failure_explanations.extend(cov_errs)

    # Determine overall status
    if unsupported_or_contradicted > 0 or any("conflict" in e.lower() for e in provenance_errors):
        overall_status = "FAILED"
    elif unresolved > 0 or not cov_ok or len(provenance_errors) > 0:
        overall_status = "INCOMPLETE"
    else:
        overall_status = "PASSED"

    is_verified = (overall_status == "PASSED")

    return ReportIntegrityResult(
        status=overall_status,
        total_claims=len(audited_claims),
        directly_supported_count=directly_supported,
        qualified_count=qualified,
        unsupported_or_contradicted_count=unsupported_or_contradicted,
        unresolved_count=unresolved,
        provenance_errors=provenance_errors,
        failure_explanations=failure_explanations,
        claims=audited_claims,
        is_verified=is_verified
    )


def generate_deterministic_bibliography(
    report_text: str,
    cumulative_sources: List[Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Remove Writer's authority to invent the final bibliography.
    Extracts citation markers from the report, resolves to actual source records,
    deduplicates by confirmed persistent identifiers, and deterministically formats
    the ## References section.
    """
    if not report_text:
        return "", [], []

    # 1. Extract all cited source IDs
    cited_ids = []
    seen_ids = set()

    for m in re.findall(r"\[\[(src-[a-zA-Z0-9_\-]+)\]\]", report_text):
        if m not in seen_ids:
            cited_ids.append(m)
            seen_ids.add(m)

    for m in re.findall(r"\[(src-[a-zA-Z0-9_\-]+)\]", report_text):
        if m not in seen_ids:
            cited_ids.append(m)
            seen_ids.add(m)

    # 2. Resolve to matching source records
    resolved_sources = []
    unresolved_ids = []

    for sid in cited_ids:
        rec = _resolve_source_record(sid, cumulative_sources)
        if rec:
            resolved_sources.append(rec)
        else:
            unresolved_ids.append(sid)

    # If no explicit markers found, fall back to sources with matching titles or URLs
    if not resolved_sources and not unresolved_ids:
        for s in cumulative_sources:
            if s.get("url") and s["url"] in report_text:
                resolved_sources.append(s)

    # 3. Deduplicate by confirmed persistent identifier or canonical URL
    deduped_sources = []
    seen_keys = set()

    for s in resolved_sources:
        doi = (s.get("doi") or "").strip().lower()
        arxiv = (s.get("arxiv_id") or "").strip().lower()
        pmid = (s.get("pmid") or "").strip()
        url = (s.get("url") or "").strip().lower()

        key = None
        if doi:
            key = f"doi:{doi}"
        elif arxiv:
            key = f"arxiv:{arxiv}"
        elif pmid:
            key = f"pmid:{pmid}"
        elif url:
            key = f"url:{url}"
        else:
            key = f"id:{s.get('id')}"

        if key not in seen_keys:
            seen_keys.add(key)
            deduped_sources.append(s)

    # 4. Generate deterministic references markdown
    ref_lines = ["\n\n## References\n"]
    if deduped_sources:
        for idx, s in enumerate(deduped_sources, 1):
            title = s.get("title") or "Untitled Document"
            authors = ", ".join(s.get("authors", [])[:4]) if s.get("authors") else "Anonymous / Unlisted"
            date = f" ({s.get('published_date')})" if s.get("published_date") else ""
            url = s.get("url") or ""
            doi = s.get("doi")
            arxiv = s.get("arxiv_id")
            pmid = s.get("pmid")

            id_parts = []
            if doi:
                id_parts.append(f"[DOI:{doi}](https://doi.org/{doi})")
            if arxiv:
                id_parts.append(f"[arXiv:{arxiv}](https://arxiv.org/abs/{arxiv})")
            if pmid:
                id_parts.append(f"PMID:{pmid}")

            id_str = f" — {', '.join(id_parts)}" if id_parts else ""
            url_str = f" — [{url}]({url})" if url else ""

            ref_lines.append(f"{idx}. **{title}**{date}. {authors}.{id_str}{url_str}")
    else:
        ref_lines.append("(No validated sources cited in this report.)")

    new_references_block = "\n".join(ref_lines)

    # 5. Strip any existing Writer-generated ## Sources or ## References
    cleaned_report = re.sub(
        r"(?i)\n*##\s*(?:Sources|References)\b.*$",
        "",
        report_text,
        flags=re.DOTALL
    ).strip()

    final_report = cleaned_report + "\n" + new_references_block

    return final_report, deduped_sources, unresolved_ids
