"""
S21 · A design-level FATAL goes back to the Design tab; design assumptions must be sourced
(docs/features/07-study-design.md, 08-writing.md).

User-seat criteria encoded here:
  - The peer Reviewer says where each problem must be fixed: in the writing, in the study design, or with more
    evidence. Only writing problems go to the Writer's revision rounds; a design FATAL is held, and the proposal
    status says it needs a change to the study design (rewording the Methods cannot fix it).
  - "Revise the design" sends the held findings, the chosen design, the resources and the trial's lessons to the
    Designer, which returns one revised design (same guardrails) saying what changed for each finding and what it
    could not resolve. Choosing it makes design v2.
  - Proposal sections written from design v1 are then marked stale ("written for design v1; the design is now v2").
  - A design that appeals to unnamed studies, or states an effect size with no witness and no "assumed", is flagged.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage

from backend.tests.scenarios.conftest import read_sse
from backend.tests.scenarios.test_s16_trial_neutral_court import RoleModel

PID = "p21"
HYP = "Night-shift nurses have higher emotional exhaustion than day-shift nurses because of circadian misalignment."
DESIGN = {"name": "Prospective cohort, 4 waves", "design_type": "cohort_prospective", "summary": "Biweekly surveys for 8 weeks.",
          "can_conclude": "Temporal ordering of misalignment and exhaustion.", "cannot_conclude": "causation",
          "tests_subclaims": [1], "measures": [], "sampling": "60 night, 120 day nurses", "sample_size": "needs power analysis",
          "threats": [], "feasibility": "feasible_with_changes"}
FATAL = {"severity": "FATAL", "section": "Methods", "passage": "This study will survey nurses every two weeks",
         "problem": "Biweekly recall windows cannot establish that misalignment precedes exhaustion.",
         "fix": "Add daily measures so the lag is days, not weeks.", "fix_in": "design"}
WORDING = {"severity": "FATAL", "section": "Background", "passage": "Shift work is bad for nurses",
           "problem": "The background overstates the evidence.", "fix": "Say the evidence is cross-sectional.", "fix_in": "writing"}
REVISED = {"design": {**DESIGN, "name": "Cohort with a 14-day daily diary", "summary": "Biweekly surveys plus a 14-day daily sleep and exhaustion diary.",
                      "sample_size": "needs power analysis with the within-person lag as input",
                      "sampling": "Simulation studies suggest 80-100 completers are enough."},
           "changes": [{"finding_id": "R1", "change": "Added a 14-day daily diary so the lag is one day."}],
           "unresolved": [{"finding_id": "R1", "why": "Subjective misalignment is still a proxy."}]}
OUTLINE = [{"key": "background", "title": "Background", "purpose": "p"}, {"key": "methods", "title": "Methods", "purpose": "p"}]


def _seed():
    from backend.memory import conversation_store as nb
    nb.write_section(PID, "hypothesis", HYP, "user")
    nb.write_section(PID, "resources", json.dumps({"time": "4 months", "budget": "none"}), "user")
    nb.write_section(PID, "design", json.dumps(DESIGN), "user")


def _install(monkeypatch, weaknesses):
    import backend.research.llm as rl
    model = RoleModel({
        "Thoth's Writer": {"markdown": "## X\n\nThis study will survey nurses every two weeks. Shift work is bad for nurses."},
        "Thoth's Reviewer": {"summary": "s", "weaknesses": weaknesses},
        "revise the chosen design": REVISED,
    })
    monkeypatch.setattr(rl, "_llm", lambda role: model)
    return model


def _write(client):
    client.put(f"/api/projects/{PID}/mode", json={"mode": "autopilot"})
    with client.stream("POST", "/api/proposal/write", json={"project_id": PID, "approve": True, "outline": OUTLINE}) as r:
        return read_sse(r, max_events=100, max_seconds=20)


def test_a_design_fatal_is_held_for_the_design_tab_not_rewritten(client, monkeypatch):
    _seed()
    model = _install(monkeypatch, [FATAL, WORDING])
    _write(client)
    revisions = [h for s, h in model.calls if "Thoth's Writer" in s and "REVISION" in s]
    assert revisions and all("cannot establish that misalignment precedes" not in h for h in revisions), \
        "only the writing FATAL goes to the Writer"
    st = client.get(f"/api/proposal?project_id={PID}").json()
    held = st["review"]["held"]
    assert any(h["fix_in"] == "design" and "Biweekly recall" in h["problem"] for h in held)
    assert any("study design" in g for g in st["status"]["gaps"])


def test_revise_design_sends_the_findings_and_returns_a_guarded_revision(client, monkeypatch):
    _seed()
    model = _install(monkeypatch, [FATAL])
    _write(client)
    out = client.post("/api/design/revise", json={"project_id": PID}).json()
    human = [h for s, h in model.calls if "revise the chosen design" in s][-1]
    assert "Biweekly recall windows" in human and "Prospective cohort, 4 waves" in human and "4 months" in human
    rev = out["designs"][0]
    assert rev["revision_of"] == "Prospective cohort, 4 waves" and rev["addresses"] == ["R1"]
    assert rev["changes"][0]["change"].startswith("Added a 14-day daily diary") and rev["unresolved"][0]["why"]
    assert any("unnamed studies" in n for n in out["guardrail_notes"]), "the sourcing check applies to revisions too"
    assert client.post("/api/design/revise", json={"project_id": "nobody"}).status_code == 400

    chosen = client.post("/api/design/choose", json={"project_id": PID, "index": 0}).json()
    assert chosen["version"] == 2
    st = client.get(f"/api/proposal?project_id={PID}").json()["status"]
    assert any("written for design v1; the design is now v2" in g for g in st["gaps"])


def test_unnamed_studies_and_unsourced_effect_sizes_are_flagged(client):
    from backend.research.designer import enforce
    lessons = {"available": True, "witnesses": [{"id": "W3", "title": "T", "measures": []}]}
    raw = {"designs": [{**DESIGN, "name": "A", "sampling": "Simulation studies suggest 80-100 completers are enough.",
                        "sample_size": "120 nurses, assuming f² = 0.05 from W3", "summary": "Detects an effect of d = 0.4."},
                       {**DESIGN, "name": "B", "sampling": "Prior work (W3) reported 30% attrition.", "summary": "Assumed d = 0.3 (to be checked)."}]}
    out = enforce(raw, lessons, [1])
    a, b = out["designs"]
    assert any("Simulation studies suggest" in u for u in a["unsourced"])
    assert any("d = 0.4" in u for u in a["unsourced"])
    assert not any("f² = 0.05" in u for u in a["unsourced"]), "cites a witness and says it's assumed"
    assert b["unsourced"] == [], "a witness id or an explicit assumption is enough"
    assert sum("unnamed studies" in n or "effect size" in n for n in out["guardrail_notes"]) >= 2


def test_a_revision_reads_witness_ids_against_the_trial_the_design_came_from(client):
    """Ids are per trial: a newer trial must not re-number the chosen design's witnesses (seen live)."""
    from backend.research import designer, store
    old = store.create_trial(PID, HYP, [{"id": 1, "claim": "c"}])
    for t in ("A paper", "MBI in ICU nurses"):
        store.update_paper(store.add_paper(old, {"title": t}), status="done", record_json={}, row_json={})
    store.update_trial(old, status="complete")
    new = store.create_trial(PID, HYP, [{"id": 1, "claim": "c"}])
    store.update_paper(store.add_paper(new, {"title": "Unrelated"}), status="done", record_json={}, row_json={})
    store.update_trial(new, status="complete")
    old_design = {**DESIGN, "measures": [{"construct": "exhaustion", "instrument": "MBI", "source_witness_id": "W2", "source_title": "MBI in ICU nurses"}]}
    assert designer.trial_for_design(PID, old_design)["trial_id"] == old, "inferred from the titles its measures cite"
    assert designer.trial_for_design(PID, {**DESIGN, "trial_id": new})["trial_id"] == new, "recorded trial wins"
    assert designer.trial_for_design(PID, DESIGN)["trial_id"] == new, "nothing to go on: the latest finished trial"


def test_sections_written_before_versions_were_recorded_are_compared_by_time(client):
    from backend.memory import conversation_store as nb
    from backend.research import proposal
    nb.write_section("p21t", "design", json.dumps(DESIGN), "user")
    old = {"key": "methods", "written_at": 1.0}  # an older section: no design_version recorded
    assert proposal.design_stale("p21t", old) == "", "design v1 only: nothing to be stale against"
    nb.write_section("p21t", "design", json.dumps({**DESIGN, "name": "v2"}), "user")
    assert proposal.design_stale("p21t", old) == "written before design v2 was chosen"
    assert proposal.design_stale("p21t", {"key": "background", "written_at": 1.0}) == "", "background doesn't restate the design"
    assert proposal.design_stale("p21t", {"key": "methods", "design_version": 2}) == ""

