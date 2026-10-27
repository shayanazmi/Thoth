"""
S15 · Systematic review (docs/features/05-literature.md tier 3).

User-seat criteria encoded here:
  - A protocol is drafted and edited before anything runs; the review runs only on approval, and only once.
  - PRISMA counts always equal the decision log, including after the researcher overrides a decision.
  - Human-in-the-loop pauses at each screening stage until every decision is confirmed.
  - Auto applies decisions and queues low-confidence ones for audit, without pausing.
  - Every exclusion carries one protocol criterion as its reason; the researcher's overrides need one too.
  - The Screener is shown the protocol, never the hypothesis or its expected result.
  - If the Screener can't be reached, records stay unscreened and the review says so.
  - Included studies become rows in a linked trial with a verdict.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage

from backend.tests.scenarios.conftest import read_sse as _read_sse

HYP = "Night-shift nurses have higher emotional exhaustion than day-shift nurses because of circadian misalignment."
PROTOCOL = {"framework": "PEO", "eligibility": {"population": "hospital nurses", "exposure": "night shifts", "comparison": "day shifts",
            "outcomes": "burnout or emotional exhaustion", "designs": "quantitative", "dates": "2000-2026", "languages": "English"},
            "search": {"openalex": "night shift nurses burnout", "europepmc": "night shift AND nurses AND burnout"}}


def screener_answer(human: str) -> dict:
    """Decide by title keyword: 'Excluded' → exclude (outcomes), 'Unsure' → low-confidence include, else include."""
    ids = re.findall(r'record_id="([^"]+)"', human)
    titles = re.findall(r"Title: (.*)", human) or [""] * len(ids)
    full = "<stage>full_text</stage>" in human
    out = []
    for rid, title in zip(ids, titles + [""] * len(ids)):
        if "Excluded" in title:
            out.append({"record_id": rid, "decision": "exclude", "exclusion_reason": "outcomes", "confidence": 0.9})
        elif "NoReason" in title:
            out.append({"record_id": rid, "decision": "exclude", "exclusion_reason": "", "confidence": 0.9})
        elif "Unsure" in title:
            out.append({"record_id": rid, "decision": "include", "confidence": 0.5})
        else:
            out.append({"record_id": rid, "decision": "include", "confidence": 0.95})
    if full:  # full-text stage gives one record without a Title line
        out = [{"record_id": ids[0], "decision": "include", "confidence": 0.9}]
    return {"decisions": out}


class Model:
    def __init__(self):
        self.calls = []

    def bind_tools(self, *a, **k):
        return self

    def invoke(self, messages, **kw):
        system, human = messages[0].content, messages[-1].content
        self.calls.append((system, human))
        if "Draft a systematic-review protocol" in system:
            return AIMessage(content=json.dumps(PROTOCOL))
        if "Split the hypothesis" in system:
            return AIMessage(content=json.dumps({"subclaims": [{"id": 1, "claim": "Night nurses more exhausted."}]}))
        if "Thoth's Screener" in system:
            return AIMessage(content=json.dumps(screener_answer(human)))
        if "Thoth's Reader" in system:
            return AIMessage(content=json.dumps({"design": {"value": "cross_sectional", "provenance": "from_full_text"},
                                                 "results": [{"finding": "f", "numbers": "", "locator": "Table 1", "provenance": "from_full_text"}]}))
        if "Thoth's Analyst" in system:
            return AIMessage(content=json.dumps({"per_subclaim": [{"id": 1, "direction": "convergent", "locator": "Table 1"}]}))
        if "Thoth's Judge" in system:
            return AIMessage(content=json.dumps({"overall": {"verdict": "supported_within_limits", "reason": "r"},
                                                 "per_subclaim": [{"id": 1, "verdict": "supported_within_limits"}]}))
        return AIMessage(content="{}")


TITLES = ["Night shift and burnout A", "Excluded sleep only B", "Unsure rota C", "Night shift and burnout D"]


def _stub(monkeypatch, with_model=True):
    import backend.research.librarian as L
    import backend.research.llm as rl
    model = Model()
    if with_model:
        monkeypatch.setattr(rl, "_llm", lambda role: model)

    async def oa(client, q, limit):
        return [{"title": t, "year": 2020, "doi": f"10.1/{i}", "abstract": f"abstract {t}", "found_via": "OpenAlex"} for i, t in enumerate(TITLES)]

    async def ep(client, q, limit):
        # one duplicate of the first OpenAlex record, by DOI
        return [{"title": TITLES[0], "year": 2020, "doi": "10.1/0", "abstract": "dup", "found_via": "Europe PMC"},
                {"title": "Another Europe paper E", "year": 2021, "doi": "10.2/9", "abstract": "abs", "found_via": "Europe PMC"},
                {"title": "Third F", "year": 2022, "doi": "10.2/10", "abstract": "abs", "found_via": "Europe PMC"}]

    async def full_text(meta):
        return ("FULL TEXT " * 400, "full_text", "test") if "D" not in meta["title"][-1:] else ("abs", "abstract_only", "test")

    monkeypatch.setattr(L, "search_openalex", oa)
    monkeypatch.setattr(L, "search_europepmc", ep)
    monkeypatch.setattr(L, "full_text", full_text)
    return model


def _protocol(client):
    return client.post("/api/review/protocol", json={"project_id": "p15", "hypothesis": HYP}).json()


def _run(client, rid, mode="copilot", approve=True, edits=None):
    with client.stream("POST", f"/api/review/{rid}/run", json={"approve": approve, "mode": mode, "protocol": edits or {}}) as r:
        if r.status_code != 200:
            return r.status_code, []
        return 200, _read_sse(r, max_events=300, max_seconds=20)


def _continue(client, rid):
    with client.stream("POST", f"/api/review/{rid}/continue", json={}) as r:
        return _read_sse(r, max_events=300, max_seconds=20)


def _counts_match_log(client, rid):
    st = client.get(f"/api/review/{rid}").json()
    c, recs = st["counts"], st["records"]
    assert c["identified"] == len(recs)
    assert c["duplicates_removed"] == sum(1 for r in recs if r["dup_of"])
    assert c["screened"] == c["identified"] - c["duplicates_removed"]
    assert c["excluded_title_abstract"] == sum(1 for r in recs if not r["dup_of"] and (r["ta"] or {}).get("decision") == "exclude")
    assert c["sought_for_retrieval"] == sum(1 for r in recs if not r["dup_of"] and (r["ta"] or {}).get("decision") in ("include", "maybe"))
    assert c["included"] == sum(1 for r in recs if r["ft_access"] == "full_text" and (r["ft"] or {}).get("decision") == "include")
    assert sum(c["excluded_title_abstract_reasons"].values()) == c["excluded_title_abstract"]
    return st


def test_protocol_first_then_approval_once(client, monkeypatch):
    _stub(monkeypatch)
    p = _protocol(client)
    assert p["protocol"]["eligibility"]["outcomes"] == "burnout or emotional exhaustion"
    assert client.get(f"/api/review/{p['review_id']}").json()["records"] == []
    assert _run(client, p["review_id"], approve=False)[0] == 403
    status, events = _run(client, p["review_id"], edits={"eligibility": {"dates": "2010-2026"}})
    assert status == 200 and events[0]["payload"]["protocol"]["eligibility"]["dates"] == "2010-2026"
    _, again = _run(client, p["review_id"])
    assert any(e["event"] == "error" and "only once" in e["payload"]["error"] for e in again)


def test_human_in_the_loop_pauses_and_counts_follow_the_log(client, monkeypatch):
    model = _stub(monkeypatch)
    p = _protocol(client)
    _, events = _run(client, p["review_id"], mode="copilot")
    paused = [e for e in events if e["event"] == "paused"]
    assert paused and paused[0]["payload"]["stage"] == "ta", "copilot must pause after title/abstract screening"
    st = _counts_match_log(client, p["review_id"])
    assert st["counts"]["identified"] == 7 and st["counts"]["duplicates_removed"] == 1 and st["counts"]["screened"] == 6
    assert len(st["queue_ta"]) == 6

    # The Screener never saw the hypothesis.
    screener_humans = [h for s, h in model.calls if "Thoth's Screener" in s]
    assert screener_humans and all("circadian misalignment" not in h for h in screener_humans)

    # An exclusion without a protocol reason is refused; with one it is recorded as an override.
    rid_a = next(q["record_id"] for q in st["queue_ta"] if q["meta"]["title"].endswith("A"))
    assert client.post(f"/api/review/{p['review_id']}/decisions/{rid_a}", json={"stage": "ta", "decision": "exclude", "reason": "felt like it"}).status_code == 400
    out = client.post(f"/api/review/{p['review_id']}/decisions/{rid_a}", json={"stage": "ta", "decision": "exclude", "reason": "designs"}).json()
    assert out["overridden"] is True and out["by"] == "user" and out["counts"]["excluded_title_abstract"] == 2
    _counts_match_log(client, p["review_id"])

    # Continuing while decisions are open just re-shows the queue.
    assert [e["event"] for e in _continue(client, p["review_id"])][0] == "paused"
    client.post(f"/api/review/{p['review_id']}/accept-all", json={"stage": "ta"})
    ev = _continue(client, p["review_id"])
    assert any(e["event"] == "paused" and e["payload"]["stage"] == "ft" for e in ev)
    client.post(f"/api/review/{p['review_id']}/accept-all", json={"stage": "ft"})
    ev = _continue(client, p["review_id"])
    kinds = [e["event"] for e in ev]
    assert "included" in kinds and "matrix_row" in kinds and "verdict" in kinds and "review_complete" in kinds
    st = _counts_match_log(client, p["review_id"])
    c = st["counts"]
    assert c["not_retrieved"] == 1, "the paper without open full text is counted as not retrieved"
    assert c["included"] == c["assessed_full_text"] - c["excluded_full_text"] - c["full_text_unscreened"]
    trial = client.get(f"/api/trial/{st['trial_id']}").json()
    assert len(trial["papers"]) == c["included"] and trial["verdict"]["overall"]["verdict"] == "supported_within_limits"


def test_auto_mode_queues_low_confidence_without_pausing(client, monkeypatch):
    _stub(monkeypatch)
    p = _protocol(client)
    _, events = _run(client, p["review_id"], mode="auto")
    kinds = [e["event"] for e in events]
    assert "paused" not in kinds and "review_complete" in kinds
    st = _counts_match_log(client, p["review_id"])
    assert [q["meta"]["title"] for q in st["queue_ta"]] == ["Unsure rota C"], "only the low-confidence decision is queued for audit"


def test_exclusion_without_reason_is_not_an_exclusion(client):
    from backend.research.review import _enforce
    d = _enforce({"decision": "exclude", "exclusion_reason": "", "confidence": 0.9}, "ta", "auto")
    assert d["decision"] == "maybe" and d["needs_review"] is True
    d = _enforce({"decision": "maybe", "confidence": 0.9}, "ft", "auto")
    assert d["decision"] == "exclude" and d["needs_review"] is True


def test_model_down_leaves_records_unscreened(client, monkeypatch):
    _stub(monkeypatch, with_model=False)
    p = client.post("/api/review/protocol", json={"project_id": "p15b", "hypothesis": HYP}).json()
    assert p["degraded"] is True
    _, events = _run(client, p["review_id"], mode="auto")
    assert any(e["event"] == "blocked" for e in events)
    st = _counts_match_log(client, p["review_id"])
    assert st["status"] == "blocked" and st["counts"]["unscreened"] == st["counts"]["screened"] and st["counts"]["included"] == 0


def test_zero_included_is_reported_honestly_without_an_empty_trial(client, monkeypatch):
    model = _stub(monkeypatch)
    real = screener_answer

    def exclude_all(human):
        out = real(human)
        if "<stage>full_text</stage>" in human:
            for d in out["decisions"]:
                d.update(decision="exclude", exclusion_reason="comparison", confidence=0.95)
        return out

    monkeypatch.setattr("backend.tests.scenarios.test_s15_systematic_review.screener_answer", exclude_all)
    p = _protocol(client)
    _, events = _run(client, p["review_id"], mode="auto")
    done = next(e["payload"] for e in events if e["event"] == "review_complete")
    assert done["included"] == 0 and done["trial_id"] is None and "comparison" in done["note"]
    assert "verdict" not in [e["event"] for e in events]
