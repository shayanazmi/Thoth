"""
S24 · Study-quality appraisal and citation following in the trial (vision §4.2, §5.6, §6.1; plan Phase 2 A and C).

User-seat criteria encoded here:
  - Every readable paper is appraised with the checklist for its design, by an Appraiser that never sees the
    hypothesis. Item answers carry evidence and locators; abstract-only text cannot answer items that need the
    full text. The researcher sees the checklist, the answers and how the weight was reached.
  - The witness weight is design × access × appraisal. A paper the Appraiser couldn't appraise keeps the old
    weight and says so; it is never punished for a model outage.
  - When every witness supporting a sub-claim is at high risk of bias, the verdict cannot claim high or moderate
    certainty for it.
  - Papers citing, or cited by, the strongest witnesses are checked for prior work (abstract level only). The
    Judge names the closest prior work by id, and cannot call the idea likely novel if that check didn't run.
    Rejudging an older trial (before citation following existed) says so and changes nothing else.
"""
from __future__ import annotations

import json

from backend.tests.scenarios.conftest import read_sse
from backend.tests.scenarios.test_s16_trial_neutral_court import (ANSWERS, HYP, RECORD, ROW, RoleModel, SUBS, VERDICT,
                                                                   _install, _stub_library)

FULL = {"aim": {"value": "compare shifts", "provenance": "from_full_text"},
        "design": {"value": "cohort_prospective", "provenance": "from_full_text"},
        "sample_size": {"value": "412 nurses", "provenance": "from_full_text"},
        "results": [{"finding": "night nurses higher EE", "numbers": "p<.01", "locator": "Table 2", "provenance": "from_full_text"}]}


def _appraiser(fail_confounding=False):
    ans = {f"k{i}": ("yes", "Methods") for i in range(1, 12)}
    if fail_confounding:
        ans["k5"] = ("no", "Methods, para 4")
    return {"items": [{"id": k, "answer": a, "evidence": "quote", "locator": loc} for k, (a, loc) in ans.items()],
            "core": {"methods_fit": {"answer": "yes", "why": "w", "locator": "Methods"},
                     "conclusions_beyond_evidence": [{"claim": "Night work causes burnout", "why": "observational", "locator": "Discussion"}]}}


def _plan(client, pid="p24"):
    return client.post("/api/trial/plan", json={"project_id": pid, "hypothesis": HYP}).json()


def _run(client, trial_id):
    with client.stream("POST", f"/api/trial/{trial_id}/run", json={"approve": True}) as r:
        return read_sse(r, max_events=300, max_seconds=20)


def test_full_text_cohort_is_appraised_blind_and_weighted(client, monkeypatch):
    model = _install(monkeypatch, {**ANSWERS, "Thoth's Reader": FULL, "Thoth's Appraiser": _appraiser(fail_confounding=True)})
    _stub_library(monkeypatch, access="full_text", text="FULL TEXT " * 400)
    plan = _plan(client)
    events = _run(client, plan["trial_id"])
    kinds = [e["event"] for e in events]
    assert kinds.count("paper_appraised") == 3
    assert kinds.index("paper_appraised") < kinds.index("matrix_row")

    appraiser_calls = [h for s, h in model.calls if "Thoth's Appraiser" in s]
    assert len(appraiser_calls) == 3 and all("circadian misalignment" not in h for h in appraiser_calls), "hypothesis-blind"
    assert all("<checklist>" in h and '"k5"' in h and "<untrusted>" in h for h in appraiser_calls)

    paper = client.get(f"/api/trial/{plan['trial_id']}").json()["papers"][0]
    a = paper["appraisal"]
    assert a["checklist_id"] == "jbi_cohort" and a["adapted_from"].startswith("JBI")
    assert a["overall"] == "high" and "confounding" in a["overall_why"]
    assert a["weight_basis"] == {"method": "v2", "design_tier": 0.7, "access_factor": 1.0, "appraisal_factor": 0.6, "appraisal": "high"}
    assert paper["weight"] == round(0.7 * 1.0 * 0.6, 2)
    row = next(e["payload"] for e in events if e["event"] == "matrix_row")
    assert row["weight"] == paper["weight"] and row["weight_basis"]["appraisal_factor"] == 0.6

    judge_human = [h for s, h in model.calls if "Thoth's Judge" in s][-1]
    matrix = json.loads(judge_human.split("<matrix>")[1].split("</matrix>")[0])
    assert matrix[0]["appraisal"]["overall"] == "high"
    assert any("confounding" in c for c in matrix[0]["appraisal"]["critical_concerns"])
    assert matrix[0]["appraisal"]["beyond_evidence"] == ["Night work causes burnout"]


def test_abstract_only_paper_cannot_answer_full_text_items(client, monkeypatch):
    _install(monkeypatch, {**ANSWERS, "Thoth's Appraiser": {"items": [{"id": f"x{i}", "answer": "yes", "locator": "Abstract"} for i in range(1, 9)]}})
    _stub_library(monkeypatch, access="abstract_only")
    plan = _plan(client)
    _run(client, plan["trial_id"])
    a = client.get(f"/api/trial/{plan['trial_id']}").json()["papers"][0]["appraisal"]
    assert a["checklist_id"] == "jbi_cross_sectional"
    assert {i["answer"] for i in a["items"]} == {"not_assessable"} and a["overall"] == "not_assessable"


def test_appraiser_outage_keeps_the_old_weight(client, monkeypatch):
    _install(monkeypatch, ANSWERS)  # no Appraiser answer: the model returns {}
    _stub_library(monkeypatch, access="abstract_only")
    plan = _plan(client)
    _run(client, plan["trial_id"])
    p = client.get(f"/api/trial/{plan['trial_id']}").json()["papers"][0]
    assert p["status"] == "done" and p["appraisal"]["overall"] == "not_appraised"
    assert p["weight"] == round(0.45 * 0.55, 2), "never punished for a model outage"


def test_high_risk_support_lowers_certainty_but_older_appraisals_do_not():
    from backend.research import judge
    subs = SUBS["subclaims"]
    raw = {"per_subclaim": [{"id": 1, "verdict": "supported_within_limits", "certainty": "high", "witness_ids_for": ["W1", "W2"]},
                            {"id": 2, "verdict": "supported_within_limits", "certainty": "moderate", "witness_ids_for": ["W3"]}],
           "overall": {"verdict": "supported_within_limits"}, "originality": {"label": "partial_overlap"}}
    papers = [{"meta": {"title": "a"}, "access": "full_text", "appraisal": {"overall": "high"}},
              {"meta": {"title": "b"}, "access": "full_text", "appraisal": {"overall": "not_assessable"}},
              {"meta": {"title": "c"}, "access": "full_text", "appraisal": {}}]
    v = judge.enforce(raw, papers, {"ran": True, "citation": {"ran": True, "papers": []}}, subs)
    assert v["per_subclaim"][0]["certainty"] == "low" and "risk of bias" in v["per_subclaim"][0]["rated_down_for"][-1]
    assert v["per_subclaim"][1]["certainty"] == "moderate", "an older-method witness doesn't trigger the rule"
    assert v["appraisal_summary"] == {"high": 1, "not_assessable": 1, "older method": 1}


def test_citation_neighbours_reach_the_judge_and_name_prior_work(client, monkeypatch):
    from backend.research import citations

    async def backward(client_, meta, limit, query=""):
        if meta["doi"] != "10.1/0":
            return [], {"provider": "OpenAlex", "error": None}
        return ([{"title": "Paper 1", "doi": "10.1/1", "abstract": "dup of a witness"},
                 {"title": "Circadian disruption and burnout in ICU nurses", "doi": "10.5/x", "abstract": "prior", "year": 2015,
                  "openalex_id": "W77"}], {"provider": "OpenAlex", "error": None})

    async def forward(client_, meta, limit, query=""):
        return [], {"provider": "OpenAlex", "error": None}

    monkeypatch.setattr(citations, "backward", backward)
    monkeypatch.setattr(citations, "forward", forward)
    verdict = {**VERDICT, "originality": {"label": "partial_overlap", "reason": "r", "closest_prior_work_ids": ["C1", "C9", "W2"]}}
    model = _install(monkeypatch, {**ANSWERS, "Thoth's Judge": verdict})
    _stub_library(monkeypatch, access="abstract_only")
    plan = _plan(client)
    events = _run(client, plan["trial_id"])
    cn = next(e["payload"] for e in events if e["event"] == "citation_neighbours")
    assert cn["ran"] is True and cn["papers"] == 1, "a paper already in the trial is not a neighbour"
    trial = client.get(f"/api/trial/{plan['trial_id']}").json()
    c1 = trial["adjacent"]["citation"]["papers"][0]
    assert c1["id"] == "C1" and c1["title"].startswith("Circadian") and c1["relation"].startswith("cited by W")
    judge_human = [h for s, h in model.calls if "Thoth's Judge" in s][-1]
    assert "<citation_neighbours>" in judge_human and "Circadian disruption" in judge_human
    assert "<evidence_base>" in judge_human and "lightweight scan" in judge_human
    v = trial["verdict"]
    assert v["originality"]["closest_prior_work_ids"] == ["C1", "W2"], "unknown ids are dropped"
    assert v["coverage"]["kind"] == "scan"


def test_likely_novel_needs_the_citation_check_and_older_trials_are_only_noted():
    from backend.research import judge
    raw = {"overall": {"verdict": "contested"}, "originality": {"label": "likely_novel"}}
    papers = [{"meta": {"title": "a"}, "access": "full_text"}]
    subs = [{"id": 1, "claim": "c"}]
    v = judge.enforce(raw, papers, {"ran": True, "citation": {"ran": False, "papers": []}}, subs)
    assert v["originality"]["label"] == "insufficiently_assessed" and any("citation search did not run" in n for n in v["guardrail_notes"])
    v = judge.enforce(raw, papers, {"ran": True}, subs)
    assert v["originality"]["label"] == "likely_novel", "an older trial keeps its label…"
    assert any("not part of this (older) run" in n for n in v["guardrail_notes"]), "…and says why"


def test_remap_copies_the_appraisal(client, monkeypatch):
    _install(monkeypatch, {**ANSWERS, "Thoth's Reader": FULL, "Thoth's Appraiser": _appraiser()})
    _stub_library(monkeypatch, access="full_text", text="FULL TEXT " * 400)
    from backend.memory import conversation_store as nb
    nb.write_section("p24r", "hypothesis", HYP, "user")
    plan = _plan(client, "p24r")
    _run(client, plan["trial_id"])
    nb.write_section("p24r", "hypothesis", "Night-shift nurses sleep less than day-shift nurses.", "user")
    remap = client.post(f"/api/trial/{plan['trial_id']}/remap", json={}).json()
    copied = client.get(f"/api/trial/{remap['trial_id']}").json()["papers"][0]
    assert copied["appraisal"]["checklist_id"] == "jbi_cohort" and copied["appraisal"]["overall"] == "low"


def test_untitled_neighbours_are_deduplicated_too(client, monkeypatch):
    from backend.research import citations

    async def backward(client_, meta, limit, query=""):
        return ([{"title": "", "doi": "10.8/x", "abstract": "a"}, {"title": "", "doi": "10.8/x", "abstract": "a"},
                 {"title": "Named prior work", "doi": "10.8/y", "abstract": "b"}], {"provider": "OpenAlex", "error": None})

    async def forward(client_, meta, limit, query=""):
        return [], {"provider": "OpenAlex", "error": None}

    monkeypatch.setattr(citations, "backward", backward)
    monkeypatch.setattr(citations, "forward", forward)
    _install(monkeypatch, ANSWERS)
    _stub_library(monkeypatch, access="abstract_only")
    plan = _plan(client, "p24u")
    _run(client, plan["trial_id"])
    papers = client.get(f"/api/trial/{plan['trial_id']}").json()["adjacent"]["citation"]["papers"]
    assert sorted(p["doi"] for p in papers) == ["10.8/x", "10.8/y"], "the same DOI appears once"
