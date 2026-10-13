from dataclasses import dataclass, field
from typing import List, Optional
from backend.conversation.mandate import ResearchMandate

@dataclass
class ClarificationResult:
    needs_clarification: bool
    clarification_prompt: str = ""
    options: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self):
        return {
            "needs_clarification": self.needs_clarification,
            "clarification_prompt": self.clarification_prompt,
            "options": self.options,
            "reason": self.reason,
        }

BROAD_TOPIC_KEYWORDS = {
    "ai",
    "cancer",
    "battery",
    "batteries",
    "climate change",
    "quantum",
    "crypto",
    "blockchain",
    "robotics",
    "machine learning",
    "deep learning",
    "energy",
    "health",
    "medicine",
}

def evaluate_clarification_need(
    mandate: ResearchMandate,
) -> ClarificationResult:
    if mandate.constraints or mandate.hypotheses:
        return ClarificationResult(
            needs_clarification=False,
            reason="Inherited context and constraints from chat.",
        )

    topic = mandate.topic.strip().lower()
    words = topic.split()

    if "unresolved" in topic:
        return ClarificationResult(
            needs_clarification=True,
            clarification_prompt=(
                "Could you specify the exact topic or problem statement "
                "you would like to research?"
            ),
            options=[
                "Explore recently discussed concepts",
                "Start with a new research question",
            ],
            reason="Unresolved topic reference without conversational context.",
        )

    if len(words) >= 5:
        return ClarificationResult(
            needs_clarification=False,
            reason="Prompt is sufficiently specific.",
        )

    is_broad = (
        len(words) <= 3
        and any(kw in topic for kw in BROAD_TOPIC_KEYWORDS)
    )

    if is_broad:
        options = [
            f"Core Mechanisms, Architectures & Theory in {mandate.topic}",
            f"Recent 2024-2026 Empirical Benchmarks & Breakthroughs in {mandate.topic}",
            f"Real-World Production Deployment & Open Challenges in {mandate.topic}",
        ]
        return ClarificationResult(
            needs_clarification=True,
            clarification_prompt=(
                f"'{mandate.topic}' is a broad research topic. "
                "Which specific scope would you like to prioritize?"
            ),
            options=options,
            reason="Short, broad topic without domain constraints.",
        )

    return ClarificationResult(
        needs_clarification=False,
        reason="Query is well-scoped for search discovery.",
    )
