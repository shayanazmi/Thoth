"""
Originality assessment (vision §4).

Compares the *substance* of the user's hypothesis against what the primary
and adjacent-field searches actually returned. Verdicts:

  likely_novel | partial_overlap | substantially_covered | insufficiently_assessed

Guardrails (vision §4.2, §11):
  - ``likely_novel`` is impossible unless at least one adjacent-field search ran
    and returned results.
  - Thoth never promises a contribution is unprecedented; every verdict carries
    the limits of the search.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with", "is", "are",
    "was", "were", "be", "by", "as", "that", "this", "it", "its", "from", "at", "than",
    "does", "do", "why", "how", "what", "whether", "despite", "between", "into", "more",
    "less", "higher", "lower", "similar", "rates", "effect", "effects", "evidence",
    "report", "reports", "reported", "study", "studies", "research", "literature", "data",
    "level", "levels", "role", "impact", "factors", "associated", "association", "among",
}

# Framings that push the search into neighbouring disciplines / vocabularies.
_ADJACENT_FRAMES = [
    "{core} mechanism",
    "{core} alternative explanation",
    "{core} systematic review OR meta-analysis",
]


def _terms(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z\-]{2,}", (text or "").lower()) if w not in _STOP}


def generate_adjacent_queries(topic: str, hypothesis: str = "") -> List[str]:
    base = hypothesis or topic
    core_terms = sorted(_terms(base), key=len, reverse=True)[:4]
    core = " ".join(core_terms) or (topic or "")[:80]
    return [f.format(core=core) for f in _ADJACENT_FRAMES]


def _overlap(hyp_terms: set, source: Dict[str, Any]) -> float:
    if not hyp_terms:
        return 0.0
    src = _terms(f"{source.get('title', '')} {source.get('abstract', '')}")
    return len(hyp_terms & src) / len(hyp_terms)


def assess_originality(
    hypothesis: str,
    primary_sources: List[Dict[str, Any]],
    adjacent_sources: List[Dict[str, Any]],
    adjacent_queries_run: List[str],
) -> Dict[str, Any]:
    hyp_terms = _terms(hypothesis)
    pool = list(primary_sources) + list(adjacent_sources)
    scored = sorted(
        ({"title": s.get("title"), "url": s.get("url"), "overlap": round(_overlap(hyp_terms, s), 2)} for s in pool),
        key=lambda x: x["overlap"],
        reverse=True,
    )
    seen, closest = set(), []
    for s in scored:
        key = (s["title"] or "").strip().lower()
        if s["overlap"] > 0 and key and key not in seen:
            seen.add(key)
            closest.append(s)
    closest = closest[:5]
    top = closest[0]["overlap"] if closest else 0.0
    strong = sum(1 for s in scored if s["overlap"] >= 0.6)

    limits = (
        "Based on titles/abstracts returned by the searches listed; database coverage, "
        "terminology and access limit certainty. This is not a guarantee of novelty."
    )

    if len(hyp_terms) < 3 or not pool:
        verdict, why = "insufficiently_assessed", "Too little to compare: the hypothesis is too short or no literature was returned."
    elif not adjacent_sources:
        # Guardrail: without an adjacent-field search we cannot call anything novel.
        verdict = "partial_overlap" if top >= 0.4 else "insufficiently_assessed"
        why = "No adjacent-field results were available, so novelty cannot be assessed beyond the primary search."
    elif strong >= 3:
        verdict, why = "substantially_covered", f"{strong} papers share most of the hypothesis's key terms; the idea appears to be well covered."
    elif top >= 0.4:
        verdict, why = "partial_overlap", "Related work exists that addresses parts of the hypothesis; the remaining contribution must be argued, not assumed."
    else:
        verdict, why = "likely_novel", "Neither the primary nor the adjacent-field searches returned papers closely matching the hypothesis."

    return {
        "verdict": verdict,
        "explanation": why,
        "hypothesis": hypothesis,
        "adjacent_queries": adjacent_queries_run,
        "adjacent_results": len(adjacent_sources),
        "closest_prior_work": closest,
        "limits": limits,
    }
