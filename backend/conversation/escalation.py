"""
Escalation state and intent detector for conversational research.

Implements a 3-state model:
- CHAT: Normal conversational discussion / brainstorming.
- RESEARCH_CANDIDATE: Conversation developing into a concrete hypothesis.
- RESEARCH_READY: Explicit research intent or confirmed candidate.
"""

import enum
import re
from typing import Any, Dict, List, Optional


class EscalationState(str, enum.Enum):
    """3-state conversational escalation enum."""

    CHAT = "CHAT"
    RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
    RESEARCH_READY = "RESEARCH_READY"


# Explicit research trigger patterns (English + Hinglish common commands)
EXPLICIT_RESEARCH_PATTERNS = [
    r"\bresearch\s+(this|that|it|into)\b",
    r"\bresearch\s+this\s+deeply\b",
    r"\bdo\s+a\s+deep\s+dive\b",
    r"\bdeep\s+dive\s+(into|on)\b",
    r"\binvestigate\s+(this|the\s+literature|evidence)\b",
    r"\bfind\s+(papers|studies|evidence|citations)\s+(on|about|for)\b",
    r"\bcheck\s+the\s+literature\b",
    r"\blook\s+into\s+this\s+properly\b",
    r"\bdo\s+a\s+literature\s+review\b",
    r"\bcompare\s+this\s+with\s+the\s+literature\b",
    r"\bverify\s+this\s+with\s+papers\b",
    r"\bispar\s+research\s+(karo|kijiye)\b",
    r"\bpapers\s+dhundho\b",
    r"\bdeep\s+research\s+karo\b",
]

# Signals indicating a discussion is developing into a testable hypothesis
HYPOTHESIS_SIGNALS = [
    r"\bwhat\s+if\b",
    r"\bmy\s+hypothesis\s+is\b",
    r"\bcould\s+it\s+be\s+that\b",
    r"\bperhaps\s+the\s+mechanism\b",
    r"\bi\s+suspect\s+that\b",
    r"\bthe\s+reason\s+might\s+be\b",
    r"\bmaybe\s+the\s+cause\s+is\b",
]

# Signals requesting empirical evidence vs casual explanation
EVIDENCE_SIGNALS = [
    r"\bis\s+there\s+any\s+(?:\w+\s+)*(proof|evidence|data|benchmark|studies)\b",
    r"\bhas\s+anyone\s+(tested|published|proven|measured|benchmarked)\b",
    r"\bwhat\s+do\s+the\s+papers\s+say\b",
    r"\bempirical\s+(results|evidence|data|proof|benchmarks?)\b",
    r"\bdoes\s+the\s+literature\s+support\b",
    r"\b(?:in\s+recent\s+papers|in\s+the\s+literature)\b",
]



def _matches_any_pattern(text: str, patterns: List[str]) -> bool:
    """Helper to test text against a list of compiled regex patterns."""
    text_lower = text.lower().strip()
    for pat in patterns:
        if re.search(pat, text_lower):
            return True
    return False


def detect_escalation_intent(
    user_query: str,
    chat_turns: Optional[List[Dict[str, Any]]] = None,
    conversation_summary: str = "",
) -> Dict[str, Any]:
    """
    Evaluates whether the current conversation turn should remain CHAT,
    escalate to RESEARCH_CANDIDATE, or trigger RESEARCH_READY.

    Rules:
    1. Explicit keywords ('research this deeply') -> RESEARCH_READY.
    2. Hypothesis + Evidence need in a multi-turn context ->
       RESEARCH_CANDIDATE (prompts user with option to start research).
    3. Normal discussion / casual technical Qs -> CHAT.
    """
    query = (user_query or "").strip()
    if not query:
        return {
            "state": EscalationState.CHAT,
            "confidence": 0.0,
            "reason": "Empty query",
            "prompt_user": False,
        }

    # 1. Check Explicit Triggers
    if _matches_any_pattern(query, EXPLICIT_RESEARCH_PATTERNS):
        return {
            "state": EscalationState.RESEARCH_READY,
            "confidence": 0.95,
            "reason": "Explicit research intent detected.",
            "prompt_user": False,
        }

    # 2. Check Implicit Research Signals in Multi-Turn Context
    turns = chat_turns or []
    turn_count = len(turns)
    has_hypothesis = _matches_any_pattern(query, HYPOTHESIS_SIGNALS)
    needs_evidence = _matches_any_pattern(query, EVIDENCE_SIGNALS)

    # If the user combines a hypothesis and asks for literature evidence
    if has_hypothesis and needs_evidence:
        return {
            "state": EscalationState.RESEARCH_READY,
            "confidence": 0.88,
            "reason": "Formulated hypothesis requesting literature evidence.",
            "prompt_user": False,
        }

    # If discussion has accumulated depth (>= 2 turns) and user asks for
    # literature validation
    if turn_count >= 2 and needs_evidence:
        return {
            "state": EscalationState.RESEARCH_CANDIDATE,
            "confidence": 0.75,
            "reason": (
                "Discussion developed into a concrete inquiry requiring "
                "empirical literature evidence."
            ),
            "prompt_user": True,
            "suggestion": (
                "This has developed into a research question. I can "
                "investigate the literature using what we've discussed so far."
            ),
        }

    # 3. Default to Casual Conversation
    return {
        "state": EscalationState.CHAT,
        "confidence": 0.10,
        "reason": "Conversational dialogue / brainstorming.",
        "prompt_user": False,
    }
