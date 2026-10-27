"""
S13 · Hypothesis: versions, rivals and strength markers (docs/features/04-hypothesis.md).

User-seat criteria encoded here:
  - The card shows four strength markers. Named constructs are the entry bar for a trial; a missing direction,
    scope or falsifier is a visible weakness, not a blocker. A marker counts only if its quoted words are in the
    hypothesis (the model cannot invent a falsifier the researcher never stated). With no model, markers are
    "not checked" and nothing is blocked.
  - Rivals live on the server: park one, retire one, swap one in (the old main becomes a rival, the rival a new
    version).
  - A trial is tied to the hypothesis version it tested; after a new version its verdict is labelled stale.
  - Swapping a rival in reuses the library: a re-mapped trial copies the papers and the Reader's records, so only
    the sub-claims, the matrix rows and the verdict rerun (no search, no Reader), and only on approval.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage

from backend.tests.scenarios.test_s16_trial_neutral_court import ANSWERS, RoleModel, _stub_library
from backend.tests.scenarios.conftest import read_sse

MAIN = "Night-shift nurses have higher emotional exhaustion than day-shift nurses because of circadian misalignment."
RIVAL = "Night-shift nurses have higher emotional exhaustion than day-shift nurses because of heavier workload."
MARKERS = {"constructs": [{"name": "night-shift work", "quote": "Night-shift nurses"}, {"name": "emotional exhaustion", "quote": "emotional exhaustion"},
                          {"name": "made up", "quote": "sleep quality index"}],
           "direction_comparison": {"quote": "higher emotional exhaustion than day-shift nurses"},
           "population_scope": None,
           "falsifier": {"quote": "no difference after controlling for workload"}}


def _install(monkeypatch, markers=MARKERS):
    import backend.research.llm as rl
    model = RoleModel({**ANSWERS, "strength markers": markers})
    monkeypatch.setattr(rl, "_llm", lambda role: model)
    return model


def _put(client, pid, section, value):
    return client.put(f"/api/projects/{pid}/notebook", json={"section": section, "value": value})


def test_markers_are_quoted_from_the_hypothesis_and_only_constructs_block_a_trial(client, monkeypatch):
    _install(monkeypatch)
    _put(client, "p13a", "hypothesis", MAIN)
    m = client.get("/api/projects/p13a/markers").json()
    assert m["checked"] is True and m["version"] == 1
    assert [c["name"] for c in m["constructs"]] == ["night-shift work", "emotional exhaustion"], "an unquoted construct is dropped"
    assert m["direction_comparison"]["present"] is True
    assert m["population_scope"]["present"] is False and m["falsifier"]["present"] is False, "a falsifier the text doesn't state is not counted"
    assert m["weaknesses"] == ["population or scope missing", "falsifier missing"]
    plan = client.post("/api/trial/plan", json={"project_id": "p13a", "hypothesis": MAIN})
    assert plan.status_code == 200, "missing falsifier and scope are weaknesses, not blockers"

    _install(monkeypatch, {"constructs": [], "direction_comparison": None, "population_scope": None, "falsifier": None})
    _put(client, "p13a", "hypothesis", "Things are bad at night.")
    m2 = client.get("/api/projects/p13a/markers").json()
    assert m2["version"] == 2 and m2["constructs"] == [] and "named constructs missing" in m2["weaknesses"]
    r = client.post("/api/trial/plan", json={"project_id": "p13a", "hypothesis": "Things are bad at night."})
    assert r.status_code == 400 and "name" in r.json()["detail"].lower()


def test_no_model_means_markers_not_checked_and_nothing_blocked(client):
    _put(client, "p13b", "hypothesis", "Things are bad at night.")
    m = client.get("/api/projects/p13b/markers").json()
    assert m["checked"] is False and m["weaknesses"] == []
    assert client.post("/api/trial/plan", json={"project_id": "p13b", "hypothesis": "Things are bad at night."}).status_code == 200


def test_rivals_can_be_parked_retired_and_swapped_in(client, monkeypatch):
    _install(monkeypatch)
    _put(client, "p13c", "hypothesis", MAIN)
    _put(client, "p13c", "rival_hypothesis", RIVAL)
    _put(client, "p13c", "rival_hypothesis", "It is the commute.")
    assert client.get("/api/projects/p13c/state").json()["rivals"] == [RIVAL, "It is the commute."]

    assert client.post("/api/projects/p13c/rivals/retire", json={"text": "It is the commute."}).json()["rivals"] == [RIVAL]
    assert client.post("/api/projects/p13c/rivals/swap", json={"text": "not a rival"}).status_code == 400
    st = client.post("/api/projects/p13c/rivals/swap", json={"text": RIVAL}).json()
    assert st["hypothesis"][-1]["text"] == RIVAL and st["hypothesis"][-1]["version"] == 2
    assert st["rivals"] == [MAIN], "the old main hypothesis is parked as a rival, not lost"


def _run(client, trial_id, approve=True):
    with client.stream("POST", f"/api/trial/{trial_id}/run", json={"approve": approve}) as r:
        return (r.status_code, read_sse(r, max_events=200, max_seconds=20) if r.status_code == 200 else [])


def test_a_swapped_rival_reuses_the_library_and_the_old_verdict_is_stale(client, monkeypatch):
    model = _install(monkeypatch)
    _stub_library(monkeypatch)
    _put(client, "p13d", "hypothesis", MAIN)
    _put(client, "p13d", "rival_hypothesis", RIVAL)
    old = client.post("/api/trial/plan", json={"project_id": "p13d", "hypothesis": MAIN}).json()
    _run(client, old["trial_id"])
    t = client.get(f"/api/trial/{old['trial_id']}").json()
    assert t["hypothesis_version"] == 1 and t["stale"] is False

    client.post("/api/projects/p13d/rivals/swap", json={"text": RIVAL})
    t = client.get(f"/api/trial/{old['trial_id']}").json()
    assert t["stale"] is True and t["hypothesis_now"] == {"version": 2, "text": RIVAL}

    import backend.research.librarian as L
    searched = []
    monkeypatch.setattr(L, "search", lambda *a, **k: searched.append(1))
    readers = len([c for c in model.calls if "Thoth's Reader" in c[0]])
    plan = client.post(f"/api/trial/{old['trial_id']}/remap", json={"project_id": "p13d"}).json()
    assert plan["remapped_from"] == old["trial_id"] and plan["hypothesis"] == RIVAL and plan["papers"] == 3
    assert "3 papers" in plan["estimate"]["scope"]
    new = client.get(f"/api/trial/{plan['trial_id']}").json()
    assert new["status"] == "planned" and all(p["record"] for p in new["papers"]), "records copied, nothing analysed yet"
    assert not any(p["row"] for p in new["papers"])

    assert _run(client, plan["trial_id"], approve=False)[0] == 403
    status, events = _run(client, plan["trial_id"])
    kinds = [e["event"] for e in events]
    assert kinds.count("paper_found") == 3 and kinds.count("matrix_row") == 3 and "verdict" in kinds
    assert "strategy" not in kinds and not searched, "no new search"
    assert len([c for c in model.calls if "Thoth's Reader" in c[0]]) == readers, "the Reader doesn't run again"
    assert RIVAL in [h for s, h in model.calls if "Thoth's Analyst" in s][-1]

    new = client.get(f"/api/trial/{plan['trial_id']}").json()
    assert new["status"] == "complete" and new["hypothesis_version"] == 2 and new["stale"] is False
    old_t = client.get(f"/api/trial/{old['trial_id']}").json()
    assert old_t["stale"] is True and old_t["verdict"], "the old trial and its verdict are kept"
    assert client.get("/api/trial/latest?project_id=p13d").json()["trial_id"] == plan["trial_id"]


def test_a_one_word_population_is_not_a_scope_and_constructs_are_not_repeated(client):
    from backend.research.hypothesis import enforce
    raw = {"constructs": [{"name": "shift type", "quote": "Night-shift"}, {"name": "shift type", "quote": "day-shift"}],
           "direction_comparison": None, "population_scope": {"quote": "nurses"}, "falsifier": None}
    m = enforce(raw, MAIN)
    assert [c["name"] for c in m["constructs"]] == ["shift type"]
    assert m["population_scope"]["present"] is False and "population or scope missing" in m["weaknesses"]
    with_dir = {**raw, "direction_comparison": {"quote": "higher emotional exhaustion than day-shift nurses"}}
    assert enforce({**with_dir, "population_scope": {"quote": "Night-shift nurses"}}, MAIN)["population_scope"]["present"] is False, \
        "repeats a construct and the comparison: scopes nothing"
    scoped = MAIN.replace("day-shift nurses", "day-shift nurses in Greek public hospitals")
    assert enforce({**with_dir, "population_scope": {"quote": "in Greek public hospitals"}}, scoped)["population_scope"]["present"] is True


def test_an_old_trial_without_a_recorded_version_is_matched_by_its_text(client):
    from backend.research import store
    from backend.memory import conversation_store as nb
    nb.write_section("p13f", "hypothesis", MAIN, "user")
    tid = store.create_trial("p13f", MAIN, [{"id": 1, "claim": "c"}])  # no version recorded (pre-feature trials)
    t = client.get(f"/api/trial/{tid}").json()
    assert t["hypothesis_version"] == 1 and t["version_inferred"] is True and t["stale"] is False
    nb.write_section("p13f", "hypothesis", RIVAL, "user")
    assert client.get(f"/api/trial/{tid}").json()["stale"] is True


def test_vague_placeholders_are_not_constructs(client):
    from backend.research.hypothesis import enforce
    m = enforce({"constructs": [{"name": "things", "quote": "Things"}, {"name": "night", "quote": "night"}],
                 "direction_comparison": {"quote": "worse at night"}, "population_scope": None, "falsifier": None},
                "Things just get worse at night.")
    assert [c["name"] for c in m["constructs"]] == ["night"]
    assert m["can_go_on_trial"] is False and "named constructs missing" in m["weaknesses"]

