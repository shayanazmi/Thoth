# Thoth · Developed by Shayan Azmi
"""
Thoth Research Integrity Gate
Deterministic provenance checks, quantitative-evidence validation,
and fail-closed integrity decision engine.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple


logger = logging.getLogger("ThothIntegrityGate")


def _slugify(text: str, max_len: int = 40) -> str:
    """Same id scheme the source ids were minted with: lowercase, [a-z0-9_-], underscores collapsed."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", text.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_len] if cleaned else "note"


def _clean_source_id(source_id: str) -> Tuple[str, Optional[str]]:
    """Separates base source ID from passage or page locators (e.g. 'src-paper:p1-1' -> ('src-paper', 'p1-1'))."""
    if not source_id:
        return "", None
    sid = source_id.strip("[] ")
    if ":" in sid:
        parts = sid.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    if ", p." in sid.lower() or ", page" in sid.lower():
        parts = re.split(r",\s*(?:p\.|page)\s*", sid, flags=re.IGNORECASE)
        return parts[0].strip(), parts[1].strip()
    return sid, None


def _resolve_source_record(source_id: str, cumulative_sources: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Resolve a source ID to its matching record in cumulative_sources."""
    if not source_id or not cumulative_sources:
        return None

    base_sid, _ = _clean_source_id(source_id)
    sid_clean = base_sid.strip("[] ").lower()
    sid_under = sid_clean.replace("-", "_")
    sid_dash = sid_clean.replace("_", "-")

    for s in cumulative_sources:
        s_id = (s.get("id") or "").strip().lower()
        if not s_id:
            s_title = s.get("title") or s.get("url") or ""
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
    # Check whether claim makes a quantitative assertion first
    corr_match = re.search(r"\b(?:r\s*=\s*|correlation\s*(?:of|is|=)?\s*)([-+]?\d*\.?\d+)", claim_text.lower())
    auc_match = re.search(r"\bauc\s*(?:of|is|=|values of)?\s*(\d*\.?\d+)(?:\s*[-–]\s*(\d*\.?\d+))?", claim_text.lower())
    bps_match = re.search(r"(\d+(?:\s*[-–]\s*\d+)?)\s*(?:basis\s*points|bps)", claim_text.lower())
    pct_match = re.search(r"\b(\d+(?:\.\d+)?)\s*%", claim_text)
    mult_match = re.search(r"\b(\d+(?:\.\d+)?)\s*x\s+(?:speedup|throughput|faster|improvement)\b", claim_text.lower())
    sample_match = re.search(r"\b(?:n\s*=\s*|sample\s*size\s*(?:of)?\s*)(\d+[\d,]*)\b", claim_text.lower())

    if not (corr_match or auc_match or bps_match or pct_match or mult_match or sample_match):
        return "NOT_APPLICABLE", None

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
    if bps_match:
        bps_val = bps_match.group(1)
        if "basis point" not in retained_text and "bps" not in retained_text and bps_val not in retained_text:
            return (
                "UNSUPPORTED",
                f"Quantitative basis-point assertion ({bps_val} bps) has no supporting evidence in source."
            )
        return "SUPPORTED", None

    # 4. Percentage checks (e.g. reduced by 75% vs 15%)
    if pct_match:
        claimed_pct = float(pct_match.group(1))
        source_pct_matches = [float(v) for v in re.findall(r"\b(\d+(?:\.\d+)?)\s*%", retained_text)]
        if source_pct_matches:
            if not any(abs(v - claimed_pct) < 1.0 for v in source_pct_matches):
                if any(abs(v - claimed_pct) >= 10.0 for v in source_pct_matches):
                    return (
                        "CONTRADICTED",
                        f"Quantitative percentage mismatch: claim asserts {claimed_pct}%, but source reports {source_pct_matches}%."
                    )
                return (
                    "UNSUPPORTED",
                    f"Quantitative percentage {claimed_pct}% not found in source (reported: {source_pct_matches}%)."
                )
            return "SUPPORTED", None
        else:
            return (
                "UNSUPPORTED",
                f"Quantitative percentage claim ({claimed_pct}%) lacks supporting evidence in source."
            )

    # 5. Multiplier speedup checks (e.g. 10x vs 1.5x)
    if mult_match:
        claimed_mult = float(mult_match.group(1))
        source_mult_matches = [float(v) for v in re.findall(r"\b(\d+(?:\.\d+)?)\s*x\b", retained_text)]
        if source_mult_matches:
            if not any(abs(v - claimed_mult) < 0.2 for v in source_mult_matches):
                return (
                    "CONTRADICTED",
                    f"Multiplier mismatch: claim asserts {claimed_mult}x speedup, but source reports {source_mult_matches}x."
                )
            return "SUPPORTED", None
        else:
            return (
                "UNSUPPORTED",
                f"Multiplier assertion ({claimed_mult}x) lacks supporting evidence in source."
            )

    # 6. Sample size checks (e.g. N = 10,000 vs N = 100)
    if sample_match:
        claimed_n = int(sample_match.group(1).replace(",", ""))
        source_n_matches = [int(v.replace(",", "")) for v in re.findall(r"\b(?:n\s*=\s*|sample\s*size\s*(?:of)?\s*)(\d+[\d,]*)\b", retained_text)]
        if source_n_matches:
            if not any(v == claimed_n for v in source_n_matches):
                return (
                    "CONTRADICTED",
                    f"Sample size mismatch: claim asserts N = {claimed_n}, but source reports N = {source_n_matches}."
                )
            return "SUPPORTED", None
        else:
            return (
                "UNSUPPORTED",
                f"Sample size assertion (N = {claimed_n}) lacks supporting evidence in source."
            )

    return "NOT_APPLICABLE", None


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

    # 1. Extract all cited source IDs (including those with locators)
    cited_ids = []
    seen_ids = set()

    for m in re.findall(r"\[\[(src-[a-zA-Z0-9_\-]+)(?:[:,\s][^\]]+)?\]\]", report_text):
        if m not in seen_ids:
            cited_ids.append(m)
            seen_ids.add(m)

    for m in re.findall(r"\[(src-[a-zA-Z0-9_\-]+)(?:[:,\s][^\]]+)?\]", report_text):
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

            access_tag = ""
            quality = s.get("extraction_quality")
            if quality == "full":
                pages = f" ({s.get('num_pages')} pages)" if s.get("num_pages") else ""
                access_tag = f" — [Full Text{pages}]"
            elif quality == "partial":
                pages = f"{s.get('num_pages')} pages" if s.get("num_pages") else "excerpt"
                access_tag = f" — [Partial Extraction - {pages}]"
            elif quality == "snippet_only":
                access_tag = " — [Search Snippet / Abstract Only]"
            elif quality == "inaccessible":
                access_tag = " — [Inaccessible / Retrieval Failed]"

            ref_lines.append(f"{idx}. **{title}**{date}. {authors}.{id_str}{url_str}{access_tag}")
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
