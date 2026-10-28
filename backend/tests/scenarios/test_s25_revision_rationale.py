"""
S25 · Why each version changed (vision §3.2, §8.1; plan Phase 3 A).

User-seat criteria encoded here:
  - Every version of the question, the hypothesis, a rival or the design keeps why it changed: a reason, what
    triggered it, the evidence or decision behind it, and the version it replaced. A plain edit with no reason says
    "Edited by you"; nothing is invented for the researcher.
  - The first version is marked as the original motivation, together with the question it answered.
  - What was known when the hypothesis changed (the latest trial verdict for the version being replaced) is attached
    as context and shown as such, never as the reason.
  - Accepting Thoth's proposal keeps Thoth's stated reason and the proposal it came from; swapping in a rival says so.
  - A design revision names the peer Reviewer's findings it answers.
  - A second browser sees the same reasons (they are on the server).
"""
from __future__ import annotations

import json

PID = "p25"
H1 = "Night-shift nurses have higher emotional exhaustion than day-shift nurses."
H2 = "Night-shift nurses on rotating schedules have higher emotional exhaustion than day-shift nurses."


def put(client, section, value, rationale=None, pid=PID):
    body = {"section": section, "value": value, **({"rationale": rationale} if rationale is not None else {})}
    r = client.put(f"/api/projects/{pid}/notebook", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def history(client, kind="hypothesis", pid=PID):
    return client.get(f"/api/projects/{pid}/history?kind={kind}").json()


def test_first_version_is_the_original_motivation_with_its_question(client):
    put(client, "question", "Why do night-shift nurses burn out more?")
    put(client, "hypothesis", H1)
    h = history(client)
    v1 = h["versions"][0]
    assert v1["rationale"]["trigger"] == "initial" and v1["rationale"]["reason"] == "First statement of the hypothesis"
    assert h["original"]["question"] == "Why do night-shift nurses burn out more?"
    assert v1["rationale"]["previous_version"] is None
    assert client.get(f"/api/projects/{PID}/history?kind=mode").status_code == 400


def test_an_edit_keeps_its_reason_and_what_was_known_then(client):
    from backend.research import store as trials
    put(client, "hypothesis", H1)
    tid = trials.create_trial(PID, H1, [{"id": 1, "claim": H1}], hypothesis_version=1)
    trials.update_trial(tid, status="complete", verdict_json={"overall": {"verdict": "contested", "reason": "mixed"}})
    put(client, "hypothesis", H2, {"reason": "The trial found the effect only in rotating shifts", "trigger": "user_edit"})
    v2 = history(client)["versions"][1]
    r = v2["rationale"]
    assert r["reason"] == "The trial found the effect only in rotating shifts" and r["trigger"] == "user_edit"
    assert r["previous_version"] == 1 and v2["previous_content"] == H1
    ctx = r["context"]
    assert ctx and ctx[0]["kind"] == "trial_verdict" and ctx[0]["ref"]["trial_id"] == tid and "contested" in ctx[0]["label"]
    assert not r["evidence"], "context is attached, but never presented as the evidence the researcher gave"


def test_a_plain_edit_says_edited_by_you_and_old_clients_still_work(client):
    put(client, "hypothesis", H1)
    out = put(client, "hypothesis", H2)  # no rationale, as before this change
    assert out["version"] == 2
    r = history(client)["versions"][1]["rationale"]
    assert r["reason"] == "Edited by you" and r["trigger"] == "user_edit" and r["source"] == "you"


def test_accepting_thoths_proposal_keeps_its_reason_and_the_proposal(client):
    from backend.memory import conversation_store as nb
    put(client, "hypothesis", H1)
    pid = nb.add_proposal(PID, "notebook_proposal", {"section": "hypothesis", "value": H2, "why": "Rotating schedules are where the misalignment is largest"})
    assert client.post(f"/api/chat/proposals/{pid}", json={"action": "accept"}).status_code == 200
    r = history(client)["versions"][1]["rationale"]
    assert r["trigger"] == "thoth_proposal" and r["source"] == "thoth"
    assert r["reason"].startswith("Rotating schedules") and r["decision_ref"] == {"kind": "conductor_proposal", "id": pid}


def test_swapping_in_a_rival_is_recorded_on_both_sides(client):
    put(client, "hypothesis", H1)
    put(client, "rival_hypothesis", H2)
    assert client.post(f"/api/projects/{PID}/rivals/swap", json={"text": H2}).status_code == 200
    hyp = history(client)["versions"][-1]["rationale"]
    assert hyp["trigger"] == "rival_swap" and "replaced v1" in hyp["reason"] and hyp["decision_ref"]["kind"] == "rival"
    rival = history(client, "rival_hypothesis")["versions"][-1]["rationale"]
    assert rival["trigger"] == "rival_swap" and "Parked" in rival["reason"]


def test_a_design_revision_names_the_findings_it_answers(client):
    from backend.memory import conversation_store as nb
    from backend.research import proposal
    nb.write_section(PID, "hypothesis", H1, "user")
    meta = proposal.get_meta(PID)
    meta["review"] = {"at": 123.0, "held": [{"id": "R1", "fix_in": "design", "problem": "Biweekly recall windows cannot show precedence."}]}
    proposal.save_meta(PID, meta, "thoth")
    design = {"name": "Cohort with a diary", "revision_of": "Prospective cohort", "addresses": ["R1"],
              "changes": [{"finding_id": "R1", "change": "Added a 14-day daily diary."}],
              "unresolved": [{"finding_id": "R1", "why": "Misalignment is still self-reported."}]}
    nb.write_section(PID, "design_candidates", json.dumps({"designs": [design], "why": "Revised to answer the peer Reviewer"}), "thoth")
    chosen = client.post("/api/design/choose", json={"project_id": PID, "index": 0}).json()
    r = history(client, "design")["versions"][-1]["rationale"]
    assert r["trigger"] == "design_revision" and r["reason"] == "Added a 14-day daily diary."
    assert r["evidence"][0]["ref"]["finding_id"] == "R1" and "Biweekly recall" in r["evidence"][0]["label"]
    assert "Still open" in r["context"][0]["label"]
    got = client.get(f"/api/design?project_id={PID}").json()["chosen"]
    assert got["version"] == chosen["version"] and got["rationale"]["trigger"] == "design_revision"


def test_a_second_browser_sees_the_same_reasons(client):
    put(client, "hypothesis", H1)
    put(client, "hypothesis", H2, {"reason": "Narrowed to rotating schedules", "source": "you"})
    st = client.get(f"/api/projects/{PID}/state").json()
    assert [v["reason"] for v in st["hypothesis"]] == ["First statement of the hypothesis", "Narrowed to rotating schedules"]
    assert [v["trigger"] for v in st["hypothesis"]] == ["initial", "user_edit"]


def test_rationale_is_cleaned():
    from backend.memory.rationale import clean
    r = clean({"reason": "x" * 5000, "trigger": "made_up", "evidence": [{"kind": "nonsense"}, {"kind": "trial_verdict", "ref": {"a": 1}}] * 8,
               "decision_ref": "not a dict"})
    assert len(r["reason"]) == 1000 and r["trigger"] == "unknown" and r["decision_ref"] is None
    assert len(r["evidence"]) == 8 and all(e["kind"] == "trial_verdict" for e in r["evidence"])
    assert clean(None)["evidence"] == [] and clean(None)["trigger"] == "unknown"
