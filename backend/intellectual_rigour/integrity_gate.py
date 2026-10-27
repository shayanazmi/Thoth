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



def _slugify(text: str, max_len: int = 40) -> str:
    """Same id scheme the source ids were minted with: lowercase, [a-z0-9_-], underscores collapsed."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", text.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_len] if cleaned else "note"

def normalize_text(text: str) -> str:
    """Standardize punctuation, dashes, quotes, and whitespace for deterministic quote searching."""
    if not text:
        return ""
    t = str(text)
    t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = t.replace("—", "-").replace("–", "-")
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


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


def _stem(w: str) -> str:
    """Deterministic light stemmer for English inflections."""
    w = w.lower()
    for sfx in ("ations", "ation", "ated", "tions", "tion", "ing", "ies", "ed", "es", "s"):
        if w.endswith(sfx) and len(w) - len(sfx) >= 3:
            if sfx == "ies":
                return w[:-3] + "y"
            w = w[:-len(sfx)]
            break
    if len(w) >= 4 and w.endswith("e") and not w.endswith("ee"):
        w = w[:-1]
    return w


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


def verify_passage_locator(
    source_id: str,
    cumulative_sources: List[Dict[str, Any]],
    claim_text: Optional[str] = None,
    quoted_evidence: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    If source_id specifies a passage or page locator (e.g. 'src-paper:p1-2'),
    verifies that:
      1. The locator exists in the retained source passages.
      2. If quoted_evidence is provided, the quote occurs in that specific cited passage.
      3. If claim_text is provided, the cited passage contains substantive evidence for the claim.
    """
    base_sid, locator = _clean_source_id(source_id)
    if not locator:
        return True, None
    record = _resolve_source_record(base_sid, cumulative_sources)
    if not record:
        return False, f"Source '{base_sid}' not found."
    passages = record.get("passages") or []
    if not passages:
        return False, f"Passage or page locator '{locator}' cited, but source '{base_sid}' has no indexed passages or page structure."

    p_ids = [p.get("passage_id") for p in passages if isinstance(p, dict) and p.get("passage_id")]
    page_match = re.match(r"(?:p|page)?\s*(\d+)", locator, flags=re.IGNORECASE)
    pg_num = int(page_match.group(1)) if page_match else None

    matching_passages = []
    if locator in p_ids:
        matching_passages = [p for p in passages if isinstance(p, dict) and p.get("passage_id") == locator]
    elif pg_num is not None:
        matching_passages = [p for p in passages if isinstance(p, dict) and p.get("page_num") == pg_num]

    if not matching_passages:
        return False, f"Passage or page locator '{locator}' not found in source '{base_sid}' (available: {p_ids[:5]})."

    # Verify passage-level content match if quoted evidence or claim text provided
    passage_combined_text = " ".join(p.get("text", "") for p in matching_passages)
    norm_passage = normalize_text(passage_combined_text)

    if quoted_evidence and quoted_evidence.strip():
        norm_q = normalize_text(quoted_evidence)
        if norm_q not in norm_passage:
            doc_text = normalize_text(record.get("extracted_text") or "")
            if norm_q in doc_text:
                return False, f"Passage mismatch for '{source_id}': quoted evidence appears elsewhere in '{base_sid}', but is absent from cited passage/page '{locator}'."
            else:
                return False, f"Quoted evidence not found in cited passage '{locator}'."

    if claim_text and not quoted_evidence:
        stop_words = {
            "the", "and", "for", "that", "this", "with", "from", "were", "been",
            "have", "more", "such", "than", "their", "will", "would", "about",
            "these", "those", "also", "into", "some", "only", "other", "there"
        }
        c_words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", normalize_text(claim_text)) if w not in stop_words]
        c_stems = {_stem(w) for w in c_words}
        p_words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", norm_passage) if w not in stop_words]
        p_stems = {_stem(w) for w in p_words}
        overlap = c_stems.intersection(p_stems)
        if len(c_stems) >= 3 and len(overlap) < 1:
            return False, f"Passage mismatch for '{source_id}': cited passage '{locator}' does not contain relevant content for the claim."

    return True, None


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


def evaluate_claim_support(
    claim_text: str,
    source_record: Optional[Dict[str, Any]],
    quoted_evidence: Optional[str] = None
) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Distinguish whether a claim is:
      - 'SUPPORTED': Claim is directly or qualifiedly corroborated by source text or passage.
      - 'CONTRADICTED': Claim is refuted, negated, or directly contradicted by the source
        despite lexical overlap.
      - 'INSUFFICIENT': Evidence is missing key predicates/metrics, remains inconclusive,
        or mentions general topic without empirical support.
      - 'UNVERIFIABLE': Source record is missing, unscraped, extraction failed, or contains no text.

    Returns:
      (support_status, explanation, metadata)
    """
    if not source_record:
        return (
            "UNVERIFIABLE",
            "Source record is unavailable or unresolved in the research state.",
            {"reason_code": "source_missing"}
        )

    scrape_status = source_record.get("scrape_status")
    quality = source_record.get("extraction_quality") or ""
    has_text = bool((source_record.get("extracted_text") or "").strip() or (source_record.get("passages")))
    has_snippet = bool((source_record.get("abstract") or source_record.get("snippet") or "").strip())

    if quality == "inaccessible" or (scrape_status in ("failed", "empty", "unscraped") and not has_snippet and not has_text):
        err = source_record.get("scrape_error") or "Source extraction produced empty or failed output."
        return (
            "UNVERIFIABLE",
            f"Source content is inaccessible (status: '{scrape_status}'): {err}",
            {"reason_code": "extraction_failed", "scrape_status": scrape_status}
        )

    passages = source_record.get("passages") or []
    extracted_text = (source_record.get("extracted_text") or "").strip()
    abstract = (source_record.get("abstract") or "").strip()
    snippet = (source_record.get("snippet") or "").strip()

    if not passages and not extracted_text and not abstract and not snippet:
        return (
            "UNVERIFIABLE",
            "Source text is unavailable or extraction produced empty content.",
            {"reason_code": "empty_content"}
        )

    # 1. Quantitative check
    sid = source_record.get("id") or "src-source"
    q_status, q_reason = verify_quantitative_claim(
        claim_text=claim_text,
        source_id=sid,
        cumulative_sources=[source_record],
        quoted_passage=quoted_evidence
    )
    if q_status == "CONTRADICTED":
        return (
            "CONTRADICTED",
            q_reason or "Contradictory quantitative evidence detected in source text.",
            {"type": "quantitative_contradiction"}
        )

    # Assemble corpus with title included for complete contextual entity grounding
    title = (source_record.get("title") or "").strip()
    if title and not title.endswith((".", "!", "?")):
        title = title + "."

    passage_texts = [p.get("text", "") for p in passages if isinstance(p, dict) and p.get("text")]
    corpus_parts = []
    if title:
        corpus_parts.append(title)
    if abstract:
        corpus_parts.append(abstract)
    if passage_texts:
        corpus_parts.extend(passage_texts)
    elif extracted_text:
        corpus_parts.append(extracted_text)
    elif snippet and snippet != abstract:
        corpus_parts.append(snippet)
    combined_source = " \n ".join(corpus_parts)
    norm_source = normalize_text(combined_source)
    clean_claim = re.sub(r"\[\[.*?\]\]", "", claim_text).strip()
    norm_claim = normalize_text(clean_claim or claim_text)

    # Check snippet-only source overclaim
    if quality in ("snippet_only", "abstract_only") or not has_text:
        if re.search(r"\b(full\s+text(?:\s+review)?|detailed\s+(?:protocol|methodology|clinical\s+trial)|comprehensive\s+(?:meta-analysis|histological|cohort|review|full-text)|entire\s+(?:dataset|paper|study|document|cohort))\b", norm_claim) or ("full-text" in norm_claim or "full text" in norm_claim):
            return (
                "INSUFFICIENT",
                "Claim asserts comprehensive full-text review or detailed analysis, but only a search snippet/abstract was available.",
                {"reason_code": "snippet_full_text_overclaim"}
            )

    # 2. Split source into candidate sentences for localized analysis
    raw_sentences = re.split(r"(?<=[.!?])\s+", combined_source)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 8]

    stop_words = {
        "the", "a", "an", "is", "was", "are", "were", "and", "or", "of", "in",
        "on", "at", "to", "for", "with", "by", "that", "this", "it", "as", "from",
        "be", "been", "have", "has", "had", "we", "our", "their", "they", "its"
    }

    raw_claim_words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", norm_claim)
    claim_words = {w for w in raw_claim_words if w not in stop_words}
    if not claim_words:
        claim_words = set(re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", norm_claim))
    claim_stems = {_stem(w) for w in claim_words}

    # 2. Check quoted evidence if provided (Adversarial quote distortion, overgeneralization, and causal leaps)
    if quoted_evidence:
        norm_q = normalize_text(quoted_evidence)
        words_q = re.findall(r"\w+", norm_q)
        words_src = re.findall(r"\w+", norm_source)
        matched_q = (norm_q in norm_source)
        if not matched_q and len(words_q) >= 4:
            seq_len = min(len(words_q), 6)
            target_seq = words_q[:seq_len]
            for i in range(len(words_src) - seq_len + 1):
                if words_src[i:i + seq_len] == target_seq:
                    matched_q = True
                    break
        if not matched_q:
            return (
                "INSUFFICIENT",
                "Quoted evidence was not found within retained source text.",
                {"quoted_evidence": quoted_evidence}
            )

        # Adversarial check 2a: Overgeneralization from preliminary / in-vitro / animal model to clinical human cure
        prelim_pattern = re.compile(r"\b(in[- ]vitro|cell\s+culture|murine|mouse|mice|rats?|preliminary|pilot|hypothetical|exploratory|computational\s+simulation|simulated)\b", re.IGNORECASE)
        clinical_claim_pattern = re.compile(r"\b(cures?|curative|clinical\s+remission|clinical\s+efficacy|effective\s+treatment\s+in\s+humans?|human\s+patients?|demonstrated\s+in\s+patients?)\b", re.IGNORECASE)
        if prelim_pattern.search(norm_q) and clinical_claim_pattern.search(norm_claim):
            has_clinical_trial_proof = bool(re.search(r"\b(phase\s+[123]\s+clinical\s+trial|randomized\s+controlled\s+trial\s+(?:demonstrated|showed|confirmed))\b", norm_source))
            if not has_clinical_trial_proof:
                return (
                    "INSUFFICIENT",
                    f"Unsupported overgeneralization: quoted passage reports in-vitro or preliminary findings ('{quoted_evidence[:90]}...'), but claim asserts clinical efficacy in humans.",
                    {"reason_code": "quote_overgeneralization", "quoted_evidence": quoted_evidence}
                )

        # Adversarial check 2b: Direction / Outcome contradiction between quote and claim
        quote_neg = re.compile(r"\b(no\s+(?:statistically\s+)?significant|failed\s+to|decreased|reduced|inhibited|ineffective|unsuccessful|not\s+supported)\b", re.IGNORECASE)
        claim_pos = re.compile(r"\b(significantly\s+(?:increased|improved|boosted|enhanced)|demonstrated\s+superior\s+efficacy|effective\s+cure|proved\s+therapeutic)\b", re.IGNORECASE)
        if quote_neg.search(norm_q) and claim_pos.search(norm_claim):
            return (
                "CONTRADICTED",
                f"Contradictory claim: claim asserts positive effect/improvement, but quoted evidence explicitly reports negative or null outcome: '{quoted_evidence[:100]}'",
                {"reason_code": "quote_direction_contradiction", "quoted_evidence": quoted_evidence}
            )

        # Adversarial check 2c: Causal leap from observational correlation
        quote_corr = re.compile(r"\b(correlated\s+with|associated\s+with|observational|may\s+suggest|conjectured|hypothesized)\b", re.IGNORECASE)
        claim_causal = re.compile(r"\b(conclusively\s+proves|proved\s+to\s+cause|causes?|definitive\s+causal\s+mechanism|establishes\s+causation)\b", re.IGNORECASE)
        if quote_corr.search(norm_q) and claim_causal.search(norm_claim):
            return (
                "INSUFFICIENT",
                f"Unsupported causal claim: quoted evidence only establishes observational correlation/association ('{quoted_evidence[:90]}...'), not causation.",
                {"reason_code": "causal_leap", "quoted_evidence": quoted_evidence}
            )

        # Adversarial check 2d: Extrapolated / Hallucinated key predicates
        words_claim_substantive = {w for w in claim_stems if len(w) >= 4 and w not in stop_words}
        words_q_stems = {_stem(w) for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", norm_q)}
        missing_from_quote = words_claim_substantive - words_q_stems
        if len(missing_from_quote) >= 3:
            missing_from_source = {w for w in missing_from_quote if w not in norm_source}
            if len(missing_from_source) >= 2:
                return (
                    "INSUFFICIENT",
                    f"Quoted passage does not establish material assertions of the claim (unsupported terms: {list(missing_from_source)[:3]}).",
                    {"reason_code": "unsupported_interpretation", "quoted_evidence": quoted_evidence}
                )

    claim_has_negation = bool(re.search(
        r"\b(no|not|never|neither|nor|failed|fails|failure|unsupported|disproved?|refuted?|contradicts?|ineffective|insignificant)\b",
        norm_claim
    ))

    negation_patterns = [
        r"\bno\s+evidence\s+(?:that|of|found)\b",
        r"\bfailed\s+to\b",
        r"\bfails\s+to\b",
        r"\bfailed\s+(?:replication|attempt|study|trial|experiment)\b",
        r"\bfailure\s+to\b",
        r"\bunsuccessful\b",
        r"\bdoes\s+not\b",
        r"\bdid\s+not\b",
        r"\bdo\s+not\b",
        r"\bcannot\b",
        r"\bcould\s+not\b",
        r"\bis\s+not\b",
        r"\bwas\s+not\b",
        r"\bare\s+not\b",
        r"\bwere\s+not\b",
        r"\brefutes?\b",
        r"\bcontradicts?\b",
        r"\bdisproved?\b",
        r"\bdisproven\b",
        r"\bdisconfirms?\b",
        r"\bineffective\b",
        r"\bno\s+(?:statistically\s+)?significant\s+(?:difference|effect|impact|improvement|relationship|benefit)\b",
        r"\bstatistically\s+insignificant\b",
        r"\bfailed\s+to\s+reach\s+statistical\s+significance\b",
        r"\bnot\s+(?:statistically\s+)?significant\b",
        r"\bnull\s+hypothesis\s+could\s+not\s+be\s+rejected\b",
        r"\bp\s*>\s*0?\.05\b",
        r"\bno\s+(?:discernible|meaningful)\s+(?:effect|difference|impact)\b",
        r"\bcontrary\s+to\s+(?:previous|prior|early)\s+claims\b",
        r"\bunsupported\s+by\s+(?:the\s+data|evidence|results)\b",
        r"\bno\s+causal\s+(?:link|relationship|mechanism|connection)\b",
        r"\bdoes\s+not\s+(?:prove|demonstrate|establish|imply)\s+causation\b",
        r"\bcorrelation\s+does\s+not\s+(?:imply|prove|demonstrate)\s+causation\b",
        r"\bnot\s+causally\s+linked\b",
        r"\bonly\s+(?:a\s+)?correlation\b",
        r"\b(?:clinical\s+translation\s+)?has\s+not\s+been\s+(?:attempted|tested|proven|demonstrated|verified|evaluated)\b",
        r"\b(?:clinical\s+translation\s+)?have\s+not\s+been\s+(?:attempted|tested|proven|demonstrated|verified|evaluated)\b",
        r"\bhas\s+not\s+been\s+attempted\b",
        r"\b(?:completely\s+)?unverified\b",
        r"\bunproven\b",
        r"\bnot\s+(?:yet\s+)?proven\b",
        r"\bnot\s+established\b",
        r"\bcausation\s+is\s+not\s+established\b",
    ]

    out_of_context_patterns = [
        r"\b(?:it\s+is\s+(?:a\s+)?(?:dangerous\s+)?(?:myth|fallacy|misconception)\s+that)\b",
        r"\b(?:contrary\s+to\s+(?:the\s+)?(?:popular\s+belief|myth|speculation|claims?\s+that))\b",
        r"\b(?:falsely\s+(?:claimed|believed|assumed)\s+that)\b",
        r"\b(?:disproved\s+the\s+hypothesis\s+that)\b",
        r"\b(?:hypothetically\s+(?:speaking|assuming)?)\b",
    ]

    narrow_population_patterns = [
        r"\bexclusively\s+in\s+(?:in[- ]vitro|murine|mice|rats?|cell\s+cultures?)\b",
        r"\bonly\s+in\s+(?:in[- ]vitro|murine|mice|rats?|cell\s+cultures?)\b",
        r"\bnot\s+(?:yet\s+)?evaluated\s+in\s+humans?\b",
        r"\bhas\s+not\s+been\s+(?:tested|demonstrated|evaluated)\s+in\s+humans?\b",
        r"\bcannot\s+be\s+generalized\s+to\s+humans?\b",
    ]

    inconclusive_patterns = [
        r"\bremains?\s+inconclusive\b",
        r"\binsufficient\s+evidence\b",
        r"\bremains?\s+(?:unclear|uncertain|unproven|unknown)\b",
        r"\b(?:further|future)\s+(?:empirical\s+)?(?:research|study|investigation|studies)\s+(?:is|are)\s+(?:needed|required)\b",
        r"\b(?:required|needed)\s+to\s+determine\b",
        r"\bcould\s+not\s+be\s+determined\b",
        r"\bpreliminary\s+only\b",
        r"\byet\s+to\s+be\s+(?:determined|established|proven)\b",
    ]

    RELATIONAL_ACTION_TERMS = {
        "increas", "decreas", "reduc", "improv", "enhanc", "worsen",
        "caus", "prevent", "inhibit", "promot", "induc", "stimulat",
        "correlat", "associat", "superior", "inferior", "effect", "efficaci"
    }

    best_match_sentence = ""
    max_overlap = 0
    contradiction_found = None
    inconclusive_found = None

    for sent in sentences:
        norm_s = normalize_text(sent)
        raw_s_words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", norm_s)
        sent_words = {w for w in raw_s_words if w not in stop_words}
        sent_stems = {_stem(w) for w in sent_words}

        # Calculate overlap using both exact words and stems
        shared_stems = claim_stems.intersection(sent_stems)
        shared_words = claim_words.intersection(sent_words)
        overlap_count = max(len(shared_words), len(shared_stems))

        if overlap_count > max_overlap:
            max_overlap = overlap_count
            best_match_sentence = sent

        # Check inconclusive indicators
        if overlap_count >= 2:
            for inc_pat in inconclusive_patterns:
                if re.search(inc_pat, norm_s):
                    inconclusive_found = (sent, inc_pat, list(shared_stems))
                    break

        # Check for contradiction despite lexical overlap
        overlap_ratio = (overlap_count / len(claim_stems)) if claim_stems else 0.0
        if len(claim_stems) >= 3 and (overlap_count >= 3 or overlap_ratio >= 0.4):
            if not claim_has_negation:
                for neg_pat in negation_patterns:
                    if re.search(neg_pat, norm_s):
                        contradiction_found = (sent, neg_pat, list(shared_stems))
                        break
                if not contradiction_found:
                    for ooc_pat in out_of_context_patterns:
                        if re.search(ooc_pat, norm_s):
                            contradiction_found = (sent, ooc_pat, list(shared_stems))
                            break
                if not contradiction_found:
                    if any(hw in norm_claim for hw in ("human", "patients", "clinical")) and any(re.search(np, norm_s) for np in narrow_population_patterns):
                        contradiction_found = (sent, "narrow_population_mismatch", list(shared_stems))
                        break
            else:
                pos_patterns = [
                    r"\b(?:significantly|substantially)\s+(?:improved|increased|reduced|decreased|extended)\b",
                    r"\bdemonstrated\s+(?:clear\s+)?(?:effectiveness|efficacy|success|superiority)\b",
                ]
                for pos_pat in pos_patterns:
                    if re.search(pos_pat, norm_s):
                        contradiction_found = (sent, pos_pat, list(shared_stems))
                        break

        if contradiction_found:
            break

    if contradiction_found:
        conflicting_sent, pat, words = contradiction_found
        return (
            "CONTRADICTED",
            f"Source explicitly contradicts claim despite lexical overlap: '{conflicting_sent.strip()}'",
            {"conflicting_sentence": conflicting_sent.strip(), "shared_words": words, "pattern": pat}
        )

    if inconclusive_found:
        inc_sent, pat, words = inconclusive_found
        return (
            "INSUFFICIENT",
            f"Source evidence on this claim is inconclusive: '{inc_sent.strip()}'",
            {"inconclusive_sentence": inc_sent.strip(), "shared_words": words, "pattern": pat}
        )

    # 3. If quantitative check was UNSUPPORTED, mark INSUFFICIENT
    if q_status == "UNSUPPORTED":
        return (
            "INSUFFICIENT",
            q_reason or "Source text lacks quantitative data to support the specific metric claimed.",
            {"type": "missing_metrics"}
        )

    # 4. Check if key substantive domain terms in the claim are completely absent from the source
    source_words = set(re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", norm_source))
    source_stems = {_stem(w) for w in source_words if w not in stop_words}
    substantive_claim_stems = {s for s in claim_stems if len(s) >= 4 and s not in stop_words}
    missing_from_entire_source = {s for s in substantive_claim_stems if s not in source_stems}
    if len(missing_from_entire_source) >= 2 or (len(substantive_claim_stems) >= 3 and len(missing_from_entire_source) / len(substantive_claim_stems) >= 0.4):
        return (
            "INSUFFICIENT",
            f"Source text provides insufficient substantive evidence: key claim terms {list(missing_from_entire_source)[:3]} do not appear in source.",
            {"reason_code": "missing_claim_predicates", "missing_terms": list(missing_from_entire_source)}
        )

    # 5a. Check sufficiency of lexical and semantic overlap across full source
    overlap_ratio = (max_overlap / len(claim_stems)) if claim_stems else 0.0
    if max_overlap < 2 or overlap_ratio < 0.25:
        return (
            "INSUFFICIENT",
            f"Source text provides insufficient substantive evidence for the claim (overlap: {max_overlap} words, {overlap_ratio:.0%}).",
            {"max_overlap": max_overlap, "overlap_ratio": overlap_ratio}
        )

    # 5b. Relational verification: If claim asserts a directional action/effect, ensure matching sentence establishes it
    claim_relational = {w for w in claim_stems if w in RELATIONAL_ACTION_TERMS}
    if claim_relational and best_match_sentence:
        best_norm = normalize_text(best_match_sentence)
        best_s_words = {w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", best_norm) if w not in stop_words}
        best_s_stems = {_stem(w) for w in best_s_words}
        if not any(w in best_s_stems for w in RELATIONAL_ACTION_TERMS):
            return (
                "INSUFFICIENT",
                f"Source mentions topical entities but does not establish the claimed relationship or effect in: '{best_match_sentence.strip()}'",
                {"missing_relational_action": list(claim_relational), "best_match_sentence": best_match_sentence.strip()}
            )

    # 6. Corroborated
    return (
        "SUPPORTED",
        f"Claim is corroborated by source evidence: '{best_match_sentence.strip()[:180]}'",
        {"passage": best_match_sentence.strip(), "overlap": max_overlap}
    )


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

        # Check claim correspondence with published report text (Claim drift / desynchronization defense)
        norm_report = normalize_text(report_text)
        norm_c = normalize_text(claim_text)
        claim_in_report = (norm_c in norm_report)
        if not claim_in_report and len(norm_report) > 100:
            stop_words = {
                "the", "and", "for", "that", "this", "with", "from", "were", "been",
                "have", "more", "such", "than", "their", "will", "would", "about",
                "these", "those", "also", "into", "some", "only", "other", "there"
            }
            c_words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", norm_c) if w not in stop_words]
            c_stems = {_stem(w) for w in c_words}
            report_sentences = re.split(r"(?<=[.!?])\s+", norm_report)
            for s in report_sentences:
                s_words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", s) if w not in stop_words]
                s_stems = {_stem(w) for w in s_words}
                shared = c_stems.intersection(s_stems)
                if len(c_stems) > 0 and len(shared) >= max(2, int(len(c_stems) * 0.4)):
                    claim_in_report = True
                    break

        if not claim_in_report and len(norm_report) > 100:
            current_status = "UNRESOLVED"
            is_valid = False
            disposition = "unresolved"
            reason = f"Claim text does not correspond to any published sentence in the report (claim drift)."
            provenance_errors.append(f"[{claim_id}] Claim drift: audited claim not present in published report text.")

        # 1. Deterministic check: Source identity
        primary_sid = s_ids[0] if s_ids else ""
        rec = _resolve_source_record(primary_sid, cumulative_sources) if primary_sid else None

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
        if quoted_evidence and primary_sid:
            q_ok, q_err = verify_quote_provenance(quoted_evidence, primary_sid, cumulative_sources)
            if not q_ok:
                provenance_verified = False
                current_status = "UNSUPPORTED"
                is_valid = False
                disposition = "unresolved"
                reason = q_err
                provenance_errors.append(f"Quote provenance failure for '{primary_sid}': {q_err}")

        # 2b. Deterministic check: Passage locator validity
        if primary_sid:
            loc_ok, loc_err = verify_passage_locator(
                primary_sid,
                cumulative_sources,
                claim_text=claim_text,
                quoted_evidence=quoted_evidence
            )
            if not loc_ok:
                provenance_verified = False
                current_status = "UNSUPPORTED"
                is_valid = False
                disposition = "unresolved"
                reason = loc_err or "Passage locator not found in source."
                provenance_errors.append(f"Passage locator error for '{primary_sid}': {loc_err}")

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

        # 5. Semantic claim support & negation/entailment evaluation
        # For theoretical synthesis combining multiple sources, evaluate across all cited records
        all_records = [_resolve_source_record(sid, cumulative_sources) for sid in s_ids]
        valid_records = [r for r in all_records if r]
        if len(valid_records) > 1 and claim_type == "theoretical_synthesis":
            eval_record = {
                "id": "src-synthesis-combined",
                "title": "Combined Synthesis Sources",
                "scrape_status": "success",
                "extracted_text": " \n\n ".join(filter(None, [r.get("extracted_text") or r.get("abstract") or "" for r in valid_records])),
                "passages": [p for r in valid_records for p in (r.get("passages") or [])]
            }
        else:
            eval_record = rec

        sup_status, sup_reason, sup_meta = evaluate_claim_support(
            claim_text=claim_text,
            source_record=eval_record,
            quoted_evidence=quoted_evidence
        )

        # Check for disagreement across cited sources if multiple sources are cited
        if len(valid_records) > 1 and claim_type != "theoretical_synthesis":
            cited_evals = []
            for s_record in valid_records:
                s_st, s_re, _ = evaluate_claim_support(
                    claim_text=claim_text,
                    source_record=s_record,
                    quoted_evidence=quoted_evidence
                )
                cited_evals.append((s_record.get("id"), s_st, s_re))

            has_contra = any(st == "CONTRADICTED" for _, st, _ in cited_evals)
            has_supp = any(st == "SUPPORTED" for _, st, _ in cited_evals)
            if has_contra and has_supp:
                contra_sid = next(sid for sid, st, _ in cited_evals if st == "CONTRADICTED")
                supp_sid = next(sid for sid, st, _ in cited_evals if st == "SUPPORTED")
                sup_status = "CONTRADICTED"
                sup_reason = f"Disagreement across cited sources: '{supp_sid}' supports the claim, but '{contra_sid}' explicitly contradicts it."
            elif has_contra:
                sup_status = "CONTRADICTED"
                sup_reason = next(re for _, st, re in cited_evals if st == "CONTRADICTED")

        # Check for omitted contradictions across other retrieved sources in cumulative_sources (Cherry-picking defense)
        if current_status in ("DIRECTLY_SUPPORTED", "QUALIFIED_SUPPORT", "SUPPORTED") or sup_status in ("SUPPORTED", "QUALIFIED_SUPPORT", "INSUFFICIENT"):
            for other_src in cumulative_sources:
                other_id = other_src.get("id") or ""
                clean_other_id, _ = _clean_source_id(other_id)
                cited_clean_sids = [clean_s for sid in s_ids for clean_s, _ in [_clean_source_id(sid)]]
                if clean_other_id in cited_clean_sids:
                    continue  # Already evaluated

                other_text = (other_src.get("extracted_text") or other_src.get("abstract") or other_src.get("snippet") or "")
                if not other_text.strip():
                    continue

                other_status, other_reason, _ = evaluate_claim_support(
                    claim_text=claim_text,
                    source_record=other_src,
                    quoted_evidence=None
                )
                if other_status == "CONTRADICTED":
                    sup_status = "CONTRADICTED"
                    sup_reason = f"Omitted contradictory evidence in retrieved source '{clean_other_id}': {other_reason}"
                    break

        if sup_status == "CONTRADICTED":
            current_status = "CONTRADICTED"
            is_valid = False
            disposition = "remove"
            reason = sup_reason
            failure_explanations.append(f"[{claim_id}] Contradiction: {sup_reason}")
        elif sup_status == "UNVERIFIABLE":
            if id_ok:
                current_status = "UNRESOLVED"
                disposition = "unresolved"
            is_valid = False
            if not reason:
                reason = sup_reason
            provenance_errors.append(f"[{claim_id}] Unverifiable: {sup_reason}")
        elif sup_status == "INSUFFICIENT":
            if claim_type == "theoretical_synthesis" and raw_status in ("QUALIFIED_SUPPORT", "DIRECTLY_SUPPORTED") and id_ok:
                current_status = "QUALIFIED_SUPPORT"
                is_valid = True
                disposition = "qualify"
            elif current_status not in ("CONTRADICTED", "UNRESOLVED"):
                current_status = "UNSUPPORTED"
                is_valid = False
                disposition = "qualify"
                reason = sup_reason
                failure_explanations.append(f"[{claim_id}] Insufficient: {sup_reason}")
        elif sup_status == "SUPPORTED":
            if is_valid and not reason:
                if current_status not in ("DIRECTLY_SUPPORTED", "QUALIFIED_SUPPORT"):
                    current_status = "DIRECTLY_SUPPORTED"
                    is_valid = True

        # 6. Theoretical synthesis handling
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
            support_status=sup_status,
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
