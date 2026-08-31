"""
Research Mandate synthesis module for conversational research escalation.

Transforms accumulated dialogue, user constraints, and discussed hypotheses
into a structured ResearchMandate without sending raw chat logs to workers.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional


@dataclass
class ResearchMandate:
    """Structured research mandate synthesized from conversation context."""

    objective: str
    primary_question: str
    sub_questions: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    scope: str = "comprehensive academic & web literature"
    known_facts: List[str] = field(default_factory=list)
    topic: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts mandate to a serializable dictionary."""
        return {
            "objective": self.objective,
            "primary_question": self.primary_question,
            "sub_questions": self.sub_questions,
            "hypotheses": self.hypotheses,
            "constraints": self.constraints,
            "scope": self.scope,
            "known_facts": self.known_facts,
            "topic": self.topic or self.primary_question,
        }


def _extract_constraints_and_hypotheses(
    turns: List[Dict[str, Any]],
    summary: str,
) -> tuple[List[str], List[str], List[str]]:
    """
    Extracts explicit constraints, hypotheses, and established facts
    from conversation turns and summary text without hallucinating.
    """
    constraints: List[str] = []
    hypotheses: List[str] = []
    facts: List[str] = []

    # Regex patterns for user constraints
    constraint_pats = [
        r"\b(?:focus on|limited to|only|restricted to|specifically)\s+([^.,;\n]+)",
        r"\b(?:within|since|between)\s+((?:20\d\d|19\d\d)[^.,;\n]*)",
        r"\b(?:under|above|less than|more than)\s+([^.,;\n]+)",
    ]

    # Regex patterns for hypotheses
    hypothesis_pats = [
        r"\b(?:what if|my hypothesis is|could it be that|perhaps)\s+([^.,?\n]+)",
        r"\b(?:i suspect that|maybe the cause is)\s+([^.,?\n]+)",
    ]

    for turn in turns:
        user_msg = turn.get("user", "")
        bot_msg = turn.get("assistant", "")

        for pat in constraint_pats:
            match = re.search(pat, user_msg, re.IGNORECASE)
            if match:
                extracted = match.group(0).strip()
                if extracted and extracted not in constraints:
                    constraints.append(extracted)

        for pat in hypothesis_pats:
            match = re.search(pat, user_msg, re.IGNORECASE)
            if match:
                extracted = match.group(0).strip()
                if extracted and extracted not in hypotheses:
                    hypotheses.append(extracted)

    if summary:
        for line in summary.split("\n"):
            clean_line = line.strip().lstrip("-*• ")
            if clean_line and len(clean_line) > 15:
                facts.append(clean_line)

    return constraints, hypotheses, facts


REFERENTIAL_PRONOUNS = re.compile(
    r"\b(?:this|that|it|the issue|the problem|this hypothesis|this idea|"
    r"the above|what we discussed|the previous point|that mechanism|"
    r"the proposed explanation|everything discussed|ispar|uspar)\b",
    re.IGNORECASE,
)

RESEARCH_VERBS = re.compile(
    r"\b(?:research|investigate|look into|check|verify|do a deep dive|"
    r"explore|dive into|study|find papers|examine)\b",
    re.IGNORECASE,
)


def is_referential_query(query: str) -> bool:
    """
    Checks if a user query is a meta-command or referential request
    rather than a self-contained, fully-specified standalone topic.
    """
    clean = query.strip()
    words = clean.split()
    if len(words) <= 3 and any(
        ref in clean.lower()
        for ref in [
            "this",
            "that",
            "it",
            "ispar",
            "uspar",
            "above",
            "discussed",
        ]
    ):
        return True

    has_cmd = bool(RESEARCH_VERBS.search(clean))
    has_ref = bool(REFERENTIAL_PRONOUNS.search(clean))
    return has_cmd and has_ref



def _resolve_referential_topic(
    query: str,
    turns: List[Dict[str, Any]],
    summary: str,
    hypotheses: List[str],
    facts: List[str],
) -> str:
    """
    Resolves referential pointers ('this', 'the issue') by prioritizing
    concrete user statements, hypotheses, facts, and rolling summaries.
    """
    # 1. If explicit hypotheses were formulated by the user, prioritize them
    if hypotheses:
        return hypotheses[0]

    # 2. Search recent user turns backwards for substantive problem statements
    for turn in reversed(turns):
        user_text = turn.get("user", "").strip()
        # Skip greetings, short meta-triggers, and pure commands
        if len(user_text.split()) >= 4 and not is_referential_query(user_text):
            return user_text

    # 3. Use established conversation facts or summary
    if facts:
        return facts[0]
    if summary:
        first_line = summary.strip().split("\n")[0].lstrip("-*• ")
        if len(first_line) > 10:
            return first_line

    # 4. If any user turn exists, fall back to its content
    if turns:
        last_turn = turns[-1].get("user", "").strip()
        if last_turn and last_turn != query:
            return last_turn

    # 5. Cold-start referential trigger with zero context
    return f"Unresolved topic reference: {query}"


def synthesize_research_mandate(
    user_query: str,
    chat_turns: Optional[List[Dict[str, Any]]] = None,
    conversation_summary: str = "",
    topic_override: str = "",
) -> ResearchMandate:
    """
    Constructs a structured ResearchMandate by separating the research
    command from the substantive research subject using conversation context.
    """
    query = (user_query or "").strip()
    turns = chat_turns or []

    constraints, hypotheses, facts = _extract_constraints_and_hypotheses(
        turns=turns,
        summary=conversation_summary,
    )

    # Determine substantive research topic
    primary_q = query
    if topic_override:
        topic = topic_override
    elif is_referential_query(query):
        topic = _resolve_referential_topic(
            query=query,
            turns=turns,
            summary=conversation_summary,
            hypotheses=hypotheses,
            facts=facts,
        )
    else:
        topic = query

    # Infer scope from command context
    if re.search(r"\b(?:literature|papers|peer-reviewed|academic)\b", query, re.I):
        scope = "peer-reviewed academic literature"
    else:
        scope = "peer-reviewed literature & technical web sources"

    # Formulate clear objective distinguishing subject from command
    if hypotheses:
        objective = (
            f"Investigate literature evidence for hypothesis: "
            f"'{hypotheses[0]}' in the context of {topic}."
        )
    else:
        objective = f"Conduct rigorous investigation on {topic}."

    # Sub-questions derived from topic & constraints
    sub_qs = [
        f"What are the foundational principles and mechanisms of {topic}?",
        f"What empirical benchmark results exist in recent literature?",
        f"What are the open technical challenges or contradictions?",
    ]

    return ResearchMandate(
        objective=objective,
        primary_question=primary_q,
        sub_questions=sub_qs,
        hypotheses=hypotheses,
        constraints=constraints,
        scope=scope,
        known_facts=facts[:5],
        topic=topic,
    )


