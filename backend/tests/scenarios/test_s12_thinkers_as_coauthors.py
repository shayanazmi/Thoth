"""
S12 · Thinkers as co-authors (docs/features/03-thinkers.md).

User-seat criteria encoded here:
  - The roster is the approved ten; benched thinkers are not offered.
  - A thinker speaks from their dossier: the prompt carries their mind, the misreadings to avoid,
    and their memory of this project, and no shared rule script.
  - What a thinker says in the main chat is remembered by the project (Thoth sees it next turn).
  - Reviews are independent: no reviewer's prompt contains another reviewer's text.
  - Debates are sequential: each speaker sees what was said before; Thoth distils it, and a
    suggested hypothesis is only a proposal.
  - Co-author memory: after an exchange the thinker's stance is stored and fed into the next prompt.
  - With no model reachable, nothing is said on a thinker's behalf.
  - The profile behind a bust comes from the dossier.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage

from backend.tests.scenarios.conftest import read_sse as _read_sse

APPROVED = ["aristotle", "ibn_al_haytham", "hume", "darwin", "nightingale", "weber", "popper", "kuhn", "simon", "ostrom"]


class RecordingModel:
    """Answers every call, recording the system and human text. ``answer`` maps a call to a reply."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def bind_tools(self, *a, **k):
        return self

    def invoke(self, messages, **kw):
        system, human = messages[0].content, messages[-1].content
        self.calls.append((system, human))
        return AIMessage(content=self.answer(system, human))


def _install(monkeypatch, answer):
    import backend.thinkers.modes as modes
    model = RecordingModel(answer)
    monkeypatch.setattr(modes, "_llm", lambda role: model)
    return model


def _speaker(system: str) -> str:
    m = re.search(r"You are ([^.]+)\. Someone has asked", system)
    return m.group(1) if m else ""


def _persona_answer(system, human):
    if "keep concise notes" in system:
        return json.dumps({"stance": "Thinks the comparison group matters most.", "changed": False, "change_note": ""})
    if "extract structure" in system:
        return json.dumps({"verdict": "mixed", "concerns": [{"claim": "causal", "severity": "serious", "why": "cross-sectional"}], "would_change_mind_if": "longitudinal data"})
    if "summarising fairly" in system:
        return json.dumps({"summary": "They agreed sleep matters; they disagreed on what would count as a test.", "hypothesis_suggestion": "Night shifts raise exhaustion via circadian misalignment, testable longitudinally."})
    return f"REPLY FROM {_speaker(system)}"


def test_roster_is_the_approved_ten(client):
    ids = [t["id"] for t in client.get("/api/thinkers").json()["thinkers"]]
    assert ids == APPROVED
    for benched in ("bacon", "box", "descartes", "turing"):
        assert benched not in ids
    assert client.get("/api/thinkers/bacon/profile").status_code == 404


def test_profile_comes_from_the_dossier(client):
    p = client.get("/api/thinkers/nightingale/profile").json()
    assert p["name"] == "Florence Nightingale"
    assert "Statistical Society" in p["life"] and "Collected Works" in p["sources"]


def test_join_speaks_from_dossier_and_is_remembered_by_the_project(client, monkeypatch):
    model = _install(monkeypatch, _persona_answer)
    out = client.post("/api/thinkers/popper/reply", json={"project_id": "p12a", "message": "One nurse never burned out. Falsified?", "mode": "join"}).json()
    assert out["reply"] == "REPLY FROM Karl Popper" and out["degraded"] is False
    system = model.calls[0][0]
    assert "<dossier>" in system and "Logic of Scientific Discovery" in system
    assert "One counterexample refutes any claim" in system  # misreading to avoid
    assert "Phase 1: Diagnostic Challenge" not in system  # the retired shared sparring script

    from backend.memory import conversation_store as store
    roles = [(t["role"], t["meta"].get("thinker_id")) for t in store.recent_turns("p12a")]
    assert ("thinker", "popper") in roles, "the main thread must remember what the thinker said"
    # The background memory update ran after the response.
    assert store.get_thinker_memory("p12a", "popper")["stance"] == "Thinks the comparison group matters most."


def test_memory_feeds_the_next_prompt(client, monkeypatch):
    from backend.memory import conversation_store as store
    store.set_thinker_memory("p12b", "hume", "Doubts the causal arrow; wants a before/after comparison.", False)
    model = _install(monkeypatch, _persona_answer)
    client.post("/api/thinkers/hume/reply", json={"project_id": "p12b", "message": "What now?", "mode": "room"})
    assert "Doubts the causal arrow" in model.calls[0][0]
    # Room conversations stay out of the main thread.
    assert all(t["role"] != "thinker" for t in store.recent_turns("p12b"))


def test_reviews_are_independent(client, monkeypatch):
    model = _install(monkeypatch, _persona_answer)
    res = client.post("/api/thinkers/review", json={"project_id": "p12c", "artifact": "hypothesis",
                                                     "text": "Night-shift nurses have higher emotional exhaustion.",
                                                     "thinker_ids": ["popper", "hume", "nightingale"]}).json()
    assert [r["thinker_id"] for r in res["reviews"]] == ["popper", "hume", "nightingale"]
    assert all(r["envelope"]["verdict"] == "mixed" for r in res["reviews"])
    review_calls = [(s, h) for s, h in model.calls if "MODE: review" in s]
    assert len(review_calls) == 3
    for system, human in review_calls:
        others = {"REPLY FROM Karl Popper", "REPLY FROM David Hume", "REPLY FROM Florence Nightingale"}
        assert not any(o in system or o in human for o in others), "a reviewer saw another review"


def test_default_reviewers_include_a_domain_voice(client):
    from backend.thinkers.modes import default_reviewers
    assert default_reviewers("night-shift nurses in hospitals") == ["popper", "hume", "nightingale"]


def test_debate_is_sequential_and_ends_in_a_proposal_not_an_edit(client, monkeypatch):
    model = _install(monkeypatch, _persona_answer)
    with client.stream("POST", "/api/thinkers/debate", json={"project_id": "p12d", "thinker_ids": ["popper", "kuhn"],
                                                             "question": "Can one study settle this?", "rounds": 2,
                                                             "hypothesis": "Night shifts raise exhaustion."}) as r:
        events = _read_sse(r, max_events=40)
    kinds = [e["event"] for e in events]
    turns = [e["payload"] for e in events if e["event"] == "debate_turn"]
    assert [t["thinker_id"] for t in turns] == ["popper", "kuhn", "popper", "kuhn"]
    debate_humans = [h for s, h in model.calls if "MODE: debate" in s]
    assert "You open the debate" in debate_humans[0]
    assert "REPLY FROM Karl Popper" in debate_humans[1], "the second speaker must see the first"
    assert "debate_summary" in kinds and "notebook_proposal" in kinds
    from backend.memory import conversation_store as store
    assert "hypothesis" not in store.notebook_snapshot("p12d"), "a debate may only propose, never edit"


def test_no_model_means_nothing_said_on_their_behalf(client):
    # Default scenario env: no provider reachable.
    out = client.post("/api/thinkers/darwin/reply", json={"project_id": "p12e", "message": "Thoughts?", "mode": "join"}).json()
    assert out["degraded"] is True and out["reply"] == ""
    council = client.post("/api/thinkers/council", json={"project_id": "p12e", "idea": "night shifts and burnout"}).json()
    assert council["degraded"] is True and all(t["take"] == "" for t in council["council"])
    from backend.memory import conversation_store as store
    assert all(t["role"] != "thinker" for t in store.recent_turns("p12e"))


def test_conductor_suggests_from_the_new_roster(client):
    from backend.conversation.conductor import _roster, _tool_schemas
    ids = list(_roster())
    assert ids == APPROVED
    enum = next(t for t in _tool_schemas(ids) if t["function"]["name"] == "suggest_thinker")["function"]["parameters"]["properties"]["thinker_id"]["enum"]
    assert enum == APPROVED
