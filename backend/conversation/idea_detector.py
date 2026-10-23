"""
Idea detector — Phase 2.

Realises `THOTH.docx` §3.1 ("detect, suggest, then promote"). Thoth notices
when a conversation turn surfaces a *potentially* meaningful research
direction, writes a short rationale, and lets the chat router surface it
as a non-blocking suggestion card. **Nothing is persisted** at this layer.

Vision rubric (§4.1 — what may constitute an original contribution):
  1. A genuinely new explanation or mechanism.
  2. An overlooked relationship or meaningful connection between
     established bodies of work.
  3. A contradiction or inconsistency in existing evidence that calls
     for investigation.
  4. A different perspective, interpretation, or methodology that
     produces a materially different understanding.
  5. A method or analytical approach that reveals something previous
     approaches did not adequately capture.

The detector maps each turn to **at most one** trigger from above. If no
trigger fires, it returns ``None``. If a trigger fires but the message is
too thin to be meaningful, it still returns ``None`` — we are conservative
by design. Vision §3.1 is explicit: the idea network must not become
"a stream of random AI-generated suggestions."

Costs: the detector runs on every substantive turn, so it uses a cheap
rule-based pre-filter and only invokes an LLM when the pre-filter fires.
Fail-open: an LLM error means no suggestion, not a crash.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ThothIdeaDetector")


# -----------------------------------------------------------------------------
# Trigger categories (from vision §4.1)
# -----------------------------------------------------------------------------

TRIGGER_NEW_EXPLANATION = "new_explanation"
TRIGGER_OVERLOOKED_LINK = "overlooked_link"
TRIGGER_CONTRADICTION = "contradiction"
TRIGGER_DIFFERENT_LENS = "different_lens"
TRIGGER_METHOD_REVEAL = "method_reveal"

_TRIGGER_LABELS = {
    TRIGGER_NEW_EXPLANATION: "a possibly new explanation or mechanism",
    TRIGGER_OVERLOOKED_LINK: "a possibly overlooked connection between fields",
    TRIGGER_CONTRADICTION: "an apparent contradiction worth investigating",
    TRIGGER_DIFFERENT_LENS: "a different interpretation of established work",
    TRIGGER_METHOD_REVEAL: "a method or approach that may reveal something new",
}


# Rule-based pre-filter patterns. Each regex is one of several ways a
# curious person might phrase that kind of observation. They are
# intentionally loose — the point is to let a *candidate* through to the
# LLM step, not to decide the verdict here.
_HEURISTIC_PATTERNS: Dict[str, List[re.Pattern]] = {
    TRIGGER_CONTRADICTION: [
        # Either direction: trigger word before or after a quantitative noun.
        re.compile(r"\b(?:but|yet|however|though|despite|although|even though)\b.*\b(?:rate|result|finding|data|evidence|outcome|number|incidence|prevalence)s?\b", re.I),
        re.compile(r"\b(?:rate|result|finding|data|evidence|outcome|number|incidence|prevalence)s?\b.*\b(?:but|yet|however|though|despite|although|even though)\b", re.I),
        # Comparative without quantitative noun: "higher despite similar X".
        re.compile(r"\b(?:higher|lower|more|less|better|worse|stronger|weaker|different|opposite|increased?|decreased?)\b.{0,80}\b(?:despite|although|though|but|however|yet|even though)\b.{0,40}\b(?:similar|same|identical|equal|comparable|matched)\b", re.I),
        re.compile(r"\b(?:why|how).{0,40}\b(?:same|similar|identical|equal)\b.*\b(?:differ|higher|lower|not|un(?:like|equal))\b", re.I),
        re.compile(r"\b(?:contradict|inconsistent|mismatch|anomal|paradox)", re.I),
        re.compile(r"\b(?:unexpected|surpris|weird|odd|strange)\b.{0,40}\b(?:result|finding|outcome|rate|pattern|trend)", re.I),
    ],
    TRIGGER_NEW_EXPLANATION: [
        re.compile(r"\bwhat if\b", re.I),
        re.compile(r"\b(?:could|might|maybe)\b.{0,40}\b(?:because|due to|driven by|caused by|explain(?:ed|s)?)\b", re.I),
        re.compile(r"\bmechanism\b.{0,40}\b(?:underlying|behind|that|explain|produces?)", re.I),
        re.compile(r"\b(?:my hypothesis|i suspect|i think the reason|i wonder (?:why|whether|if))\b", re.I),
    ],
    TRIGGER_OVERLOOKED_LINK: [
        re.compile(r"\b(?:connect|link|bridge|parallel|similar(?:ity)?|analogy)\b.{0,60}\b(?:between|to|with|and)\b", re.I),
        re.compile(r"\b(?:borrow|import|apply)\b.{0,40}\b(?:from|idea|concept|technique)\b", re.I),
        re.compile(r"\b(?:cross(?:-|\s)disciplin|interdisciplin|adjacent field|another field|other field)\b", re.I),
    ],
    TRIGGER_DIFFERENT_LENS: [
        re.compile(r"\b(?:reframe|re[-]?read|reinterpret|new (?:lens|angle|perspective|interpretation))\b", re.I),
        re.compile(r"\bviewed? (?:as|through|under)\b", re.I),
        re.compile(r"\b(?:not just|instead of|rather than)\b.{0,60}\b(?:but|also|also as|means)\b", re.I),
    ],
    TRIGGER_METHOD_REVEAL: [
        re.compile(r"\b(?:method|technique|measurement|instrument|protocol)\b.{0,40}\b(?:miss(?:ed|ing)|overlook|hide|obscur)", re.I),
        re.compile(r"\b(?:different|new|improved|cleaner)\s+(?:method|measurement|approach|design|protocol)\b", re.I),
        re.compile(r"\b(?:if we measured|if we tested|if we captured|if we quantified)\b", re.I),
    ],
}


# Negative filters — if any of these match, the turn is almost certainly
# NOT a research idea. Keep conservative.
_NEGATIVE_PATTERNS = [
    re.compile(r"^(?:hi|hello|hey|thanks|thank you|ok(?:ay)?|cool|nice|got it|understood)\b", re.I),
    re.compile(r"^(?:/|\?help)", re.I),  # slash command, help lookup
    re.compile(r"^(?:what|who|where|when)\s+(?:is|are)\s+\w+\??$", re.I),  # pure definition lookups
]


# -----------------------------------------------------------------------------
# Public dataclass
# -----------------------------------------------------------------------------


@dataclass
class IdeaCandidate:
    """A detected but **unpersisted** research direction.

    Vision §3.1: tentative ideas may remain in the conversational context
    while the user continues exploring. Promotion is what persists them.
    """
    title: str
    hypothesis: str
    rationale: str
    trigger: str
    trigger_label: str
    source_quote: str = ""
    score: float = 0.0  # 0.0–1.0; higher = more confident
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "hypothesis": self.hypothesis,
            "rationale": self.rationale,
            "trigger": self.trigger,
            "trigger_label": self.trigger_label,
            "source_quote": self.source_quote,
            "score": self.score,
            "extra": dict(self.extra),
            "status": "tentative",  # Reminder: this is a suggestion, not a saved row.
        }


# -----------------------------------------------------------------------------
# Pre-filter
# -----------------------------------------------------------------------------


def _passes_negative_filter(text: str) -> bool:
    """Return True when the text does NOT match any clearly-not-an-idea pattern."""
    for pat in _NEGATIVE_PATTERNS:
        if pat.search(text):
            return False
    return True


def _heuristic_trigger(text: str) -> Optional[Tuple[str, re.Match]]:
    """Return the first matching (trigger, match) pair, or None."""
    if not text or len(text.strip()) < 20:
        # A turn under 20 characters is unlikely to be a research direction.
        return None
    if not _passes_negative_filter(text):
        return None
    for trigger, patterns in _HEURISTIC_PATTERNS.items():
        for pat in patterns:
            m = pat.search(text)
            if m:
                return trigger, m
    return None


# -----------------------------------------------------------------------------
# Heuristic-only candidate (used when no LLM is available)
# -----------------------------------------------------------------------------


def _heuristic_candidate(message: str, trigger: str, match: re.Match) -> IdeaCandidate:
    """Build a sober, factual candidate from the regex match alone. Used as
    a fallback when the LLM is unreachable or disabled. The hypothesis is
    quoted verbatim from the user — Thoth does not invent a stronger claim.
    """
    cleaned = message.strip()
    # Pick a short snippet around the match as the source_quote.
    start = max(match.start() - 15, 0)
    end = min(match.end() + 60, len(cleaned))
    snippet = cleaned[start:end].strip()
    # Title: the first ~8 words of the message.
    words = re.split(r"\s+", cleaned)
    title = " ".join(words[:8]).rstrip(",;:")
    if len(words) > 8:
        title += "…"
    # Hypothesis: the message, trimmed, as the user wrote it.
    hypothesis = cleaned if len(cleaned) <= 240 else (cleaned[:237].rstrip() + "…")
    rationale = (
        f"This sounds like {_TRIGGER_LABELS[trigger]}. "
        "I noticed it in what you just said; I haven't persisted anything yet."
    )
    return IdeaCandidate(
        title=title,
        hypothesis=hypothesis,
        rationale=rationale,
        trigger=trigger,
        trigger_label=_TRIGGER_LABELS[trigger],
        source_quote=snippet,
        score=0.55,  # heuristic-only confidence is modest by design
        extra={"source": "heuristic"},
    )


# -----------------------------------------------------------------------------
# LLM-assisted candidate (opt-in; silently skipped on failure)
# -----------------------------------------------------------------------------


_LLM_PROMPT = """You are helping a researcher notice when their own observation
might be worth investigating. Here is the latest thing they said:

---
{message}
---

Recent context (may be empty):
{context}

The pre-filter flagged this as possibly matching the pattern:
  {trigger_label}

Your task: decide whether this really is a research direction worth capturing,
AND if so, write three fields.

Rules you MUST follow:
- Be conservative. If this is just curiosity, chit-chat, or a definition
  lookup, return {{"capture": false}} and nothing else.
- Never invent facts the user didn't say. The hypothesis field must stay
  faithful to the user's own wording; shorten but don't strengthen.
- The rationale must be one sentence, no more, no hedging. Say concretely
  why this looks worth capturing.
- If the user is clearly tentative ("I wonder…", "maybe…"), preserve that
  tentativeness in the hypothesis.

Return a strict JSON object. Nothing else. Examples:
  {{"capture": false}}
  {{"capture": true, "title": "...", "hypothesis": "...", "rationale": "..."}}
"""


def _build_llm_context(chat_history: Optional[List[Dict[str, Any]]], summary: str) -> str:
    pieces: List[str] = []
    if summary:
        pieces.append(f"Summary: {summary.strip()[:400]}")
    if chat_history:
        for turn in chat_history[-3:]:
            u = (turn.get("user") or "").strip()[:200]
            a = (turn.get("assistant") or "").strip()[:200]
            if u:
                pieces.append(f"User: {u}")
            if a:
                pieces.append(f"Thoth: {a}")
    return "\n".join(pieces) or "(no prior context)"


def _llm_refine(
    message: str,
    trigger: str,
    chat_history: Optional[List[Dict[str, Any]]],
    summary: str,
) -> Optional[Dict[str, str]]:
    """Call the fallback-wrapped LLM once. Return a parsed dict or None.
    Never raises — fail-open is the vision principle.
    """
    try:
        from backend.agents import FallbackLLMWrapper, _build_primary_llm, _build_fallback_llm, safe_extract_json  # type: ignore
    except Exception:
        # Older build; stay silent.
        return None

    prompt = _LLM_PROMPT.format(
        message=message.strip()[:800],
        context=_build_llm_context(chat_history, summary),
        trigger_label=_TRIGGER_LABELS.get(trigger, trigger),
    )

    try:
        from backend.agents import direct_chat_chain  # type: ignore
        raw = direct_chat_chain.invoke({"user_query": prompt})
        if hasattr(raw, "content"):
            raw = raw.content
        text = str(raw)
    except Exception as exc:
        logger.info("[idea_detector] LLM refinement unavailable (%s); using heuristic", type(exc).__name__)
        return None

    try:
        parsed = safe_extract_json(text)
    except Exception:
        parsed = None
    if not isinstance(parsed, dict):
        return None

    if not parsed.get("capture"):
        return None  # Model vetoed the suggestion.

    required = ("title", "hypothesis", "rationale")
    if not all(isinstance(parsed.get(k), str) and parsed.get(k).strip() for k in required):
        return None

    return {k: parsed[k].strip() for k in required}


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def detect_promising_direction(
    message: str,
    chat_history: Optional[List[Dict[str, Any]]] = None,
    conversation_summary: str = "",
    *,
    use_llm: bool = True,
) -> Optional[IdeaCandidate]:
    """Classify a single turn against the five vision §4.1 triggers.

    Returns ``None`` when the turn is clearly not a research direction, or
    when the detector is uncertain. Returns an ``IdeaCandidate`` otherwise.

    Parameters
    ----------
    message : str
        The user's latest message, as sent.
    chat_history : list[dict] | None
        Recent prior turns in the shape ``[{user, assistant}]``.
    conversation_summary : str
        Rolling summary of the conversation. Used only as LLM context.
    use_llm : bool
        If False, skip the LLM step entirely and return the heuristic
        candidate directly. Useful for deterministic tests.
    """
    if not isinstance(message, str):
        return None

    hit = _heuristic_trigger(message)
    if not hit:
        return None
    trigger, match = hit

    if not use_llm:
        return _heuristic_candidate(message, trigger, match)

    refined = _llm_refine(message, trigger, chat_history or [], conversation_summary or "")
    if refined is None:
        # LLM unavailable OR LLM declined — fall back to the heuristic
        # candidate (preserving conservatism by returning None when the
        # heuristic is itself weak).
        return _heuristic_candidate(message, trigger, match)

    return IdeaCandidate(
        title=refined["title"][:120],
        hypothesis=refined["hypothesis"][:400],
        rationale=refined["rationale"][:400],
        trigger=trigger,
        trigger_label=_TRIGGER_LABELS[trigger],
        source_quote=match.group(0)[:200],
        score=0.75,  # LLM-assisted confidence
        extra={"source": "llm+heuristic"},
    )


__all__ = [
    "IdeaCandidate",
    "detect_promising_direction",
    "TRIGGER_NEW_EXPLANATION",
    "TRIGGER_OVERLOOKED_LINK",
    "TRIGGER_CONTRADICTION",
    "TRIGGER_DIFFERENT_LENS",
    "TRIGGER_METHOD_REVEAL",
]
