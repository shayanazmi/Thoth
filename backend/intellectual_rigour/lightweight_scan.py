"""
Lightweight literature scan (vision §5.4).

Early exploration gets a fast, bounded, honestly labelled scan instead of a
formal PRISMA review:

  - at most ``MAX_SCAN_PAPERS`` papers,
  - abstract-level only (no full-text scraping, no snowballing),
  - no screening ledger or appraisal matrix — so nothing here can be mistaken
    for systematic-review counts.

When maturity signals are present, the scan *recommends* a formal review. It
never launches one: that needs a new brief version with
``review_mode="formal"`` and its own explicit approval.
"""
from __future__ import annotations

from typing import Any, Dict, List

MAX_SCAN_PAPERS = 20

# Rough effort figures shown to the user before they approve a formal review.
FORMAL_REVIEW_EFFORT = {
    "papers_considered": "up to ~60 papers (search + citation snowballing)",
    "full_text_attempts": "up to 15 legally accessible full texts",
    "llm_calls": "~10-20",
    "typical_duration": "5-15 minutes",
}


def run_lightweight_scan(sources: List[Dict[str, Any]], brief: Dict[str, Any]) -> Dict[str, Any]:
    """Summarise the first-pass search results without pretending to depth."""
    kept = [s for s in sources if (s.get("title") or "").strip()][:MAX_SCAN_PAPERS]
    papers = []
    for s in kept:
        has_abstract = bool((s.get("abstract") or s.get("snippet") or "").strip())
        papers.append({
            "title": s.get("title"),
            "url": s.get("url"),
            "year": (s.get("published_date") or "")[:4] or None,
            "source_api": s.get("source_api"),
            # Vision §5.2 / §11: never present abstract-level inspection as full text.
            "reading_depth": "abstract_only" if has_abstract else "title_only",
        })

    counter_hits = [s for s in kept if (s.get("relation") or "").startswith("counter")]
    signals = _maturity_signals(brief, counter_hits)

    return {
        "kind": "lightweight_scan",
        "paper_count": len(papers),
        "cap": MAX_SCAN_PAPERS,
        "papers": papers,
        "reading_depth_note": (
            "Lightweight scan: titles and abstracts only. No full texts were read, "
            "no citation snowballing, no screening counts. Treat this as orientation, "
            "not a systematic review."
        ),
        "maturity_signals": signals,
        "recommend_formal_review": bool(signals) and len(papers) > 0,
    }


def _maturity_signals(brief: Dict[str, Any], counter_hits: List[Dict[str, Any]]) -> List[str]:
    signals: List[str] = []
    if brief.get("hypotheses") and brief.get("falsification_criteria"):
        signals.append("The brief carries a testable hypothesis with falsification criteria.")
    if counter_hits:
        signals.append(f"{len(counter_hits)} potentially disconfirming paper(s) surfaced in the scan.")
    if brief.get("idea_id"):
        signals.append("This direction is linked to an idea you promoted to your idea network.")
    return signals


def formal_review_recommendation(scan: Dict[str, Any], brief: Dict[str, Any]) -> Dict[str, Any]:
    """Payload for the ``recommend_formal_review`` card."""
    return {
        "brief_id": brief.get("brief_id"),
        "reasons": scan.get("maturity_signals", []),
        "effort": FORMAL_REVIEW_EFFORT,
        "guidance": (
            "This looks like it could become a serious research question. A formal, "
            "PRISMA-aligned review records every search, screening decision and exclusion. "
            "It takes longer — say 'run a formal review' when you want it; I won't start it on my own."
        ),
    }
