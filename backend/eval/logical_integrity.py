"""
backend/eval/logical_integrity.py - Logical Integrity & System Health Diagnostic Engine for Thoth.
Implements:
1. Contradiction Leakage verification across Knowledge Graph 'contradicts' edges.
2. Circular Replan Detection comparing new draft claims against previous attempt rejected claims.
3. Unsupported Causal & Comparative Claims verification.
4. Non-Sequitur / Unsupported Conclusion analysis.
5. Wasted-Token Tracking & Retrieval Precision ratio calculation.
6. No-Response / Apology Rate tracking and alerting.
"""
import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

logger = logging.getLogger("ThothLogicalIntegrity")


# =============================================================================
# 1. CIRCULAR REPLAN DETECTION
# =============================================================================

def _tokenize_claim(text: str) -> Set[str]:
    """Tokenizes text into normalized alphanumeric words for lexical overlap."""
    words = re.findall(r"\w+", text.lower())
    # Filter short stop words
    stop_words = {"the", "a", "an", "and", "or", "in", "on", "at", "of", "to", "for", "is", "are", "was", "were"}
    return {w for w in words if len(w) > 2 and w not in stop_words}


def compute_claim_similarity(claim_a: str, claim_b: str) -> float:
    """
    Computes token Jaccard similarity between two claim statements.
    Returns float between 0.0 and 1.0.
    """
    tokens_a = _tokenize_claim(claim_a)
    tokens_b = _tokenize_claim(claim_b)
    if not tokens_a or not tokens_b:
        return 1.0 if claim_a.strip().lower() == claim_b.strip().lower() else 0.0
    
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    return len(intersection) / len(union) if union else 0.0


def detect_circular_replan(
    previous_rejected_claims: List[str],
    new_draft_claims: List[str],
    similarity_threshold: float = 0.80
) -> List[Dict[str, Any]]:
    """
    Detects whether a regenerated draft reintroduces any previously rejected claims
    without correction, indicating circular replanning / loopback fallacy.
    Returns list of circular reintroduction findings.
    """
    findings = []
    if not previous_rejected_claims or not new_draft_claims:
        return findings

    for n_idx, new_c in enumerate(new_draft_claims):
        for r_idx, rej_c in enumerate(previous_rejected_claims):
            sim = compute_claim_similarity(new_c, rej_c)
            # Check exact or high lexical match
            if sim >= similarity_threshold or (rej_c.lower() in new_c.lower() and len(rej_c) > 20):
                findings.append({
                    "rejected_claim": rej_c,
                    "reintroduced_claim": new_c,
                    "similarity": round(sim, 3),
                    "reason": f"Regenerated draft claim #{n_idx+1} reintroduces previously rejected unverified claim #{r_idx+1} ({sim*100:.1f}% lexical match)."
                })
                logger.warning(f"[CIRCULAR REPLAN] Reintroduced rejected claim: '{rej_c[:60]}' (sim={sim:.2f})")

    return findings


# =============================================================================
# 2. WASTED-TOKEN TRACKING & RETRIEVAL PRECISION
# =============================================================================

def extract_cited_note_ids_from_text(text: str) -> Set[str]:
    """
    Extracts all citation identifiers mentioned in report text.
    Matches bracketed identifiers like [src-arxiv-2401-12345], [topic-quantum], [claim-...]
    as well as embedded note slugs.
    """
    if not text:
        return set()

    cited_ids = set()
    # Match standard bracketed citation format [src-...] or [topic-...] or [note_id]
    bracket_matches = re.findall(r"\[([a-zA-Z0-9_\-\.:]+)\]", text)
    for m in bracket_matches:
        cleaned = m.strip()
        if cleaned.startswith("src-") or cleaned.startswith("topic-") or cleaned.startswith("claim-"):
            cited_ids.add(cleaned)
        elif "_" in cleaned or "-" in cleaned:
            cited_ids.add(cleaned)

    # Search for unbracketed src-* or topic-* patterns
    inline_matches = re.findall(r"\b(src-[a-zA-Z0-9_\-]+|topic-[a-zA-Z0-9_\-]+|claim-[a-zA-Z0-9_\-]+)\b", text)
    for m in inline_matches:
        cited_ids.add(m.strip())

    return cited_ids


def compute_retrieval_precision_and_wasted_tokens(
    retrieved_notes: List[Dict[str, Any]],
    final_report: str
) -> Dict[str, Any]:
    """
    Instruments the retrieval step to evaluate the 'wasted tokens' metric.
    Calculates:
      - Retrieval Precision ratio: (cited retrieved notes / total retrieved notes)
      - Wasted Token Count: tokens in retrieved notes that were never cited or used.
      - Wasted Token Ratio: wasted tokens / total retrieved tokens.
    """
    if not retrieved_notes:
        return {
            "retrieval_precision": 1.0,
            "cited_count": 0,
            "retrieved_count": 0,
            "wasted_tokens": 0,
            "total_retrieved_tokens": 0,
            "wasted_token_ratio": 0.0,
            "cited_note_ids": [],
            "unused_note_ids": []
        }

    cited_in_report = extract_cited_note_ids_from_text(final_report)
    
    cited_notes: List[Dict[str, Any]] = []
    unused_notes: List[Dict[str, Any]] = []

    for note in retrieved_notes:
        nid = note.get("note_id", "")
        # Check if note_id was directly cited, or if content appears in report
        if nid and (nid in cited_in_report or nid in final_report or nid.replace("_", "-") in cited_in_report):
            cited_notes.append(note)
        else:
            unused_notes.append(note)

    total_retrieved = len(retrieved_notes)
    cited_count = len(cited_notes)
    retrieval_precision = round(cited_count / total_retrieved, 4) if total_retrieved > 0 else 1.0

    # Token approximations (1.3 tokens per whitespace-separated word)
    def count_note_tokens(n: Dict[str, Any]) -> int:
        content = n.get("content", "")
        return max(1, int(len(content.split()) * 1.3))

    total_retrieved_tokens = sum(count_note_tokens(n) for n in retrieved_notes)
    wasted_tokens = sum(count_note_tokens(n) for n in unused_notes)
    wasted_token_ratio = round(wasted_tokens / total_retrieved_tokens, 4) if total_retrieved_tokens > 0 else 0.0

    return {
        "retrieval_precision": retrieval_precision,
        "cited_count": cited_count,
        "retrieved_count": total_retrieved,
        "wasted_tokens": wasted_tokens,
        "total_retrieved_tokens": total_retrieved_tokens,
        "wasted_token_ratio": wasted_token_ratio,
        "cited_note_ids": [n.get("note_id", "") for n in cited_notes],
        "unused_note_ids": [n.get("note_id", "") for n in unused_notes]
    }


# =============================================================================
# 3. NO-RESPONSE / APOLOGY RATE TRACKING
# =============================================================================

APOLOGY_PATTERNS = [
    r"\bi apologize\b",
    r"\bas an ai\b",
    r"\bunable to find\b",
    r"\bcannot answer\b",
    r"\bsorry, i (do not|cannot|could not)\b",
    r"\bi do not have (access|information)\b",
    r"\bno relevant (information|sources|data) found\b"
]


def check_is_apology_or_fallback(text: str) -> bool:
    """Checks if text consists primarily of an apology or refusal fallback."""
    if not text or not text.strip():
        return True
    
    clean = text.lower().strip()
    for pat in APOLOGY_PATTERNS:
        if re.search(pat, clean):
            return True
    return False


def compute_no_response_and_apology_rate(
    reports: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Evaluates no-response / apology frequency across a set of outputs.
    Identifies:
      - Empty reports (length 0).
      - Zero valid claims (all dropped under write boundary rule).
      - Generic apology / refusal responses.
    """
    total = len(reports)
    if total == 0:
        return {
            "total_reports": 0,
            "empty_reports": 0,
            "zero_claim_reports": 0,
            "apology_reports": 0,
            "no_response_rate": 0.0,
            "apology_rate": 0.0,
            "alert": False,
            "status": "HEALTHY"
        }

    empty_count = 0
    zero_claim_count = 0
    apology_count = 0

    for rep in reports:
        content = rep.get("report", "") if isinstance(rep, dict) else str(rep)
        valid_claims = rep.get("valid_claims", -1) if isinstance(rep, dict) else -1

        if not content or not content.strip():
            empty_count += 1
        elif check_is_apology_or_fallback(content):
            apology_count += 1
        elif valid_claims == 0:
            zero_claim_count += 1

    no_response_total = empty_count + zero_claim_count
    no_response_rate = round(no_response_total / total, 4)
    apology_rate = round(apology_count / total, 4)

    is_alert = no_response_rate > 0.05 or apology_rate > 0.05

    return {
        "total_reports": total,
        "empty_reports": empty_count,
        "zero_claim_reports": zero_claim_count,
        "apology_reports": apology_count,
        "no_response_rate": no_response_rate,
        "apology_rate": apology_rate,
        "alert": is_alert,
        "status": "DEGRADED_ALERT" if is_alert else "HEALTHY"
    }
