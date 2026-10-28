"""
S20 · Thoth hears the thinkers (docs/features/01 + 03; the gap left in verify/conversation_core.md).

User-seat criteria encoded here:
  - What a thinker said in a one-to-one room, and where each thinker now stands on the project, reach Thoth's
    context, attributed and labelled as opinion (not evidence), within a size cap.
  - Thoth's recall search finds thinker words in the rooms too, and says who said them and where.
  - When older turns are folded into the rolling summary, a thinker's words keep the thinker's name.
  - Another project's rooms never leak in.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage

from backend.tests.scenarios.test_s10_conductor_memory_and_offers import ScriptedModel, _call, _install, _turn

PID = "p20"


def _seed(pid=PID):
    from backend.memory import conversation_store as store
    room = f"{pid}::room::popper"
    store.add_turn(room, "user", "Is my circadian story testable?", {"to_thinker": "popper", "mode": "room"})
    store.add_turn(room, "thinker", "Only if you say which sleep result would refute it. Name the falsifier first.",
                   {"thinker_id": "popper", "thinker_name": "Karl Popper", "mode": "room"})
    store.set_thinker_memory(pid, "popper", "Doubts the hypothesis can fail as stated; wants a falsifier on sleep timing.", True)
    store.set_thinker_memory(pid, "nightingale", "Wants ward-level counts before any mechanism.", False)


def _system_prompt(model):
    return model.inputs[-1][0].content


def test_rooms_and_stances_reach_thoths_context_attributed_and_labelled(client, monkeypatch):
    _seed()
    _seed("other_project")  # must not leak
    from backend.memory import conversation_store as store
    store.add_turn("other_project::room::hume", "thinker", "SECRET FROM ANOTHER PROJECT",
                   {"thinker_id": "hume", "thinker_name": "David Hume", "mode": "room"})
    model = _install(monkeypatch, ScriptedModel([AIMessage(content="Popper asked you for a falsifier.")]))
    _turn(client, {"message": "what did Popper tell me?", "project_id": PID})
    system = _system_prompt(model)
    block = system[system.index("<thinkers_heard>"):system.index("</thinkers_heard>")]
    assert "Karl Popper" in block and "Name the falsifier first." in block and "Is my circadian story testable?" in block
    assert "Doubts the hypothesis can fail as stated" in block and "Wants ward-level counts" in block
    assert "changed their mind" in block, "a stance that moved says so"
    assert "opinion, not evidence" in system
    assert "SECRET FROM ANOTHER PROJECT" not in system


def test_the_block_is_capped_and_says_so_when_empty(client, monkeypatch):
    from backend.conversation import conductor
    from backend.memory import conversation_store as store
    assert "none yet" in conductor.thinkers_heard("p20empty")
    for tid in ("popper", "hume", "darwin", "nightingale", "ostrom", "weber"):
        store.set_thinker_memory("p20big", tid, "x" * 2000, False)
        store.add_turn(f"p20big::room::{tid}", "thinker", "y" * 3000, {"thinker_id": tid, "thinker_name": tid.title()})
    assert len(conductor.thinkers_heard("p20big")) <= conductor.THINKERS_HEARD_MAX + 80


def test_recall_finds_room_turns_and_says_who_and_where(client, monkeypatch):
    _seed()
    model = _install(monkeypatch, ScriptedModel([_call("recall", {"query": "falsifier sleep"}), AIMessage(content="ok")]))
    _turn(client, {"message": "remind me what was said about a falsifier", "project_id": PID})
    tool_result = next(m for m in model.inputs[-1] if getattr(m, "type", "") == "tool")
    hits = json.loads(tool_result.content)
    room_hit = next(h for h in hits if "Name the falsifier" in h["content"])
    assert room_hit["who"] == "Karl Popper" and room_hit["where"] == "one-to-one with Karl Popper"


def test_the_rolling_summary_keeps_the_thinkers_name(client, monkeypatch):
    import asyncio
    import backend.agents as agents
    from backend.conversation import conductor
    from backend.memory import conversation_store as store
    seen = {}

    class Summariser:
        def invoke(self, inputs):
            seen.update(inputs)
            return "summary"

    monkeypatch.setattr(agents, "conversation_summarizer_chain", Summariser())
    store.add_turn("p20s", "thinker", "Measure melatonin, not mood.", {"thinker_id": "popper", "thinker_name": "Karl Popper"})
    for i in range(conductor.RECENT_TURNS + conductor.SUMMARY_EVERY + 1):
        store.add_turn("p20s", "user" if i % 2 else "assistant", f"turn {i}")
    async def go():
        await conductor._maybe_summarise("p20s", asyncio.get_running_loop())
    asyncio.run(go())
    assert "Karl Popper (thinker): Measure melatonin, not mood." in seen["recent_turns"]


def _answer(events):
    return next(e for e in events if e["event"] == "direct_answer")["payload"]


def test_a_made_up_quotation_is_flagged_and_a_real_one_is_not(client, monkeypatch):
    _seed()
    real = 'Popper said: "Only if you say which sleep result would refute it. Name the falsifier first."'
    made_up = 'Popper said: "Only if you say which sleep result would refute it, and a diary would never be enough for me."'
    _install(monkeypatch, ScriptedModel([AIMessage(content=real), AIMessage(content=made_up),
                                         AIMessage(content="> Only if you say which sleep result would refute it. Name the falsifier first.")]))
    ok = _answer(_turn(client, {"message": "what did Popper say?", "project_id": PID}))
    assert ok["misquotes"] == [] and "not in the record word for word" not in ok["answer"]
    bad = _answer(_turn(client, {"message": "and exactly?", "project_id": PID}))
    assert bad["misquotes"] and "Read it as a paraphrase" in bad["answer"], "invented words in quotation marks are flagged"
    block = _answer(_turn(client, {"message": "quote it", "project_id": PID}))
    assert block["misquotes"] == [], "a blockquote of the real words passes"
    from backend.memory import conversation_store as store
    assert store.recent_turns(PID, 10)[-3]["meta"]["misquotes"], "the flag is kept with the turn"
    from backend.conversation import conductor
    assert conductor.unsourced_quotes(made_up, PID, []), "Thoth's own earlier reply is not a source for its quote"


def test_quoting_a_paper_looked_up_this_turn_is_not_flagged(client, monkeypatch):
    import backend.conversation.conductor as cd

    async def quick_look(query):
        return [{"title": "Shift work and sleep", "abstract": "Night workers slept 1.2 hours less than day workers on average.", "year": 2021}]

    monkeypatch.setattr(cd, "_quick_look", quick_look)
    _install(monkeypatch, ScriptedModel([_call("quick_look", {"query": "night work sleep"}),
                                         AIMessage(content='One abstract says: "Night workers slept 1.2 hours less than day workers on average."')]))
    out = _answer(_turn(client, {"message": "how much less do night workers sleep?", "project_id": "p20q"}))
    assert out["misquotes"] == []
