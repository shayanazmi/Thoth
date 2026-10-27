"""
S17 · Study design (docs/features/07-study-design.md).

User-seat criteria encoded here:
  - Designs need the researcher's resources first, and are checked against them.
  - Designs are built on the trial: the Designer is shown the trial's witnesses as W1.. (the Judge's numbering).
  - A measure must cite a real witness or is marked "new: needs validation".
  - A non-causal design (e.g. cross-sectional) cannot claim causation; a sample size must state assumptions.
  - Choosing a design writes a versioned Design section; the researcher's notes are kept.
  - With no model reachable, no designs are invented.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage


HYP = "Night-shift nurses have higher emotional exhaustion than day-shift nurses because of circadian misalignment."
RES = {"time": "3 months", "population_access": "one hospital, ~60 night nurses", "budget": "none", "skills": "basic SPSS"}

DESIGNS = {"designs": [
    {"name": "Cross-sectional survey", "design_type": "cross_sectional", "summary": "Survey both shifts once.",
     "can_conclude": "Night shifts cause higher exhaustion.", "cannot_conclude": "",
     "tests_subclaims": [1, 9], "measures": [{"construct": "exhaustion", "instrument": "MBI-EE", "source_witness_id": "W1"},
                                             {"construct": "misalignment", "instrument": "MCTQ", "source_witness_id": "W7"}],
     "sampling": "all nurses", "sample_size": "120 nurses", "threats": [{"validity": "internal", "threat": "selection", "mitigation": "adjust"}],
     "feasibility": "feasible", "blockers": []},
    {"name": "Prospective cohort", "design_type": "cohort_prospective", "summary": "Follow new night starters.",
     "can_conclude": "Whether exhaustion rises after starting nights (temporal ordering).", "cannot_conclude": "",
     "tests_subclaims": [1], "measures": [], "sampling": "new starters", "sample_size": "needs power analysis with expected change",
     "threats": [], "feasibility": "not_feasible", "blockers": ["3 months is too short"]}],
    "recommended": "Something else", "why": "simplest"}


class Model:
    def __init__(self):
        self.calls = []

    def bind_tools(self, *a, **k):
        return self

    def invoke(self, messages, **kw):
        self.calls.append((messages[0].content, messages[-1].content))
        return AIMessage(content=json.dumps(DESIGNS))


def _seed_trial(thread):
    from backend.research import store
    tid = store.create_trial(thread, HYP, [{"id": 1, "claim": "Night nurses more exhausted."}])
    pid = store.add_paper(tid, {"title": "MBI in ICU nurses", "year": 2021})
    store.update_paper(pid, status="done", access="full_text", weight=0.45,
                       record_json={"design": {"value": "cross_sectional"}, "measures": [{"construct": "exhaustion", "instrument": "MBI-EE"}]},
                       row_json={"boundary_conditions": ["ICU only"]})
    store.update_trial(tid, status="complete", verdict_json={"overall": {"verdict": "insufficient_evidence"}})
    return tid


def test_designs_need_resources_first(client):
    r = client.post("/api/design/propose", json={"project_id": "p17a", "hypothesis": HYP})
    assert r.status_code == 400 and "resources" in r.json()["detail"]


def test_designs_are_grounded_and_guarded(client, monkeypatch):
    import backend.research.llm as rl
    model = Model()
    monkeypatch.setattr(rl, "_llm", lambda role: model)
    _seed_trial("p17b")
    client.post("/api/design/resources", json={"project_id": "p17b", "resources": RES})
    out = client.post("/api/design/propose", json={"project_id": "p17b", "hypothesis": HYP}).json()

    human = model.calls[0][1]
    assert '"id": "W1"' in human and "MBI in ICU nurses" in human and "one hospital" in human
    assert out["lessons_used"] is True

    cross, cohort = out["designs"]
    assert cross["can_conclude"].startswith("Associations") and "causation" in cross["cannot_conclude"]
    assert cross["measures"][0]["source_witness_id"] == "W1" and cross["measures"][0]["source_title"] == "MBI in ICU nurses"
    assert cross["measures"][1]["source_witness_id"] == "new" and cross["measures"][1]["note"] == "needs validation"
    assert cross["measures"][0]["source_match"] == "used", "W1 reported MBI-EE itself"

    assert "power analysis" in cross["sample_size"]
    assert cross["tests_subclaims"] == [1], "sub-claim ids that don't exist are dropped"
    assert cohort["can_conclude"].startswith("Whether exhaustion rises"), "a causal-capable design keeps its claim"
    assert out["recommended"] == "Cross-sectional survey", "the recommendation must be one of the candidates"
    assert len(out["guardrail_notes"]) == 2


def test_choosing_writes_a_versioned_design_section(client, monkeypatch):
    import backend.research.llm as rl
    monkeypatch.setattr(rl, "_llm", lambda role: Model())
    client.post("/api/design/resources", json={"project_id": "p17c", "resources": RES})
    client.post("/api/design/propose", json={"project_id": "p17c", "hypothesis": HYP})
    first = client.post("/api/design/choose", json={"project_id": "p17c", "index": 0, "notes": ""}).json()
    second = client.post("/api/design/choose", json={"project_id": "p17c", "index": 1, "notes": "Add a 6-month follow-up."}).json()
    assert first["version"] == 1 and first["author"] == "thoth_accepted"
    assert second["version"] == 2 and second["author"] == "user" and second["researcher_notes"] == "Add a 6-month follow-up."
    state = client.get("/api/design?project_id=p17c").json()
    assert state["chosen"]["name"] == "Prospective cohort" and state["resources"]["time"] == "3 months"
    assert client.post("/api/design/choose", json={"project_id": "p17c", "index": 7}).status_code == 400


def test_no_model_means_no_invented_designs(client):
    client.post("/api/design/resources", json={"project_id": "p17d", "resources": RES})
    out = client.post("/api/design/propose", json={"project_id": "p17d", "hypothesis": HYP}).json()
    assert out["degraded"] is True and out["designs"] == []
    assert client.get("/api/design?project_id=p17d").json()["candidates"] is None


def test_a_cited_witness_that_never_used_the_instrument_is_only_related(client):
    from backend.research.designer import enforce
    lessons = {"available": True, "witnesses": [{"id": "W1", "title": "T", "measures": [{"construct": "burnout", "instrument": "Copenhagen Burnout Inventory"}]}]}
    raw = {"designs": [{"name": "D", "design_type": "rct", "measures": [{"construct": "exhaustion", "instrument": "MBI-EE (Maslach)", "source_witness_id": "W1"}]}]}
    m = enforce(raw, lessons, [1])["designs"][0]["measures"][0]
    assert m["source_witness_id"] == "W1" and m["source_match"] == "related"
