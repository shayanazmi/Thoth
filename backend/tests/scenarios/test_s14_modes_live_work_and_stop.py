"""
S14 · Autopilot / Co-pilot, live work and Stop (docs/features/02-threads-projects-notebook.md).

User-seat criteria encoded here:
  - Each project has one mode (Co-pilot by default) with per-step overrides; it is stored on the server.
  - Autopilot never skips the up-front approval for a heavy run: a trial still runs only on approve: true.
  - A running trial reports its work as it goes: papers found and analysed, and model calls used (with how many
    the fallback answered), so the header can show them against the estimate.
  - Stop keeps what's done: finished rows stay, the rest are marked "not run", the trial is "stopped", and a
    verdict weighed afterwards names the papers that weren't run (it is not presented as complete).
  - Proposal sections: Co-pilot writes one section per approval; Autopilot writes them all.
"""
from __future__ import annotations

import asyncio
import json

from langchain_core.messages import AIMessage

from backend.tests.scenarios.conftest import read_sse
from backend.tests.scenarios.test_s16_trial_neutral_court import ANSWERS, HYP, RoleModel


def _install(monkeypatch, extra=None):
    import backend.research.llm as rl
    model = RoleModel({**ANSWERS, **(extra or {})})
    monkeypatch.setattr(rl, "_llm", lambda role: model)
    return model


def _slow_library(monkeypatch, n=4, slow_after=1, delay=1.5):
    """n papers; the first `slow_after` arrive at once, the rest take `delay` seconds each to fetch."""
    import backend.research.librarian as L

    async def search(strat, limit=15, subclaims=None):
        return [{"title": f"Paper {i}", "year": 2020, "authors": ["A"], "doi": f"10.1/{i}", "abstract": "abs"} for i in range(n)]

    async def full_text(meta):
        if int(meta["title"].split()[-1]) >= slow_after:
            await asyncio.sleep(delay)
        return "ABSTRACT TEXT", "abstract_only", "test"

    async def adjacent(strat, per_field=4):
        return {"ran": False, "fields": []}

    monkeypatch.setattr(L, "search", search)
    monkeypatch.setattr(L, "full_text", full_text)
    monkeypatch.setattr(L, "adjacent_search", adjacent)


def test_mode_is_per_project_with_step_overrides(client):
    assert client.get("/api/projects/p14a/mode").json() == {"mode": "copilot", "step_overrides": {},
                                                           "effective": {"subclaims": "copilot", "screening": "copilot", "proposal": "copilot"}}
    out = client.put("/api/projects/p14a/mode", json={"mode": "autopilot", "step_overrides": {"proposal": "copilot"}}).json()
    assert out["effective"] == {"subclaims": "autopilot", "screening": "autopilot", "proposal": "copilot"}
    assert client.put("/api/projects/p14a/mode", json={"mode": "yolo"}).status_code == 400
    assert client.put("/api/projects/p14a/mode", json={"mode": "copilot", "step_overrides": {"everything": "autopilot"}}).status_code == 400
    assert client.get("/api/projects/p14a/state").json()["mode"]["mode"] == "autopilot"
    assert client.get("/api/projects/p14b/mode").json()["mode"] == "copilot", "modes are per project"


def test_autopilot_still_needs_approval_and_the_run_reports_its_work(client, monkeypatch):
    _install(monkeypatch)
    _slow_library(monkeypatch, n=3, slow_after=3)
    client.put("/api/projects/p14c/mode", json={"mode": "autopilot"})
    plan = client.post("/api/trial/plan", json={"project_id": "p14c", "hypothesis": HYP}).json()
    assert plan["mode"] == "autopilot"
    with client.stream("POST", f"/api/trial/{plan['trial_id']}/run", json={}) as r:
        assert r.status_code == 403, "autopilot never skips the up-front approval"
    with client.stream("POST", f"/api/trial/{plan['trial_id']}/run", json={"approve": True}) as r:
        events = read_sse(r, max_events=200, max_seconds=20)
    usage = [e["payload"] for e in events if e["event"] == "usage"]
    assert usage and usage[-1]["found"] == 3 and usage[-1]["analysed"] == 3
    # Sub-claims were split at planning; the run makes Librarian strategy + 3 Reader + 3 Appraiser + 3 Analyst
    # + Judge = 11 calls (citation following makes no model calls).
    assert usage[-1]["model_calls"] == 11 and usage[-1]["fallback_calls"] == 0
    assert [u["model_calls"] for u in usage] == sorted(u["model_calls"] for u in usage), "counts only grow"


def test_stop_keeps_finished_rows_and_marks_the_rest_not_run(client, monkeypatch):
    _install(monkeypatch)
    _slow_library(monkeypatch, n=4, slow_after=1, delay=3)
    plan = client.post("/api/trial/plan", json={"project_id": "p14d", "hypothesis": HYP}).json()
    tid = plan["trial_id"]
    assert client.post(f"/api/trial/{tid}/stop").status_code == 409, "only a running trial can be stopped"
    from backend.research import store, trial as trial_mod
    other = store.create_trial("p14d", HYP, [{"id": 1, "claim": "c"}])
    store.update_trial(other, status="running")
    assert client.post(f"/api/trial/{other}/stop").json() == {"stopping": True, "trial_id": other}
    assert other in trial_mod.STOPS
    # The test client buffers a whole SSE response, so the run is driven directly and Stop is pressed between
    # events, as the stop endpoint would (it is checked over HTTP below).
    from backend.research import trial as trial_mod

    async def drive():
        out = []
        async for name, payload in trial_mod.run(tid):
            out.append({"event": name, "payload": payload})
            if name == "matrix_row":
                assert client.get(f"/api/trial/{tid}").json()["status"] == "running"
                trial_mod.request_stop(tid)
        return out

    events = asyncio.run(drive())
    kinds = [e["event"] for e in events]
    assert "stopped" in kinds and "verdict" not in kinds, "no verdict is weighed without being asked"
    stopped = next(e["payload"] for e in events if e["event"] == "stopped")
    assert stopped["analysed"] == 1 and stopped["not_run"] == 3
    t = client.get(f"/api/trial/{tid}").json()
    assert t["status"] == "stopped"
    assert sorted(p["status"] for p in t["papers"]) == ["done", "not_run", "not_run", "not_run"]

    v = client.post(f"/api/trial/{tid}/rejudge").json()
    assert any("3 papers were not run" in n for n in v["guardrail_notes"]), "a partial verdict says so"
    assert client.post(f"/api/trial/{tid}/stop").status_code == 409


def test_a_restart_marks_unfinished_papers_not_run(client):
    from backend.research import store
    tid = store.create_trial("p14e", HYP, [{"id": 1, "claim": "c"}])
    store.update_trial(tid, status="running")
    a, b = store.add_paper(tid, {"title": "A"}), store.add_paper(tid, {"title": "B"})
    store.update_paper(a, status="done")
    store.update_paper(b, status="reading")
    old = store.create_trial("p14e", HYP, [{"id": 1, "claim": "c"}])  # stopped by an older build, papers left mid-way
    store.update_trial(old, status="stopped")
    store.update_paper(store.add_paper(old, {"title": "C"}), status="analysing")
    store.reconcile_orphaned_trials()
    assert store.get_trial(tid)["status"] == "stopped"
    assert [p["status"] for p in store.list_papers(old)] == ["not_run"]
    assert {p["meta"]["title"]: p["status"] for p in store.list_papers(tid)} == {"A": "done", "B": "not_run"}


SECTION = {"markdown": "## X\n\nThis study will recruit nurses."}
OUTLINE = [{"key": "background", "title": "Background", "purpose": "p"}, {"key": "methods", "title": "Methods", "purpose": "p"},
           {"key": "timeline", "title": "Timeline", "purpose": "p"}]


def _write(client, pid):
    with client.stream("POST", "/api/proposal/write", json={"project_id": pid, "approve": True, "outline": OUTLINE}) as r:
        return [e["event"] for e in read_sse(r, max_events=100, max_seconds=20)]


def test_copilot_writes_one_proposal_section_per_approval_autopilot_writes_all(client, monkeypatch):
    _install(monkeypatch, {"Thoth's Writer": SECTION, "Thoth's Reviewer": {"summary": "ok", "weaknesses": []}})
    from backend.memory import conversation_store as nb
    for pid in ("p14f", "p14g"):
        nb.write_section(pid, "hypothesis", HYP, "user")

    first = _write(client, "p14f")
    assert first.count("section_done") == 1 and "awaiting_next" in first and "review_start" not in first
    second = _write(client, "p14f")
    assert second.count("section_done") == 1
    third = _write(client, "p14f")
    assert third.count("section_done") == 1 and "review_start" in third, "the Reviewer runs once every section is written"

    client.put("/api/projects/p14g/mode", json={"mode": "autopilot"})
    all_at_once = _write(client, "p14g")
    assert all_at_once.count("section_done") == 3 and "awaiting_next" not in all_at_once
