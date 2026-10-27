"""How thinkers take part (docs/features/03-thinkers.md § Modes).

join / room   one thinker talking with the researcher (main thread / private room)
review        each chosen thinker assesses an artefact INDEPENDENTLY (separate calls, no shared text)
council       every thinker gives a first reaction, independently
debate        2-3 thinkers in sequential rounds, each seeing the debate so far; Thoth distils it

Every thinker exchange updates that thinker's stance on the project (co-author memory).
When no model is reachable, nothing is invented: the call reports that the thinker could not respond.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agents import MODEL_SLOTS, get_role_llm, safe_extract_json, sanitize_log_message, strip_chain_of_thought
from backend.memory import conversation_store as store
from backend.thinkers import persona, roster

logger = logging.getLogger("ThothThinkers")

HISTORY_TURNS = 12
MAX_DEBATERS = 3
# Concurrent model calls are capped by backend.agents.MODEL_SLOTS (shared with the trial roles).


def _llm(role: str):
    """Indirection so scenario tests can stub the model."""
    return get_role_llm(role)


async def _invoke(role: str, system: str, human: str) -> str:
    loop = asyncio.get_running_loop()
    model = _llm(role)

    def call():
        with MODEL_SLOTS:
            return model.invoke([SystemMessage(content=system), HumanMessage(content=human)])

    msg = await loop.run_in_executor(None, call)
    return strip_chain_of_thought(getattr(msg, "content", msg) or "").strip()


_background: set = set()


def _in_background(coro) -> None:
    """Memory updates must not hold up the reply the researcher is waiting for."""
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def room_thread(thread_id: str, thinker_id: str) -> str:
    return f"{thread_id}::room::{thinker_id}"


def _name(thinker_id: str) -> str:
    return roster.get(thinker_id)["name"]


def _thinker_meta(thinker_id: str, mode: str, **extra: Any) -> Dict[str, Any]:
    return {"thinker_id": thinker_id, "thinker_name": _name(thinker_id), "mode": mode, **extra}


async def update_memory(thread_id: str, thinker_id: str, exchange: str) -> None:
    """Co-author memory: rewrite the thinker's stance on this project after an exchange."""
    previous = store.get_thinker_memory(thread_id, thinker_id)["stance"] or "(none yet)"
    try:
        raw = await _invoke("thinker_support", "You keep concise notes on a co-author's views.",
                            persona.MEMORY_UPDATE.format(name=_name(thinker_id), previous=previous, exchange=exchange[-6000:]))
        data = safe_extract_json(raw, default={}) or {}
        stance = str(data.get("stance") or "").strip()
        if stance:
            store.set_thinker_memory(thread_id, thinker_id, stance, bool(data.get("changed")))
    except Exception as exc:
        logger.info("[thinkers] memory update skipped for %s: %s", thinker_id, sanitize_log_message(str(exc)))


async def reply(thread_id: str, thinker_id: str, message: str, mode: str = "join") -> Dict[str, Any]:
    """One thinker answers the researcher. Returns the reply and a coroutine-free result;
    the caller schedules ``update_memory`` (see ``memory_job``)."""
    if roster.get(thinker_id) is None:
        raise KeyError(thinker_id)
    where = thread_id if mode == "join" else room_thread(thread_id, thinker_id)
    history = store.recent_turns(where, HISTORY_TURNS)
    store.add_turn(where, "user", message, {"to_thinker": thinker_id, "mode": mode})

    memory = store.get_thinker_memory(thread_id, thinker_id)["stance"]
    system = persona.system_prompt(thinker_id, mode, memory)
    human = (
        (f"The conversation so far:\n<conversation>\n{persona.transcript(history)}\n</conversation>\n\n" if history else "")
        + f"The researcher's latest message:\n{message}"
    )
    try:
        text = await _invoke("thinker", system, human)
    except Exception as exc:
        logger.warning("[thinkers] %s could not respond: %s", thinker_id, sanitize_log_message(str(exc)))
        text = ""
    if not text:
        return {"thinker_id": thinker_id, "thinker_name": _name(thinker_id), "reply": "", "degraded": True,
                "message": f"{_name(thinker_id)} couldn't be reached right now. Nothing was said on their behalf."}
    store.add_turn(where, "thinker", text, _thinker_meta(thinker_id, mode))
    return {"thinker_id": thinker_id, "thinker_name": _name(thinker_id), "reply": text, "degraded": False,
            "exchange": f"Researcher: {message}\n\n{_name(thinker_id)}: {text}"}


async def _review_one(thread_id: str, thinker_id: str, artifact: str, text: str) -> Dict[str, Any]:
    memory = store.get_thinker_memory(thread_id, thinker_id)["stance"]
    system = persona.system_prompt(thinker_id, "review", memory, artifact=artifact)
    out: Dict[str, Any] = {"thinker_id": thinker_id, "thinker_name": _name(thinker_id), "artifact": artifact}
    try:
        review = await _invoke("thinker", system, f"The {artifact} to assess:\n<untrusted>\n{text}\n</untrusted>")
    except Exception as exc:
        logger.warning("[thinkers] review by %s failed: %s", thinker_id, sanitize_log_message(str(exc)))
        review = ""
    if not review:
        return {**out, "review": "", "degraded": True, "envelope": None}
    envelope = None
    try:
        raw = await _invoke("thinker_support", "You extract structure from reviews without adding anything.",
                            persona.REVIEW_ENVELOPE.format(name=_name(thinker_id), review=review))
        envelope = safe_extract_json(raw, default=None)
        if not isinstance(envelope, dict):
            logger.warning("[thinkers] envelope for %s was not valid JSON; review kept without it", thinker_id)
            envelope = None
    except Exception as exc:
        logger.info("[thinkers] envelope skipped for %s: %s", thinker_id, sanitize_log_message(str(exc)))
    store.add_turn(thread_id, "thinker", review, _thinker_meta(thinker_id, "review", artifact=artifact, envelope=envelope))
    _in_background(update_memory(thread_id, thinker_id, f"{_name(thinker_id)} reviewed the {artifact}:\n{text}\n\nTheir review:\n{review}"))
    return {**out, "review": review, "degraded": False, "envelope": envelope}


async def review(thread_id: str, thinker_ids: List[str], artifact: str, text: str) -> List[Dict[str, Any]]:
    """Independent reviews: run in parallel, and no reviewer's prompt contains another's review."""
    ids = [t for t in dict.fromkeys(thinker_ids) if roster.get(t)]
    return list(await asyncio.gather(*[_review_one(thread_id, t, artifact, text) for t in ids]))


def default_reviewers(text: str) -> List[str]:
    """Until the conductor picks reviewers from territories, a sensible default trio:
    the two hypothesis-testers plus one domain voice."""
    low = text.lower()
    if any(w in low for w in ("nurse", "patient", "hospital", "health", "mortality", "clinic", "care")):
        third = "nightingale"
    elif any(w in low for w in ("community", "institution", "rule", "commons", "governance", "cooperat")):
        third = "ostrom"
    elif any(w in low for w in ("meaning", "culture", "belief", "religio", "motivation", "workplace")):
        third = "weber"
    else:
        third = "darwin"
    return ["popper", "hume", third]


async def council(thread_id: str, idea: str) -> List[Dict[str, Any]]:
    async def one(tid: str) -> Dict[str, Any]:
        memory = store.get_thinker_memory(thread_id, tid)["stance"]
        try:
            take = await _invoke("thinker", persona.system_prompt(tid, "council", memory), f"The idea:\n<untrusted>\n{idea}\n</untrusted>")
        except Exception as exc:
            logger.info("[thinkers] council take from %s failed: %s", tid, sanitize_log_message(str(exc)))
            take = ""
        return {"id": tid, "name": _name(tid), "brings": roster.get(tid)["brings"], "take": take, "degraded": not take}

    takes = list(await asyncio.gather(*[one(t) for t in roster.ROSTER_IDS]))
    heard = [t for t in takes if t["take"]]
    if heard:
        store.add_turn(thread_id, "assistant", "[First reactions from the thinkers]\n" + "\n".join(f"{t['name']}: {t['take']}" for t in heard),
                       {"mode": "council"})
    return takes


async def debate(thread_id: str, thinker_ids: List[str], question: str, rounds: int = 3,
                 hypothesis: str = "") -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Sequential turn-taking: each speaker sees the debate so far. Then Thoth distils it."""
    ids = [t for t in dict.fromkeys(thinker_ids) if roster.get(t)][:MAX_DEBATERS]
    if len(ids) < 2:
        yield "error", {"error": "A debate needs two or three thinkers from the roster."}
        return
    rounds = max(1, min(int(rounds or 3), 3))
    yield "debate_start", {"thinkers": [{"id": t, "name": _name(t)} for t in ids], "question": question, "rounds": rounds}
    store.add_turn(thread_id, "user", f"[Debate requested] {', '.join(_name(t) for t in ids)} on: {question}", {"mode": "debate"})

    spoken: List[Dict[str, Any]] = []
    for r in range(1, rounds + 1):
        for tid in ids:
            others = " and ".join(_name(o) for o in ids if o != tid)
            system = persona.system_prompt(tid, "debate", store.get_thinker_memory(thread_id, tid)["stance"],
                                           others=others, question=question, round_no=r, rounds=rounds)
            so_far = persona.transcript(spoken) if spoken else "(Nobody has spoken yet. You open the debate.)"
            human = f"Hypothesis on the table: {hypothesis or '(none stated)'}\n\nThe debate so far:\n<conversation>\n{so_far}\n</conversation>"
            try:
                text = await _invoke("thinker", system, human)
            except Exception as exc:
                logger.warning("[thinkers] debate turn by %s failed: %s", tid, sanitize_log_message(str(exc)))
                text = ""
            if not text:
                yield "debate_stopped", {"reason": f"{_name(tid)} couldn't be reached, so the debate stops here rather than continue one-sided."}
                return
            turn = {"role": "thinker", "content": text, "meta": _thinker_meta(tid, "debate", round=r)}
            spoken.append(turn)
            store.add_turn(thread_id, "thinker", text, turn["meta"])
            yield "debate_turn", {"thinker_id": tid, "thinker_name": _name(tid), "round": r, "text": text}

    debate_text = persona.transcript(spoken)
    summary, suggestion = "", ""
    try:
        raw = await _invoke("thinker_support", "You are Thoth, summarising fairly for a researcher.",
                            persona.DEBATE_DISTILL.format(question=question, hypothesis=hypothesis or "(none)", debate=debate_text))
        data = safe_extract_json(raw, default={}) or {}
        summary = str(data.get("summary") or "").strip()
        suggestion = str(data.get("hypothesis_suggestion") or "").strip()
    except Exception as exc:
        logger.info("[thinkers] debate distillation failed: %s", sanitize_log_message(str(exc)))
    if summary:
        store.add_turn(thread_id, "assistant", f"[Debate summary] {summary}", {"mode": "debate_summary"})
    yield "debate_summary", {"summary": summary, "degraded": not summary}
    if suggestion and suggestion != hypothesis:
        payload = {"section": "hypothesis", "value": suggestion, "why": f"Suggested by the debate between {', '.join(_name(t) for t in ids)}."}
        pid = store.add_proposal(thread_id, "notebook_proposal", payload)
        yield "notebook_proposal", {"proposal_id": pid, **payload}
    for tid in ids:
        _in_background(update_memory(thread_id, tid, f"Debate on: {question}\n\n{debate_text}"))
