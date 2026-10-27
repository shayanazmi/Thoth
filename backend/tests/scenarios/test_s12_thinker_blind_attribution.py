"""
S12 (live) · Blind attribution: do the ten thinkers sound like ten different minds?

docs/features/03-thinkers.md § Drift test. Every thinker answers the same three prompts through the
real persona prompt; names and signature terms are redacted; a judge model attributes each reply.
Each reply is judged on its own (no elimination). Pass: at least 80% correct overall and every thinker
identified in at least 6 of 9 prompts. Set THOTH_EVAL_DUMP=path.json to keep the replies and guesses.

Calls the live model (~180 calls, sequential: about an hour on the free tier), so it only runs with THOTH_LIVE_TESTS=1:
    THOTH_LIVE_TESTS=1 venv/bin/python -m pytest backend/tests/scenarios/test_s12_thinker_blind_attribution.py -s
"""
from __future__ import annotations

import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = [
    pytest.mark.live_llm,
    pytest.mark.skipif(os.environ.get("THOTH_LIVE_TESTS") != "1", reason="live model test; set THOTH_LIVE_TESTS=1"),
]

# Three kinds of question (causal claim from weak data, measurement choice, messy comparison) across three
# domains, so each thinker is judged on 9 replies. With only 3 (an earlier version), one judge slip decided
# pass/fail and the weak thinkers changed from run to run. Topics are spread so no thinker's home territory
# dominates (an all-nursing version biased the judge towards Nightingale).
PROMPTS = [
    # transport
    "A city added bike lanes to 20 streets and cycling injuries on those streets fell 30% the next year. "
    "I want to argue that bike lanes make cycling safer. What do you think?",
    "To find out whether a new bus route reduced car use, should I use traffic counts, or a survey asking "
    "residents how they travel? Which would you trust, and why?",
    "Town A has far more reported near-misses between cars and cyclists than Town B. But Town A has a phone app "
    "for reporting near-misses, and Town B has twice as many cycle paths. What should I make of this?",
    # education
    "Pupils who used a reading app at home scored higher on reading tests at the end of the year. I want to argue "
    "the app improves reading. What do you think?",
    "To find out whether pupils learned more under a new teaching method, should I use test scores, or "
    "teachers' observations of pupils' work? Which would you trust, and why?",
    "Pupils at School A report far more anxiety than pupils at School B. But School A runs a wellbeing programme "
    "that encourages talking about feelings, and School B streams pupils by ability. What should I make of this?",
    # work and economy
    "Companies that adopted a four-day week reported higher productivity a year later. I want to argue a four-day "
    "week makes people more productive. What do you think?",
    "To measure whether remote workers are as productive as office workers, should I use output metrics from "
    "their software, or managers' ratings? Which would you trust, and why?",
    "Firm A's staff report far more burnout than Firm B's. But Firm A runs an annual anonymous wellbeing survey, "
    "and Firm B lets staff choose their own hours. What should I make of this?",
]

# Words that give a thinker away without any reasoning (their own name, coined terms).
SIGNATURES = ["Verstehen", "ideal type", "paradigm", "falsif", "satisfic", "bounded rationality", "polycentric",
              "commons", "four causes", "Lyceum", "Scutari", "Crimea", "barnacle", "Beagle", "Ptolemy", "candle",
              "billiard", "Offenbacher", "Törbel", "Logic of Scientific Discovery"]


def _redact(text: str, names: list[str]) -> str:
    words = names + [n.split()[-1] for n in names] + ["Alhazen", "Haytham", "Stagirite"] + SIGNATURES
    return re.sub("|".join(re.escape(w) for w in words), "[REDACTED]", text, flags=re.I)


def _patient(call, *args):
    """The free tier rate-limits by time window. Wait it out and retry the SAME model (never a fallback)."""
    import time
    for attempt in range(8):
        try:
            out = call(*args)
            time.sleep(2)
            return out
        except Exception as exc:
            if "429" not in str(exc) or attempt == 7:
                raise
            time.sleep(30 * (attempt + 1))


def test_ten_thinkers_are_distinguishable_blind():
    from langchain_core.messages import HumanMessage, SystemMessage

    from backend.agents import get_role_llm
    from backend.thinkers import persona, roster

    thinker_llm = get_role_llm("thinker", allow_fallback=False)  # a fallback answer is not the persona
    judge_llm = get_role_llm("evaluator", allow_fallback=False)
    names = {t["id"]: t["name"] for t in roster.ROSTER}

    def speak(tid: str, prompt: str) -> str:
        system = persona.system_prompt(tid, "join")
        return thinker_llm.invoke([SystemMessage(content=system), HumanMessage(content=f"The researcher's latest message:\n{prompt}")]).content

    def judge(reply: str) -> str:
        ask = (f"One of these thinkers wrote the reply below: {', '.join(names.values())}. Names and signature terms "
               "are redacted. Judge from reasoning style, concerns and temperament. Answer with only the thinker's "
               "full name from the list, nothing else.\n\n<reply>\n" + reply + "\n</reply>")
        out = (judge_llm.invoke([HumanMessage(content=ask)]).content or "").strip()
        # Take the last roster name mentioned, in case the model explains first.
        found = [(out.rfind(n), n) for n in names.values() if n in out]
        return max(found)[1] if found else out[-60:]

    hits: dict[str, int] = {tid: 0 for tid in names}
    total = correct = 0
    report, dump = [], []
    for p_i, prompt in enumerate(PROMPTS):
        with ThreadPoolExecutor(1) as ex:  # sequential: the free tier's per-minute limit rejects even 2 at a time
            replies = dict(zip(names, ex.map(lambda tid: _patient(speak, tid, prompt), names)))
            blind = {t: _redact(replies[t], list(names.values())) for t in names}
            guesses = dict(zip(names, ex.map(lambda t: _patient(judge, blind[t]), names)))
        for tid in names:
            ok = guesses[tid] == names[tid]
            hits[tid] += ok
            correct += ok
            total += 1
            dump.append({"prompt": p_i + 1, "thinker": names[tid], "guess": guesses[tid], "reply": replies[tid]})
            if not ok:
                report.append(f"prompt {p_i + 1}: {names[tid]} read as {guesses[tid]}")

    if os.environ.get("THOTH_EVAL_DUMP"):
        with open(os.environ["THOTH_EVAL_DUMP"], "w", encoding="utf-8") as f:
            json.dump(dump, f, indent=1, ensure_ascii=False)
    print(f"\nBlind attribution: {correct}/{total}")
    print("Per thinker:", {names[t]: f"{h}/{len(PROMPTS)}" for t, h in hits.items()})
    print("Misses:", report or "none")
    assert correct / total >= 0.8, report
    assert all(h >= 6 for h in hits.values()), {names[t]: h for t, h in hits.items()}
