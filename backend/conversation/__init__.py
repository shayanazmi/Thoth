"""
Conversational Research & Escalation Package for Thoth.
Provides intent detection, research mandate synthesis, and
pre-flight clarification.
"""

from backend.conversation.mandate import (
    ResearchMandate,
    synthesize_research_mandate,
)
from backend.conversation.escalation import (
    EscalationState,
    detect_escalation_intent,
)
from backend.conversation.clarification import (
    ClarificationResult,
    evaluate_clarification_need,
)

__all__ = [
    "ResearchMandate",
    "synthesize_research_mandate",
    "EscalationState",
    "detect_escalation_intent",
    "ClarificationResult",
    "evaluate_clarification_need",
]
