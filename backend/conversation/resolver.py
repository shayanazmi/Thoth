import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("thoth.conversation.resolver")

@dataclass
class ResolvedQuery:
    canonical_topic: str
    standalone_query: str
    resolution_type: str  # "DIRECT", "DETERMINISTIC_CONTINUATION", "REFORMULATED", "TOPIC_CORRECTION", "CLARIFICATION_NEEDED"
    is_correction: bool = False
    needs_clarification: bool = False
    clarification_prompt: str = ""
    clarification_options: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_topic": self.canonical_topic,
            "standalone_query": self.standalone_query,
            "resolution_type": self.resolution_type,
            "is_correction": self.is_correction,
            "needs_clarification": self.needs_clarification,
            "clarification_prompt": self.clarification_prompt,
            "clarification_options": self.clarification_options,
            "confidence": self.confidence,
        }

CONTINUATION_PATTERNS = [
    r"^(?:please\s+|can\s+you\s+|let\'?s\s+)?(?:continue|go\s+ahead|go\s+explore|proceed|carry\s+on)(?:\s+with\s+(?:that|this|it))?[\.!\?]*$",
    r"^(?:go\s+deeper|dig\s+deeper|explore\s+deeply)[\.!\?]*$",
    r"^(?:start\s+research|do\s+deep\s+research|run\s+deep\s+research|conduct\s+research)[\.!\?]*$",
    r"^(?:research|explore|investigate)\s+(?:this|that|it|the\s+above)(?:\s+(?:deeply|further|properly))?[\.!\?]*$",
    r"^(?:find|gather)\s+(?:evidence|literature|papers)\s+(?:for|on)\s+(?:this|that|it)[\.!\?]*$",
    r"^(?:yes|yep|sure|ok|okay),?\s*(?:continue|go\s+ahead|explore|proceed)[\.!\?]*$",
]

CORRECTION_PATTERNS = [
    r"(?:you\s+(?:have\s+)?misunderstood\s+me|that\'?s\s+not\s+what\s+i\s+meant|i\s+didn\'?t\s+mean\s+that|wrong\s+topic)",
    r"(?:i\s+mean[t]?|i\s+am\s+referring\s+to|what\s+i\s+meant\s+was|no,\s+i\s+mean)\s+([^\.]+)",
    r"(?:correct\s+(?:the\s+)?topic\s+to|switch\s+(?:the\s+)?topic\s+to)\s+([^\.]+)",
]

REFERENTIAL_AMBIGUITY_PATTERNS = [
    r"\b(?:in\s+this\s+area|in\s+that\s+area|in\s+this\s+field|in\s+this\s+domain)\b",
    r"\b(?:key\s+breakthroughs|breakthroughs\s+in|latest\s+advances\s+in)\b",
    r"\b(?:those\s+findings|these\s+findings|the\s+above|recent\s+papers\s+on\s+this)\b",
    r"\b(?:explore|investigate|study|examine)\s+(?:this|that|it|these|those)\b",
    r"\bwhat\s+does\s+the\s+(?:research|literature)\s+say\s+about\s+(?:this|that|it)\b",
]

def is_continuation_directive(text: str) -> bool:
    if not text:
        return False
    clean = text.strip().lower()
    return any(re.match(p, clean) for p in CONTINUATION_PATTERNS)

def detect_topic_correction(text: str) -> Optional[Tuple[str, str]]:
    if not text:
        return None
    clean = text.strip()
    clean_lower = clean.lower()

    has_correction_marker = bool(re.search(
        r"\b(?:you\s+(?:have\s+)?misunderstood\s+me|that\'?s\s+not\s+what\s+i\s+meant|i\s+didn\'?t\s+mean\s+that|you\s+misunderstood)\b",
        clean_lower
    ))

    extract_match = re.search(
        r"(?:i\s+mean[t]?|i\s+am\s+referring\s+to|what\s+i\s+meant\s+was|no,\s+i\s+mean|correct\s+(?:the\s+)?topic\s+to|topic\s+is\s+actually)\s+([^.]+)",
        clean,
        re.IGNORECASE
    )

    if extract_match:
        extracted = extract_match.group(1).strip()
        cleaned_target = re.sub(
            r"\b(?:continue\s+with\s+that|please\s+continue|look\s+into\s+that|research\s+that|go\s+ahead)\b",
            "",
            extracted,
            flags=re.IGNORECASE
        ).strip().rstrip(".,;:")
        if cleaned_target:
            return (cleaned_target, "Explicit user topic correction")

    if has_correction_marker:
        sentences = re.split(r"[\.!\?]\s*", clean)
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            if re.search(r"\b(?:misunderstood|not\s+what\s+i\s+meant)\b", s_clean, re.I):
                continue
            cleaned_s = re.sub(
                r"\b(?:continue\s+with\s+that|please\s+continue|go\s+ahead)\b",
                "",
                s_clean,
                flags=re.I
            ).strip().rstrip(".,;:")
            if len(cleaned_s.split()) >= 3:
                return (cleaned_s, "Explicit user topic correction")

    return None

def is_ambiguous_referential_query(text: str) -> bool:
    if not text:
        return False
    clean = text.strip().lower()
    return any(re.search(p, clean) for p in REFERENTIAL_AMBIGUITY_PATTERNS)

def _extract_fallback_topic_from_history(
    chat_turns: Optional[List[Dict[str, Any]]],
    summary: str = "",
) -> str:
    if chat_turns:
        for turn in reversed(chat_turns):
            user_text = ""
            if "role" in turn:
                if turn.get("role") == "user":
                    user_text = turn.get("content", "").strip()
            else:
                user_text = (turn.get("user_query") or turn.get("user") or "").strip()

            if user_text and not is_continuation_directive(user_text):
                if len(user_text.split()) >= 3:
                    return user_text

    if summary:
        first_line = summary.strip().split("\n")[0].lstrip("-*• ")
        if len(first_line) > 10:
            return first_line

    return ""

def reformulate_conversational_query(
    user_query: str,
    canonical_topic: str = "",
    chat_turns: Optional[List[Dict[str, Any]]] = None,
    conversation_summary: str = "",
    use_llm: bool = True,
) -> ResolvedQuery:
    query = (user_query or "").strip()
    turns = chat_turns or []

    correction = detect_topic_correction(query)
    if correction:
        corrected_topic, reason = correction
        logger.info(f"[QueryResolver] Detected topic correction: '{corrected_topic}' (reason: {reason})")
        return ResolvedQuery(
            canonical_topic=corrected_topic,
            standalone_query=corrected_topic,
            resolution_type="TOPIC_CORRECTION",
            is_correction=True,
            confidence=0.98,
        )

    active_topic = canonical_topic.strip()
    if not active_topic or active_topic.lower() in ("research topic", "general academic research"):
        active_topic = _extract_fallback_topic_from_history(turns, conversation_summary)

    if is_continuation_directive(query):
        if active_topic:
            logger.info(f"[QueryResolver] Continuation directive '{query}' bound to canonical topic: '{active_topic}'")
            return ResolvedQuery(
                canonical_topic=active_topic,
                standalone_query=active_topic,
                resolution_type="DETERMINISTIC_CONTINUATION",
                is_correction=False,
                confidence=0.95,
            )
        else:
            return ResolvedQuery(
                canonical_topic="",
                standalone_query="",
                resolution_type="CLARIFICATION_NEEDED",
                needs_clarification=True,
                clarification_prompt="What specific research topic or question would you like to explore?",
                clarification_options=[
                    "Explore recent machine learning breakthroughs",
                    "Specify a new research question",
                ],
                confidence=0.2,
            )

    is_ambiguous = is_ambiguous_referential_query(query)
    is_short_referential = len(query.split()) <= 4 and any(
        ref in query.lower() for ref in ["this", "that", "it", "more", "breakthroughs"]
    )

    if is_ambiguous or is_short_referential:
        if not active_topic:
            return ResolvedQuery(
                canonical_topic="",
                standalone_query="",
                resolution_type="CLARIFICATION_NEEDED",
                needs_clarification=True,
                clarification_prompt=(
                    f"You mentioned '{query}', but there is no active research topic set. "
                    "Which research area would you like to investigate?"
                ),
                clarification_options=[
                    "Specify research domain",
                    "Browse suggested academic topics",
                ],
                confidence=0.3,
            )

        reformulated = ""
        if use_llm:
            try:
                from backend.agents import verifier_llm
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.output_parsers import StrOutputParser

                cqr_prompt = ChatPromptTemplate.from_messages([
                    ("system", """You are a precision Conversational Query Reformulator for an academic research intelligence gateway.
Your task is to rewrite ambiguous user follow-ups into a self-contained, standalone academic research search query.
RULES:
1. Preserve the user's intended focus while anchoring it strictly within the canonical topic scope.
2. DO NOT introduce unrelated fields, disciplines, or speculative concepts.
3. Replace deictic terms ('this area', 'those findings', 'it') with the canonical topic entities.
4. Output ONLY the standalone search query string. No preamble, quotes, or markdown."""),
                    ("human", """Canonical Topic: {canonical_topic}
Recent Dialogue Context: {dialogue_context}
User Follow-Up Query: {user_query}
Standalone Search Query:""")
                ])

                recent_context = ""
                if turns:
                    recent_turn_strs = []
                    for t in turns[-2:]:
                        u = t.get("user") or t.get("user_query") or ""
                        a = (t.get("assistant") or t.get("assistant_response") or "")[:120]
                        recent_turn_strs.append(f"User: {u}\nAssistant: {a}")
                    recent_context = "\n".join(recent_turn_strs)

                cqr_chain = cqr_prompt | verifier_llm | StrOutputParser()
                llm_reformulated = cqr_chain.invoke({
                    "canonical_topic": active_topic,
                    "dialogue_context": recent_context or conversation_summary[:200],
                    "user_query": query,
                })
                reformulated = llm_reformulated.strip().strip('"\'')
            except Exception as e:
                logger.warning(f"[QueryResolver] LLM query reformulation failed ({e}); falling back to deterministic synthesis.")
                reformulated = ""

        if not reformulated:
            clean_q = re.sub(
                r"\b(?:in\s+this\s+area|in\s+that\s+area|explore|examine|investigate|study)\b",
                "",
                query,
                flags=re.IGNORECASE
            ).strip().rstrip(".,;:")
            if clean_q:
                reformulated = f"{active_topic}: {clean_q}"
            else:
                reformulated = active_topic

        logger.info(f"[QueryResolver] Reformulated '{query}' -> '{reformulated}' (topic: '{active_topic}')")
        return ResolvedQuery(
            canonical_topic=active_topic,
            standalone_query=reformulated,
            resolution_type="REFORMULATED",
            is_correction=False,
            confidence=0.90,
        )

    if active_topic:
        standalone = f"{active_topic} {query}" if not any(w in query.lower() for w in active_topic.lower().split()[:2]) else query
        return ResolvedQuery(
            canonical_topic=active_topic,
            standalone_query=standalone,
            resolution_type="DIRECT",
            is_correction=False,
            confidence=0.92,
        )

    return ResolvedQuery(
        canonical_topic=query,
        standalone_query=query,
        resolution_type="DIRECT",
        is_correction=False,
        confidence=0.85,
    )
