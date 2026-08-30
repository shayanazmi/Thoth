import logging
import time
from typing import Dict, Any, List, Optional
import tiktoken
from backend.agents import conversation_summarizer_chain

logger = logging.getLogger("ThothSessionMemory")

# Default token budget allocation for conversational Q&A turns
DEFAULT_TOKEN_BUDGET: Dict[str, int] = {
    "system": 1000,
    "retrieved_notes": 16000,  # Expanded from 2500 to allow rich academic context
    "summary": 2500,
    "recent_turns": 4000,
    "headroom": 2000,
}

# Dedicated Token Budget for Full Deep Research Report Writer (Nemotron-30B/70B 128k context)
RESEARCH_WRITER_TOKEN_BUDGET: Dict[str, int] = {
    "system": 1500,
    "retrieved_notes": 32000,  # 32k tokens of full scraped papers & primary sources
    "summary": 3000,
    "recent_turns": 4000,
    "headroom": 3000,
}

_tokenizer = None


def get_tokenizer():
    """Lazy loader for tiktoken encoding."""
    global _tokenizer
    if _tokenizer is None:
        try:
            _tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tokenizer = None
    return _tokenizer


def count_tokens(text: str) -> int:
    """Counts tokens using tiktoken cl100k_base with character heuristic fallback."""
    if not text:
        return 0
    enc = get_tokenizer()
    if enc:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, len(text) // 4)


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    """
    Truncates text to fit within max_tokens limit, preserving structural boundaries where practical.
    """
    if not text or max_tokens <= 0:
        return ""

    enc = get_tokenizer()
    if enc:
        try:
            tokens = enc.encode(text)
            if len(tokens) <= max_tokens:
                return text
            logger.warning(f"[TOKEN BUDGET] Truncating text slice from {len(tokens)} to {max_tokens} tokens.")
            print(f"\n[WARNING] [TOKEN BUDGET] Truncating text slice from {len(tokens)} to {max_tokens} tokens.")
            raw_truncated = enc.decode(tokens[:max_tokens])
            min_len = int(len(raw_truncated) * 0.75)
            for delim in ["\n\n--- Source:", "\n\n", ".\n", "\n"]:
                last_idx = raw_truncated.rfind(delim)
                if last_idx >= min_len:
                    return raw_truncated[:last_idx].strip()
            return raw_truncated
        except Exception:
            pass

    char_limit = max_tokens * 4
    if len(text) > char_limit:
        logger.warning(f"[TOKEN BUDGET] Truncating text from {len(text)} to {char_limit} chars.")
        print(f"\n[WARNING] [TOKEN BUDGET] Truncating text from {len(text)} to {char_limit} chars.")
        raw_truncated = text[:char_limit]
        min_len = int(len(raw_truncated) * 0.75)
        for delim in ["\n\n--- Source:", "\n\n", ".\n", "\n"]:
            last_idx = raw_truncated.rfind(delim)
            if last_idx >= min_len:
                return raw_truncated[:last_idx].strip()
        return raw_truncated
    return text


class SessionMemory:
    """
    Manages the short-term side of memory for Thoth conversations:
    - Maintains a rolling summary of key facts established.
    - Maintains a FIFO buffer of recent raw conversation turns.
    - Generates context slices sized strictly according to token budgets.
    """

    def __init__(
        self,
        session_id: str = "default_session",
        system_prompt: str = "",
        initial_summary: str = "",
        initial_turns: Optional[List[Dict[str, Any]]] = None
    ):
        self.session_id = session_id
        self.system_prompt = system_prompt
        self.summary = initial_summary
        self.turns: List[Dict[str, Any]] = list(initial_turns or [])

    def add_turn(
        self,
        user_query: str,
        assistant_response: str,
        turn_metadata: Optional[Dict[str, Any]] = None,
        auto_summarize: bool = False
    ):
        """
        Records a new interaction turn.
        Optionally triggers rolling summarization if turns exceed threshold.
        """
        turn_num = len(self.turns) + 1
        turn_data = {
            "turn": turn_num,
            "user_query": user_query,
            "assistant_response": assistant_response,
            "timestamp": time.time(),
            **(turn_metadata or {})
        }
        self.turns.append(turn_data)

        if auto_summarize and len(self.turns) >= 3:
            self.compress_history()

    def update_summary(self, new_summary: str):
        """Manually updates the rolling summary text."""
        self.summary = new_summary.strip()

    def compress_history(self, summarizer_chain=conversation_summarizer_chain) -> str:
        """
        Runs LLM summarizer over existing summary + recent turns to update rolling summary.
        """
        if not self.turns:
            return self.summary

        recent_turns_formatted = []
        for t in self.turns[-4:]:
            recent_turns_formatted.append(
                f"Turn {t.get('turn')}:\nUser: {t.get('user_query', '')}\nAssistant: {t.get('assistant_response', '')[:500]}"
            )
        turns_text = "\n\n".join(recent_turns_formatted)

        try:
            updated_summary = summarizer_chain.invoke({
                "existing_summary": self.summary or "(No prior summary)",
                "recent_turns": turns_text
            })
            if updated_summary and isinstance(updated_summary, str):
                self.summary = updated_summary.strip()
                logger.info(f"[SESSION MEMORY] Compressed conversation history ({len(self.turns)} turns).")
        except Exception as e:
            logger.warning(f"[SESSION MEMORY] Summarizer chain invoke failed: {e}")

        return self.summary

    def get_context(
        self,
        token_budget: Optional[Dict[str, int]] = None,
        retrieved_notes_text: str = "",
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Assembles budget-bounded slices for:
        - system: system instructions
        - retrieved_notes: relevant vault memory notes
        - summary: rolling conversation summary
        - recent_turns: recent raw conversation turns (dropping oldest if over budget)
        """
        budget = dict(DEFAULT_TOKEN_BUDGET)
        if token_budget:
            budget.update(token_budget)

        sys_text = system_prompt or self.system_prompt
        sys_slice = truncate_text_to_tokens(sys_text, budget["system"])
        notes_slice = truncate_text_to_tokens(retrieved_notes_text, budget["retrieved_notes"])
        summary_slice = truncate_text_to_tokens(self.summary, budget["summary"])

        # Accumulate recent turns from newest to oldest within recent_turns budget
        turns_budget = budget["recent_turns"]
        kept_turns = []
        accumulated_tokens = 0

        for turn in reversed(self.turns):
            turn_str = f"User: {turn.get('user_query', '')}\nAssistant: {turn.get('assistant_response', '')}\n"
            t_tokens = count_tokens(turn_str)
            if accumulated_tokens + t_tokens <= turns_budget:
                kept_turns.insert(0, turn_str)
                accumulated_tokens += t_tokens
            else:
                logger.warning(
                    f"[TOKEN BUDGET] Dropped older raw chat turn #{turn.get('turn')} "
                    f"to fit within {turns_budget} recent_turns token budget."
                )
                print(
                    f"\n[WARNING] [TOKEN BUDGET] Dropped older raw chat turn #{turn.get('turn')} "
                    f"to fit within {turns_budget} recent_turns token budget."
                )

        recent_turns_slice = "\n".join(kept_turns)

        # Formatted combined context
        formatted_blocks = []
        if sys_slice:
            formatted_blocks.append(f"### SYSTEM INSTRUCTIONS\n{sys_slice}")
        if notes_slice:
            formatted_blocks.append(f"### RETRIEVED VAULT NOTES\n{notes_slice}")
        if summary_slice:
            formatted_blocks.append(f"### CONVERSATION SUMMARY\n{summary_slice}")
        if recent_turns_slice:
            formatted_blocks.append(f"### RECENT CONVERSATION TURNS\n{recent_turns_slice}")

        formatted_prompt_context = "\n\n".join(formatted_blocks)
        total_tokens = count_tokens(formatted_prompt_context)

        return {
            "system": sys_slice,
            "retrieved_notes": notes_slice,
            "summary": summary_slice,
            "recent_turns": recent_turns_slice,
            "formatted_prompt_context": formatted_prompt_context,
            "total_tokens": total_tokens,
            "budget_applied": budget
        }
