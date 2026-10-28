"""
S26 · The design correction loop, closed (vision §6.5, §8.3; plan Phase 3 B). Builds on S21.

User-seat criteria encoded here:
  - After a design-level FATAL is held and a revised design is chosen, the stale sections can be regenerated and the
    Reviewer run again. A finding that is no longer raised is recorded as resolved by the design version that fixed
    it (never silently dropped); one still raised stays held.
  - Findings raised against an older design cannot drive a revision of the current one: the Reviewer must look again.
  - The chosen revision's rationale names the finding it answers, so the whole loop can be followed afterwards.
"""
from __future__ import annotations

from backend.tests.scenarios.test_s21_design_revision_loop import FATAL, PID, _install, _seed, _write


def _review(client):
    r = client.post("/api/proposal/review", json={"project_id": PID})
    assert r.status_code == 200, r.text
    return client.get(f"/api/proposal?project_id={PID}").json()


def _revise_and_choose(client):
    assert client.post("/api/design/revise", json={"project_id": PID}).status_code == 200
    return client.post("/api/design/choose", json={"project_id": PID, "index": 0}).json()


def test_a_finding_fixed_by_the_new_design_is_recorded_as_resolved(client, monkeypatch):
    _seed()
    _install(monkeypatch, [FATAL])
    _write(client)
    held = client.get(f"/api/proposal?project_id={PID}").json()["review"]["held"]
    assert held[0]["design_version"] == 1, "a held finding remembers the design it was raised against"
    chosen = _revise_and_choose(client)
    assert chosen["version"] == 2

    st = client.get(f"/api/proposal?project_id={PID}").json()
    stale = [k for k, s in st["sections"].items() if s.get("design_stale")]
    assert stale == ["methods"]
    assert client.post(f"/api/proposal/sections/methods/regenerate", json={"project_id": PID, "overwrite": False}).status_code == 200

    _install(monkeypatch, [])  # the Reviewer no longer raises it
    st = _review(client)
    rv = st["review"]
    assert rv["held"] == [] and rv["resolved_held"][0]["id"] == "R1"
    assert rv["resolved_held"][0]["resolved_by_design_version"] == 2 and rv["resolved_held"][0]["design_version"] == 1
    assert not any("study design" in g or "design v" in g for g in st["status"]["gaps"]), st["status"]["gaps"]

    why = client.get(f"/api/projects/{PID}/history?kind=design").json()["versions"][-1]["rationale"]
    assert why["trigger"] == "design_revision" and why["evidence"][0]["ref"]["finding_id"] == "R1"


def test_a_finding_still_raised_stays_held(client, monkeypatch):
    _seed()
    _install(monkeypatch, [FATAL])
    _write(client)
    _revise_and_choose(client)
    client.post(f"/api/proposal/sections/methods/regenerate", json={"project_id": PID, "overwrite": False})
    rv = _review(client)["review"]
    assert [h["fix_in"] for h in rv["held"]] == ["design"] and rv["held"][0]["design_version"] == 2
    assert rv.get("resolved_held") == []


def test_findings_against_an_older_design_cannot_drive_a_revision(client, monkeypatch):
    _seed()
    _install(monkeypatch, [FATAL])
    _write(client)
    _revise_and_choose(client)
    r = client.post("/api/design/revise", json={"project_id": PID})
    assert r.status_code == 409 and "design v1" in r.json()["detail"] and "now v2" in r.json()["detail"]


def test_designer_and_writer_see_appraisal_coverage_and_why_things_changed(client, monkeypatch):
    from backend.memory import conversation_store as nb
    from backend.research import designer, store, writer
    nb.write_section("p26d", "hypothesis", "H one", "user", rationale={"trigger": "initial", "reason": "First statement"})
    nb.write_section("p26d", "hypothesis", "H two", "user", rationale={"trigger": "user_edit", "reason": "Narrowed after the trial"})
    tid = store.create_trial("p26d", "H two", [{"id": 1, "claim": "H two"}], hypothesis_version=2)
    pid = store.add_paper(tid, {"title": "A cohort"})
    store.update_paper(pid, status="done", record_json={"design": {"value": "cohort_prospective"}}, weight=0.42,
                       appraisal_json={"overall": "high", "checklist_name": "Cohort studies",
                                       "items": [{"q": "Were confounding factors identified?", "critical": True, "answer": "no"}]})
    store.update_trial(tid, status="complete", verdict_json={"overall": {"verdict": "contested"},
                                                             "coverage": {"kind": "scan", "note": "A lightweight scan"}})
    lessons = designer.trial_lessons(store.get_trial(tid))
    assert lessons["witnesses"][0]["appraisal"]["overall"] == "high"
    assert "confounding" in lessons["witnesses"][0]["appraisal"]["critical_concerns"][0]
    assert lessons["verdict"]["coverage"]["kind"] == "scan"
    rf = writer.research_file("p26d")
    assert rf["witnesses"][0]["appraisal"]["overall"] == "high" and rf["verdict"]["coverage"]["kind"] == "scan"
    assert [h["reason"] for h in rf["hypothesis_history"]] == ["First statement", "Narrowed after the trial"]
    assert rf["design_history"] == [], "one version (or none) is not a history"
