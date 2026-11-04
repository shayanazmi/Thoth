# Thoth · Developed by Shayan Azmi
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv
import os
import json
import re
import warnings
from typing import List, Dict, Any, Optional

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
import logging

logger = logging.getLogger("ThothLLM")

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_nvidia_ai_endpoints")

load_dotenv()

def sanitize_log_message(msg: Any) -> str:
    if msg is None:
        return ""
    text = str(msg)
    text = re.sub(r"(nvapi-[A-Za-z0-9_-]{8,})", r"nvapi-***REDACTED***", text)
    text = re.sub(r"(gsk_[A-Za-z0-9_-]{8,})", r"gsk_***REDACTED***", text)
    text = re.sub(r"(sk-[A-Za-z0-9_-]{8,})", r"sk-***REDACTED***", text)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/-]{8,}", r"\g<1>***REDACTED***", text, flags=re.IGNORECASE)
    text = re.sub(r"((?:api[_-]?key|token|secret)[\"\'\s:=]+)[A-Za-z0-9._~+/-]{8,}", r"\g<1>***REDACTED***", text, flags=re.IGNORECASE)
    return text

class FallbackLLMWrapper(Runnable):
    primary_llm: Any
    fallback_llm: Optional[Any]
    primary_name: str
    fallback_name: str

    def __init__(self, primary_llm: Any, fallback_llm: Optional[Any] = None, primary_name: str = "NVIDIA NIM", fallback_name: str = "Fallback Provider"):
        super().__init__()
        self.primary_llm = primary_llm
        self.fallback_llm = fallback_llm
        self.primary_name = primary_name
        self.fallback_name = fallback_name

    def _adapt_input_for_fallback(self, input_val: Any, max_chars: int = 24000) -> Any:
        if isinstance(input_val, str):
            if len(input_val) > max_chars:
                return input_val[:max_chars] + "\n\n[Context truncated for fallback provider capacity]"
            return input_val
        elif isinstance(input_val, list):
            new_msgs = []
            for msg in input_val:
                if hasattr(msg, "content") and isinstance(msg.content, str) and len(msg.content) > max_chars:
                    truncated_content = msg.content[:max_chars] + "\n\n[Context truncated for fallback capacity]"
                    msg_copy = type(msg)(content=truncated_content)
                    new_msgs.append(msg_copy)
                elif isinstance(msg, dict) and "content" in msg and isinstance(msg["content"], str) and len(msg["content"]) > max_chars:
                    m_copy = dict(msg)
                    m_copy["content"] = m_copy["content"][:max_chars] + "\n\n[Context truncated for fallback capacity]"
                    new_msgs.append(m_copy)
                else:
                    new_msgs.append(msg)
            return new_msgs
        elif hasattr(input_val, "messages") and isinstance(input_val.messages, list):
            new_msgs = []
            for msg in input_val.messages:
                if hasattr(msg, "content") and isinstance(msg.content, str) and len(msg.content) > max_chars:
                    truncated_content = msg.content[:max_chars] + "\n\n[Context truncated for fallback capacity]"
                    msg_copy = type(msg)(content=truncated_content)
                    new_msgs.append(msg_copy)
                else:
                    new_msgs.append(msg)

            try:
                adapted_prompt = type(input_val)(messages=new_msgs)
                return adapted_prompt
            except Exception:
                return new_msgs
        return input_val

    def invoke(self, input: Any, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        try:
            res = self.primary_llm.invoke(input, config=config, **kwargs)
            logger.info(f"[LLM Call] Served by primary provider: {self.primary_name}")
            return res
        except Exception as primary_err:
            if self.fallback_llm is not None:
                msg_warn = f"[LLM Call] Primary provider ({self.primary_name}) failed: {primary_err}. Retrying with fallback ({self.fallback_name})..."
                logger.warning(sanitize_log_message(msg_warn))
                print(f"\n[WARNING] {sanitize_log_message(msg_warn)}")
                try:
                    adapted_input = self._adapt_input_for_fallback(input)
                    res = self.fallback_llm.invoke(adapted_input, config=config, **kwargs)
                    msg_fb = f"[LLM Call] Served by fallback provider: {self.fallback_name}"
                    logger.info(msg_fb)
                    print(f"[INFO] {msg_fb}")
                    return res
                except Exception as fallback_err:
                    msg_err = f"[LLM Call] Fallback provider ({self.fallback_name}) also failed: {fallback_err}"
                    logger.error(sanitize_log_message(msg_err))
                    raise fallback_err from primary_err
            else:
                logger.error(sanitize_log_message(f"[LLM Call] Primary provider ({self.primary_name}) failed: {primary_err}. No fallback provider configured."))
                raise primary_err

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FallbackLLMWrapper":
        primary_bound = self.primary_llm.bind_tools(tools, **kwargs) if hasattr(self.primary_llm, "bind_tools") else self.primary_llm
        fallback_bound = self.fallback_llm.bind_tools(tools, **kwargs) if (self.fallback_llm and hasattr(self.fallback_llm, "bind_tools")) else None
        return FallbackLLMWrapper(
            primary_llm=primary_bound,
            fallback_llm=fallback_bound,
            primary_name=self.primary_name,
            fallback_name=self.fallback_name
        )

class _UnavailableLLM:
    """Stands in for a provider whose client could not be built at import (no network, a TLS-intercepting
    proxy, a bad key). Every call raises, so FallbackLLMWrapper moves to the fallback and the app still boots."""

    def __init__(self, name: str, reason: str):
        self.name, self.reason = name, reason

    def _fail(self, *a: Any, **kw: Any) -> Any:
        raise RuntimeError(f"{self.name} is unavailable: {self.reason}")

    invoke = ainvoke = stream = astream = batch = _fail

    def bind_tools(self, *a: Any, **kw: Any) -> "_UnavailableLLM":
        return self

    def bind(self, *a: Any, **kw: Any) -> "_UnavailableLLM":
        return self


def _nim_client(**kwargs: Any) -> Any:
    """ChatNVIDIA validates the model against NVIDIA's model list over the network as it is constructed.
    That must never stop the server from booting (fail open): degrade to an unavailable stand-in instead."""
    try:
        return ChatNVIDIA(**kwargs)
    except Exception as exc:
        reason = sanitize_log_message(str(exc))[:300]
        logger.warning("[LLM setup] NVIDIA client for %s could not be built; continuing without it: %s", kwargs.get("model"), reason)
        return _UnavailableLLM(f"NVIDIA {kwargs.get('model')}", reason)


_primary_verifier_llm = _nim_client(
    model="nvidia/nemotron-3.5-lightning-30b-a3b",
    api_key=os.getenv("NVIDIA_API_KEY"),
    temperature=0.1,
    max_completion_tokens=2048,
    timeout=30,
    model_kwargs={
        "chat_template_kwargs": {"enable_thinking": False},
    }
)

groq_key = os.getenv("GROQ_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

if groq_key and len(groq_key) > 10 and not groq_key.startswith("dummy"):
    groq_primary_model = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-120b")
    groq_verifier_model = os.getenv("GROQ_VERIFIER_MODEL", "openai/gpt-oss-20b")
    _fallback_llm = ChatOpenAI(model=groq_primary_model, api_key=groq_key, base_url=GROQ_BASE_URL, temperature=0.6, timeout=60)
    _fallback_verifier_llm = ChatOpenAI(model=groq_verifier_model, api_key=groq_key, base_url=GROQ_BASE_URL, temperature=0.1, timeout=30)
    _fb_name = f"Groq ({groq_primary_model})"
    _fb_slot = f"groq:{groq_primary_model}"
elif openai_key and len(openai_key) > 10 and not openai_key.startswith("sk-dummy") and not openai_key.startswith("dummy"):
    _fallback_llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=0.6, timeout=60)
    _fallback_verifier_llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=0.1, timeout=30)
    _fb_name = "OpenAI"
    _fb_slot = "openai:gpt-4o-mini"
else:
    _fallback_llm = None
    _fallback_verifier_llm = None
    _fb_name = "None"
    _fb_slot = ""

verifier_llm = FallbackLLMWrapper(primary_llm=_primary_verifier_llm, fallback_llm=_fallback_verifier_llm, primary_name="NVIDIA-Nemotron-30B", fallback_name=_fb_name)


# Per-role models (docs/FEATURES.md §9, model map). All free NVIDIA NIM.
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
# gpt-oss-20b on NIM stopped answering (no first token in 180s, observed 2026-11-04); Lightning answers in
# seconds with its hidden reasoning off.
NIM_FALLBACK = "nvidia/nemotron-3.5-lightning-30b-a3b"
NO_THINKING = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
ROLE_MODELS: Dict[str, Dict[str, Any]] = {
    "conductor": {"model": NIM_ULTRA, "temperature": 0.5, "max_tokens": 1200, "timeout": 60},
    "thinker": {"model": NIM_ULTRA, "temperature": 0.8, "max_tokens": 900, "timeout": 90},
    # Memory updates, review envelopes, debate distillation. Doc 09 planned Lightning; Ultra at
    # temperature 0 is used instead because Lightning spends small token budgets on hidden reasoning.
    "thinker_support": {"model": NIM_ULTRA, "temperature": 0.0, "max_tokens": 1500, "timeout": 60, "thinking": False},
    # Trial roles (docs/FEATURES.md §5, §6).
    # Extraction roles run with Ultra's hidden reasoning off: on long papers it spent the whole token
    # budget reasoning and the JSON was cut off (observed: 3000 tokens spent, 199 visible characters).
    "librarian": {"model": NIM_ULTRA, "temperature": 0.2, "max_tokens": 1200, "timeout": 60, "thinking": False},
    "reader": {"model": NIM_ULTRA, "temperature": 0.0, "max_tokens": 3000, "timeout": 120, "thinking": False},
    "analyst": {"model": NIM_ULTRA, "temperature": 0.2, "max_tokens": 2000, "timeout": 120, "thinking": False},
    # Study-quality appraisal (vision §5.6): hypothesis-blind, one checklist per paper, item answers with locators.
    "appraiser": {"model": NIM_ULTRA, "temperature": 0.0, "max_tokens": 2500, "timeout": 120, "thinking": False},
    "judge": {"model": NIM_ULTRA, "temperature": 0.2, "max_tokens": 4000, "timeout": 180},
    # Systematic-review screening: extraction-style judgement on records, many calls, so no hidden reasoning.
    "screener": {"model": NIM_ULTRA, "temperature": 0.0, "max_tokens": 6000, "timeout": 120, "thinking": False},
    # Three full design candidates are long JSON; hidden reasoning would eat the budget (see Reader).
    "designer": {"model": NIM_ULTRA, "temperature": 0.4, "max_tokens": 6000, "timeout": 180, "thinking": False},
    # Proposal roles (docs/FEATURES.md §8). Sections and the review are long JSON, so hidden reasoning is off
    # (see Reader); the Verifier judges one sentence against one record.
    "writer": {"model": NIM_ULTRA, "temperature": 0.4, "max_tokens": 3000, "timeout": 150, "thinking": False},
    "verifier": {"model": NIM_ULTRA, "temperature": 0.0, "max_tokens": 700, "timeout": 60, "thinking": False},
    "reviewer": {"model": NIM_ULTRA, "temperature": 0.3, "max_tokens": 4000, "timeout": 180, "thinking": False},
    # Offline evaluations (e.g. the blind-attribution drift test): long reasoning over many replies.
    "evaluator": {"model": NIM_ULTRA, "temperature": 0.0, "max_tokens": 4000, "timeout": 180},
}


# Thinkers speak through models from different labs, so the council does not share one model's blind spots
# (docs/FEATURES.md §3, §9). None is an NVIDIA model, so the Ultra judge never grades its own model's thinkers.
# Chosen from live tests on 2026-11-04; the NIM catalogue changes, so swap a model here if it stops answering.
_NIM_THINKER = {"base_url": NIM_BASE_URL, "key_env": "NVIDIA_API_KEY", "max_tokens": 3000, "timeout": 120,
                "max_retries": 3, "extra": {"reasoning_effort": "low"}}  # "low": 30s -> 5s on MiniMax, same voice
THINKER_MODELS: Dict[str, Dict[str, Any]] = {
    "minimaxai/minimax-m3.1-flash": _NIM_THINKER,
    "meta/muse-glimmer-30b": _NIM_THINKER,
    "stepfun-ai/step-5-preview": _NIM_THINKER,
    # Groq allows 8K tokens a minute per model and a dossier is ~2K, so at most two thinkers per Groq model.
    # Extra retries: the client waits out Groq's retry-after on a 429.
    "openai/gpt-oss-120b": {"base_url": GROQ_BASE_URL, "key_env": "GROQ_API_KEY", "max_tokens": 1500, "timeout": 60,
                            "max_retries": 4, "extra": {}},
    "qwen/qwen3.8-27b": {"base_url": GROQ_BASE_URL, "key_env": "GROQ_API_KEY", "max_tokens": 900, "timeout": 60,
                         "max_retries": 4, "extra": {}},
}
# Thinkers who argue with each other are on different models (Popper/Kuhn, Popper/Hume, and the default
# review trio Popper + Hume + a domain voice).
THINKER_ASSIGNMENT: Dict[str, str] = {
    "popper": "minimaxai/minimax-m3.1-flash", "aristotle": "minimaxai/minimax-m3.1-flash", "simon": "minimaxai/minimax-m3.1-flash",
    "hume": "meta/muse-glimmer-30b", "kuhn": "meta/muse-glimmer-30b", "ibn_al_haytham": "meta/muse-glimmer-30b",
    "nightingale": "openai/gpt-oss-120b", "weber": "openai/gpt-oss-120b",
    "darwin": "qwen/qwen3.8-27b", "ostrom": "qwen/qwen3.8-27b",
}
# From a lab no thinker uses, so a fallback never makes two thinkers share a mind.
THINKER_SPARE = "stepfun-ai/step-5-preview"


# NIM's free tier answers 429 to bursts, on one model and across the account, and the fallback would then
# answer with a different model. Each call holds a slot for the model actually answering, so a council on
# Groq never queues behind a trial on NIM.
import contextlib as _contextlib
import threading as _threading
NIM_SLOTS = _threading.BoundedSemaphore(8)
_model_slots: Dict[str, _threading.BoundedSemaphore] = {}
_model_slots_lock = _threading.Lock()


def model_slot(slot_key: str) -> _threading.BoundedSemaphore:
    with _model_slots_lock:
        return _model_slots.setdefault(slot_key, _threading.BoundedSemaphore(4))


class _Slotted(Runnable):
    """A client that takes its model's slot (and the NIM-wide one) for the length of each call."""

    def __init__(self, llm: Any, slot_key: str, nim: bool):
        super().__init__()
        self.llm, self.slot_key, self.nim = llm, slot_key, nim

    def invoke(self, input: Any, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        with _contextlib.ExitStack() as held:
            if self.nim:
                held.enter_context(NIM_SLOTS)  # always before the model slot, so no two calls wait on each other
            held.enter_context(model_slot(self.slot_key))
            return self.llm.invoke(input, config=config, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_Slotted":
        return _Slotted(self.llm.bind_tools(tools, **kwargs), self.slot_key, self.nim)


def _nim_llm(model: str, key: str, **kwargs: Any) -> _Slotted:
    return _Slotted(ChatOpenAI(model=model, api_key=key, base_url=NIM_BASE_URL, **kwargs), model, nim=True)


def get_role_llm(role: str, allow_fallback: bool = True) -> FallbackLLMWrapper:
    """Build the LLM for one agent role: Ultra → Lightning (both NIM) → the configured
    Groq/OpenAI fallback. Keys are read at call time so tests with empty env fail open.
    allow_fallback=False gives the primary model only (evaluations must not be answered by another model)."""
    cfg = ROLE_MODELS[role]
    key = os.getenv("NVIDIA_API_KEY") or ""
    # Two retries with the client's backoff before falling back: a 429 is usually a passing rate limit,
    # and the fallback model is weaker.
    common = {"temperature": cfg["temperature"], "max_tokens": cfg["max_tokens"], "timeout": cfg["timeout"], "max_retries": 2}
    primary_extra = {} if cfg.get("thinking", True) else NO_THINKING
    if not allow_fallback:
        common["max_retries"] = 6
        return FallbackLLMWrapper(_nim_llm(cfg["model"], key, **common, **primary_extra), None,
                                  primary_name=f"NIM {cfg['model']}")
    tail = _Slotted(_fallback_llm, _fb_slot, nim=False) if _fallback_llm is not None else None
    if key:
        backup = FallbackLLMWrapper(
            _nim_llm(NIM_FALLBACK, key, **common, **NO_THINKING),
            tail, primary_name=f"NIM {NIM_FALLBACK}", fallback_name=_fb_name,
        )
        return FallbackLLMWrapper(
            _nim_llm(cfg["model"], key, **common, **primary_extra),
            backup, primary_name=f"NIM {cfg['model']}", fallback_name=f"NIM {NIM_FALLBACK}",
        )
    if tail is None:
        raise RuntimeError("No LLM provider configured (NVIDIA_API_KEY is empty and no fallback key)")
    return FallbackLLMWrapper(tail, None, primary_name=_fb_name)


def _thinker_client(model: str) -> Optional[_Slotted]:
    cfg = THINKER_MODELS[model]
    key = os.getenv(cfg["key_env"]) or ""
    if not key:
        return None
    nim = cfg["base_url"] == NIM_BASE_URL
    llm = ChatOpenAI(model=model, api_key=key, base_url=cfg["base_url"], temperature=0.8, max_tokens=cfg["max_tokens"],
                     timeout=cfg["timeout"], max_retries=cfg["max_retries"], **cfg["extra"])
    return _Slotted(llm, model if nim else f"groq:{model}", nim)


_thinkers_on_default: set = set()


def get_thinker_llm(thinker_id: str) -> FallbackLLMWrapper:
    """The model one thinker speaks through, with the spare behind it. Without the provider's key the
    thinker speaks through the shared "thinker" role model instead (logged once)."""
    model = THINKER_ASSIGNMENT.get(thinker_id, "")
    own = _thinker_client(model) if model else None
    if own is None:
        if thinker_id not in _thinkers_on_default:
            _thinkers_on_default.add(thinker_id)
            logger.warning("[LLM setup] %s has no reachable model of their own (%s); using the shared thinker model",
                           thinker_id, model or "unassigned")
        return get_role_llm("thinker")
    spare = _thinker_client(THINKER_SPARE) if model != THINKER_SPARE else None
    return FallbackLLMWrapper(own, spare, primary_name=model, fallback_name=f"{THINKER_SPARE} (spare)")


summarizer_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a research conversation compressor. Condense the previous dialogue history into a dense, high-signal bulleted summary of key facts established, user queries asked, and insights discovered.
Keep the summary under 200 words. Do not drop key domain entities, names, or source URLs."""),
    ("human", """Existing Summary:
{existing_summary}

Recent Conversation Turns to Incorporate:
{recent_turns}""")
])

conversation_summarizer_chain = summarizer_prompt | verifier_llm | StrOutputParser()

def strip_chain_of_thought(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = getattr(text, "content", str(text))
    if not text:
        return ""

    raw_str = str(text)

    trimmed = raw_str.strip()
    if trimmed.startswith(("{", "[")):
        try:
            json.loads(trimmed)
            return trimmed
        except Exception:
            pass

    cleaned = re.sub(
        r"(?is)<(think|thought|reasoning)(?:\s+[^>]*)?>.*?</\1>",
        "",
        raw_str
    ).strip()

    cleaned = re.sub(
        r"(?is)<(think|thought|reasoning)(?:\s+[^>]*)?>.*$",
        "",
        cleaned
    ).strip()

    cleaned = re.sub(
        r"(?is)</(think|thought|reasoning)>",
        "",
        cleaned
    ).strip()

    match = re.search(r"(?m)^(#{1,4}\s+.+)$", cleaned)
    if match and match.start() > 0:
        preamble = cleaned[:match.start()].strip()
        meta_phrases = ["let me", "i need to", "i will", "the user wants", "i should", "let's do", "let draft", "i'll draft", "i'll write", "structure:"]
        if any(phrase in preamble.lower() for phrase in meta_phrases):
            cleaned = cleaned[match.start():].strip()

    return cleaned

def _find_json_candidates(text: str) -> List[Any]:
    decoder = json.JSONDecoder()
    candidates = []
    i = 0
    n = len(text)
    while i < n:
        match = re.search(r"[\{\[]", text[i:])
        if not match:
            break
        start_pos = i + match.start()
        try:
            obj, end_pos = decoder.raw_decode(text, start_pos)
            if isinstance(obj, (dict, list)):
                candidates.append((start_pos, end_pos, obj))
                i = end_pos
                continue
        except Exception:
            pass
        i = start_pos + 1
    return [c[2] for c in candidates]

def _select_best_candidate(candidates: List[Any], default: Any = None) -> Any:
    if not candidates:
        return default
    if len(candidates) == 1:
        return candidates[0]

    target_type = None
    if isinstance(default, (dict, list)):
        target_type = type(default)

    def _score(item_idx_pair):
        idx, item = item_idx_pair
        type_match = 1 if (target_type and isinstance(item, target_type)) else 0
        size = len(item) if isinstance(item, (dict, list)) else 0
        return (type_match, size > 0, size, idx)

    best_idx, best_item = max(enumerate(candidates), key=_score)
    return best_item

def safe_extract_json(raw_text: Any, default: Any = None) -> Any:
    if raw_text is None:
        return default
    if isinstance(raw_text, (dict, list)):
        return raw_text
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    text = raw_text.strip()
    if not text:
        return default

    try:
        return json.loads(text)
    except Exception:
        pass

    cleaned = strip_chain_of_thought(text).strip()
    if not cleaned:
        return default

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    fence_matches = list(re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE))
    if fence_matches:
        fenced_candidates = []
        for fm in fence_matches:
            fcontent = fm.group(1).strip()
            try:
                fenced_candidates.append(json.loads(fcontent))
                continue
            except Exception:
                pass
            fcands = _find_json_candidates(fcontent)
            if fcands:
                fenced_candidates.extend(fcands)
        if fenced_candidates:
            return _select_best_candidate(fenced_candidates, default)

    unfenced = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    unfenced = re.sub(r"\s*```$", "", unfenced, flags=re.MULTILINE).strip()
    if unfenced and unfenced != cleaned:
        try:
            return json.loads(unfenced)
        except Exception:
            pass
        unfenced_cands = _find_json_candidates(unfenced)
        if unfenced_cands:
            return _select_best_candidate(unfenced_cands, default)

    candidates = _find_json_candidates(cleaned)

    start_bracket = cleaned.find('[')
    start_brace = cleaned.find('{')
    if start_bracket != -1 and (start_brace == -1 or start_bracket < start_brace):
        has_array_candidate = any(isinstance(c, list) for c in candidates)
        if not has_array_candidate:
            try:
                salvaged = []
                sub_text = cleaned[start_bracket:]
                decoder = json.JSONDecoder()
                for m in re.finditer(r"\{", sub_text):
                    try:
                        obj, _ = decoder.raw_decode(sub_text, m.start())
                        if isinstance(obj, dict):
                            salvaged.append(obj)
                    except Exception:
                        pass
                if salvaged:
                    return {"results": salvaged} if any("claim" in p for p in salvaged) else salvaged
            except Exception:
                pass

    if candidates:
        return _select_best_candidate(candidates, default)

    try:
        start_bracket = cleaned.find('[')
        if start_bracket != -1:
            salvaged = []
            sub_text = cleaned[start_bracket:]
            decoder = json.JSONDecoder()
            for m in re.finditer(r"\{", sub_text):
                try:
                    obj, _ = decoder.raw_decode(sub_text, m.start())
                    if isinstance(obj, dict):
                        salvaged.append(obj)
                except Exception:
                    pass
            if salvaged:
                return {"results": salvaged} if any("claim" in p for p in salvaged) else salvaged
    except Exception:
        pass

    return default
