"""
S11 · Threads, projects and retention (docs/features/02-threads-projects-notebook.md).

User-seat criteria encoded here:
  - A new chat is a thread; it becomes a project when a hypothesis is accepted (by the researcher writing it, or
    by accepting Thoth's proposal). Nothing moves: the same id keeps its turns, notes and papers.
  - The project's state lives on the server: a second browser (empty localStorage) gets back the question,
    every hypothesis version with who wrote it, the rivals and the conversation.
  - Deleting a project needs one confirmation that lists counts; afterwards nothing is left for that id in any
    table (turns, thinker rooms, notebook, proposals, thinker memory, trials and their papers, systematic
    reviews and their records, the project row).
"""
from __future__ import annotations

import json



def _new(client, title="Why do night-shift nurses burn out more?"):
    return client.post("/api/projects", json={"title": title}).json()["project"]["project_id"]


def _kinds(client):
    return {p["project_id"]: p.get("kind") for p in client.get("/api/projects").json()["projects"]}


def test_a_chat_is_a_thread_until_a_hypothesis_is_accepted(client):
    pid = _new(client)
    assert client.get(f"/api/projects/{pid}/state").json()["kind"] == "thread"
    assert _kinds(client)[pid] == "thread"

    from backend.memory import conversation_store as store
    store.add_turn(pid, "user", "Why do night nurses burn out?")
    prop = store.add_proposal(pid, "notebook_proposal", {"section": "hypothesis", "value": "Night nurses burn out more because of misalignment."})
    r = client.post(f"/api/chat/proposals/{prop}", json={"action": "accept"})
    assert r.status_code == 200

    st = client.get(f"/api/projects/{pid}/state").json()
    assert st["kind"] == "project" and st["promoted_at"], "accepting a hypothesis promotes the thread"
    assert st["messages"][0]["text"] == "Why do night nurses burn out?", "the thread's turns stay with the project"
    assert _kinds(client)[pid] == "project"


def test_a_second_browser_gets_the_whole_project_back(client):
    pid = _new(client)
    from backend.memory import conversation_store as store
    store.add_turn(pid, "user", "Do night nurses burn out more?")
    store.add_turn(pid, "assistant", "Often, yes; the question is why.")
    store.add_turn(pid, "thinker", "Ask what would show you wrong.", {"thinker_id": "popper", "thinker_name": "Karl Popper"})
    store.add_turn(f"{pid}::room::hume", "user", "private room chat")

    put = lambda section, value: client.put(f"/api/projects/{pid}/notebook", json={"section": section, "value": value})
    assert put("question", "Do night-shift nurses burn out more?").status_code == 200
    assert put("hypothesis", "Night nurses are more exhausted.").json()["kind"] == "project"
    put("hypothesis", "Night nurses are more exhausted because of misalignment.")
    put("rival_hypothesis", "Workload, not the clock, explains it.")
    assert put("design", "anything").status_code == 400, "only question, hypothesis and rivals are written here"
    assert put("hypothesis", "  ").status_code == 400

    st = client.get(f"/api/projects/{pid}/state").json()
    assert st["question"] == "Do night-shift nurses burn out more?"
    assert [v["text"] for v in st["hypothesis"]] == ["Night nurses are more exhausted.", "Night nurses are more exhausted because of misalignment."]
    assert all(v["source"] == "you" for v in st["hypothesis"])
    assert st["rivals"] == ["Workload, not the clock, explains it."]
    assert [(m["role"], m["text"][:8]) for m in st["messages"]] == [("user", "Do night"), ("thoth", "Often, y"), ("thinker", "Ask what")]
    assert st["messages"][2]["thinker"] == {"id": "popper", "name": "Karl Popper"}
    assert "private room chat" not in json.dumps(st["messages"]), "one-to-one rooms are not the main conversation"


def _fill(pid):
    """A project with something in every table that belongs to it."""
    from backend.memory import conversation_store as store
    from backend.research import store as trials
    store.add_turn(pid, "user", "hello")
    store.add_turn(f"{pid}::room::popper", "user", "room")
    store.set_summary(pid, "summary", 1)
    store.add_proposal(pid, "step_offer", {"step": "trial"})
    store.write_section(pid, "hypothesis", "H", "user")
    store.set_thinker_memory(pid, "popper", "stance", True)
    tid = trials.create_trial(pid, "H", [{"id": 1, "claim": "c"}])
    trials.add_paper(tid, {"title": "P1"})
    trials.add_paper(tid, {"title": "P2"})
    from backend.memory import db as _db
    conn = _db.get_connection(_db.DEFAULT_DB_PATH)
    with conn:
        conn.execute("INSERT INTO sys_reviews (review_id, thread_id, hypothesis, protocol_json, status, created_at, updated_at) "
                     "VALUES (?, ?, 'H', '{}', 'planned', 0, 0)", (f"rv_{pid}", pid))
        conn.execute("INSERT INTO sys_review_records (record_id, review_id, meta_json, source, created_at) VALUES (?, ?, '{}', 'x', 0)",
                     (f"rr_{pid}", f"rv_{pid}"))
    return tid


def test_delete_needs_a_confirmation_with_counts_and_leaves_nothing(client):
    keep, gone = _new(client, "keep me"), _new(client, "delete me")
    _fill(keep)
    _fill(gone)

    fp = client.get(f"/api/projects/{gone}/footprint").json()
    assert fp["counts"]["messages"] == 2 and fp["counts"]["papers"] == 2 and fp["counts"]["trials"] == 1
    assert fp["counts"]["systematic_reviews"] == 1 and fp["counts"]["notebook_entries"] == 1
    assert "2 papers" in fp["summary"] and "2 messages" in fp["summary"]

    r = client.delete(f"/api/projects/{gone}")
    assert r.status_code == 409 and r.json()["detail"]["counts"] == fp["counts"], "no confirmation, nothing deleted"
    assert client.get(f"/api/projects/{gone}/footprint").json()["counts"] == fp["counts"]

    assert client.delete(f"/api/projects/{gone}?confirm=true").json()["deleted"] is True
    after = client.get(f"/api/projects/{gone}/footprint").json()["counts"]
    assert not any(after.values()), after
    from backend.memory import db as _db
    conn = _db.get_connection(_db.DEFAULT_DB_PATH)
    leftovers = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE thread_id = ? OR thread_id LIKE ?", (gone, f"{gone}::%")).fetchone()[0]
                 for t in ("conversation_turns", "thread_summaries", "conductor_proposals", "notebook_sections", "thinker_memory", "trials", "sys_reviews")}
    assert not any(leftovers.values()), leftovers
    assert conn.execute("SELECT COUNT(*) FROM trial_papers").fetchone()[0] == 2, "the other project's papers stay"
    assert conn.execute("SELECT COUNT(*) FROM sys_review_records").fetchone()[0] == 1
    assert gone not in _kinds(client) and keep in _kinds(client)
    assert client.get(f"/api/projects/{keep}/footprint").json()["counts"]["messages"] == 2
    assert client.delete(f"/api/projects/{gone}?confirm=true").status_code == 404
