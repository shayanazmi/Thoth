"""
S23 · The systematic review at scale: budgets, a logged search, stopping rules, citation rounds, Stop and Resume
(vision §5.4-5.7, §4.2; plan Phase 2 B).

User-seat criteria encoded here:
  - The review pages through each database up to the researcher's budget, and records every request: database,
    query, page, date, how many it returned, how many were new, how many matches exist in total.
  - Why a search stopped is always recorded in words the researcher can read: a database ran out, the budget was
    reached ("the first 120 of 400"), title/abstract screening stopped after K irrelevant records in a row, a
    citation round found nothing new. Records left unscreened by a rule are counted, never dropped.
  - If the researcher overrides a decision inside that run of irrelevant records, the rule no longer holds: the
    entry is kept but marked superseded, and screening carries on.
  - References of, and papers citing, what passed screening are searched in rounds, logged with their seed, and
    counted apart from the database results (PRISMA "other methods").
  - Eligible records beyond the full-text budget are counted as "not retrieved (budget)"; raising the budget reads
    them, and a finished synthesis is never rewritten: a new trial is made and the earlier one kept.
  - Stop keeps everything; Continue resumes from the stored cursor without duplicating a record. A review left
    running by a crash is stopped at startup and can be continued.
  - The Screener never sees the hypothesis; the Judge is told how the evidence was found.
"""
from __future__ import annotations

import json
import re

from backend.tests.scenarios.conftest import read_sse
from backend.tests.scenarios.test_s16_trial_neutral_court import RoleModel

HYP = "Night-shift nurses have higher emotional exhaustion than day-shift nurses because of circadian misalignment."
PROTOCOL = {"framework": "PICO", "question": {}, "eligibility": {c: f"{c} rule" for c in
            ("population", "exposure", "comparison", "outcomes", "designs", "dates", "languages")},
            "search": {"openalex": "night shift nurses exhaustion", "europepmc": "night shift nurses"}}


def screener(relevant):
    """Includes records whose title passes `relevant(title)`, excludes the rest with a protocol reason."""
    def answer(human):
        out = []
        for rid, body in re.findall(r'<untrusted record_id="([^"]+)">\n(.*?)\n</untrusted>', human, re.S):
            title = body.split("\n", 1)[0].replace("Title: ", "")
            ok = relevant(title)
            out.append({"record_id": rid, "decision": "include" if ok else "exclude", "exclusion_reason": "" if ok else "population",
                        "confidence": 0.95, "criteria": []})
        return {"decisions": out}
    return answer


def install(monkeypatch, relevant, full_text_access="abstract_only", extra=None):
    import backend.research.llm as rl
    model = RoleModel({"Draft a systematic-review protocol": PROTOCOL, "Split the hypothesis": {"subclaims": [{"id": 1, "claim": HYP}]},
                       "Thoth's Screener": screener(relevant), **(extra or {})})
    monkeypatch.setattr(rl, "_llm", lambda role: model)
    import backend.research.librarian as L

    async def full_text(meta):
        return ("FULL TEXT " * 400, "full_text", "test") if full_text_access == "full_text" else (meta.get("abstract") or "abs", "abstract_only", "test")

    async def ep(client, q, limit, dropped=None, cursor=None, page_info=None):
        return []

    async def adjacent(strat, per_field=4):
        return {"ran": True, "fields": []}

    monkeypatch.setattr(L, "full_text", full_text)
    monkeypatch.setattr(L, "search_europepmc", ep)
    monkeypatch.setattr(L, "adjacent_search", adjacent)
    return model


def openalex(monkeypatch, titles, total=None, on_page=None):
    """A paged OpenAlex: cursor "*" → page 1, "c2" → page 2, …; reports total and next cursor."""
    import backend.research.librarian as L
    pages = []

    async def oa(client, q, limit, cursor=None, page_info=None):
        page = 1 if cursor in (None, "*") else int(str(cursor)[1:])
        pages.append(page)
        if on_page:
            on_page(page)
        start = (page - 1) * 100
        chunk = titles[start:start + limit]
        if page_info is not None:
            page_info["total"] = total if total is not None else len(titles)
            page_info["next_cursor"] = f"c{page + 1}" if start + limit < len(titles) else None
        return [{"title": t, "year": 2020, "doi": f"10.9/{start + i}", "abstract": f"abstract of {t}", "found_via": "OpenAlex",
                 "openalex_id": f"W{start + i + 1}"} for i, t in enumerate(chunk)]

    monkeypatch.setattr(L, "search_openalex", oa)
    return pages


def protocol(client, pid="p23"):
    return client.post("/api/review/protocol", json={"project_id": pid, "hypothesis": HYP}).json()


def run(client, rid, budget, mode="auto"):
    with client.stream("POST", f"/api/review/{rid}/run", json={"approve": True, "mode": mode, "budget": budget}) as r:
        return read_sse(r, max_events=2000, max_seconds=30)


def resume(client, rid):
    with client.stream("POST", f"/api/review/{rid}/continue", json={}) as r:
        return read_sse(r, max_events=2000, max_seconds=30)


def state(client, rid):
    return client.get(f"/api/review/{rid}").json()


def stops(st, rule=None):
    return [s for s in st["stopping"] if (rule is None or s["rule"] == rule)]


def test_paging_logs_every_request_and_records_the_budget_stop(client, monkeypatch):
    model = install(monkeypatch, lambda t: False)
    pages = openalex(monkeypatch, [f"Paper {i} on night work" for i in range(400)])
    rid = protocol(client)["review_id"]
    run(client, rid, {"keyword_records": 120, "citation_rounds": 0, "stop_after_irrelevant": 0})
    st = state(client, rid)
    assert st["counts"]["identified"] == st["counts"]["identified_databases"] == 120
    assert pages == [1, 2], "100 per page, then the remaining 20"
    log = client.get(f"/api/review/{rid}/searches").json()["searches"]
    oa = [s for s in log if s["source"] == "OpenAlex" and s["requested"]]
    assert [(s["page"], s["returned"], s["total_available"]) for s in oa] == [(1, 100, 400), (2, 20, 400)]
    assert all(s["query"] == "night shift nurses exhaustion" and s["searched_at"] for s in oa)
    budget = stops(st, "budget_reached")
    assert any(s["scope"] == "OpenAlex" and "first 120 of 400" in s["detail"] for s in budget)
    assert any("first 120 of 400" in x for x in st["limitations"]) and any("core corpus" in x for x in st["limitations"])
    assert any(s["rule"] == "citation_off" for s in st["stopping"])
    # The Screener is blind to the hypothesis.
    assert all("circadian misalignment" not in h for s, h in model.calls if "Thoth's Screener" in s)


def test_a_database_that_runs_out_says_so(client, monkeypatch):
    install(monkeypatch, lambda t: False)
    openalex(monkeypatch, [f"Paper {i}" for i in range(30)])
    rid = protocol(client)["review_id"]
    run(client, rid, {"keyword_records": 300, "citation_rounds": 0, "stop_after_irrelevant": 0})
    st = state(client, rid)
    assert st["counts"]["identified"] == 30
    assert any(s["scope"] == "OpenAlex" and "all 30" in s["detail"] for s in stops(st, "source_exhausted"))
    assert not [s for s in stops(st, "budget_reached") if s["scope"] == "OpenAlex"]


def test_screening_stops_after_k_irrelevant_records_and_counts_the_rest(client, monkeypatch):
    titles = [f"Relevant {i}" if i < 30 else f"Other {i}" for i in range(200)]
    install(monkeypatch, lambda t: t.startswith("Relevant"))
    openalex(monkeypatch, titles)
    rid = protocol(client)["review_id"]
    run(client, rid, {"keyword_records": 200, "citation_rounds": 0, "stop_after_irrelevant": 50})
    st = state(client, rid)
    c = st["counts"]
    assert c["not_screened_stopped"] > 0 and c["screened_by_screener"] >= 100
    assert c["screened_by_screener"] + c["not_screened_stopped"] == c["screened"] == 200
    s4 = stops(st, "consecutive_irrelevant")
    assert len(s4) == 1 and "50 consecutive irrelevant" in s4[0]["detail"]
    left = client.get(f"/api/review/{rid}/records?filter=not_screened&limit=200").json()
    assert left["total"] == c["not_screened_stopped"]
    assert all(r["screening"]["ta"]["by"] == "stopping_rule" for r in left["records"])
    assert c["sought_for_retrieval"] == 30, "every relevant record was ranked above the stop"


def test_overriding_inside_the_run_supersedes_the_rule_and_screening_resumes(client, monkeypatch):
    titles = [f"Relevant {i}" if i < 30 else f"Other {i}" for i in range(200)]
    install(monkeypatch, lambda t: t.startswith("Relevant"))
    openalex(monkeypatch, titles)
    rid = protocol(client)["review_id"]
    run(client, rid, {"keyword_records": 200, "citation_rounds": 0, "stop_after_irrelevant": 50})
    before = state(client, rid)["counts"]["not_screened_stopped"]
    recs = client.get(f"/api/review/{rid}/records?filter=excluded_ta&limit=200").json()["records"]
    last_excluded = max(recs, key=lambda r: int(r["meta"]["title"].split()[-1]))
    assert client.post(f"/api/review/{rid}/decisions/{last_excluded['record_id']}",
                       json={"stage": "ta", "decision": "include"}).status_code == 200
    resume(client, rid)
    st = state(client, rid)
    s4 = stops(st, "consecutive_irrelevant")
    assert any(s.get("superseded") for s in s4), "the earlier stop is kept, marked superseded"
    assert st["counts"]["not_screened_stopped"] < before, "screening carried on past the old stop"


def test_citation_rounds_are_logged_counted_apart_and_stop_at_saturation(client, monkeypatch):
    from backend.research import citations
    titles = ["Relevant A", "Relevant B"] + [f"Other {i}" for i in range(10)]
    install(monkeypatch, lambda t: t.startswith("Relevant") or t.startswith("Cited relevant"))
    openalex(monkeypatch, titles)

    async def backward(client_, meta, limit, query=""):
        t = meta["title"]
        if t.startswith("Relevant"):
            found = [{"title": f"Cited relevant {t[-1]}{i}", "doi": f"10.7/{t[-1]}{i}", "abstract": "x"} for i in range(5)]
            found += [{"title": "Other 3", "doi": "10.9/5", "abstract": "dup of a database record"}]
        else:
            found = [{"title": f"Cited other {t[-2:]}{i}", "doi": f"10.8/{t[-2:]}{i}", "abstract": "x"} for i in range(3)]
        return found, {"provider": "OpenAlex", "requested": limit, "returned": len(found), "removed_offtopic": 1, "total_available": 9, "error": None}

    async def forward(client_, meta, limit, query=""):
        return [], {"provider": "OpenAlex", "requested": limit, "returned": 0, "removed_offtopic": 0, "total_available": 0, "error": None}

    monkeypatch.setattr(citations, "backward", backward)
    monkeypatch.setattr(citations, "forward", forward)
    rid = protocol(client)["review_id"]
    run(client, rid, {"keyword_records": 100, "citation_records": 200, "citation_rounds": 3, "stop_after_irrelevant": 0})
    st = state(client, rid)
    c = st["counts"]
    assert c["identified_databases"] == 12
    assert c["identified_citations"] == 2 * 6 + 10 * 3, "round 1: two seeds × 6; round 2: ten new seeds × 3"
    assert c["identified"] == c["identified_databases"] + c["identified_citations"]
    assert c["duplicates_removed"] >= 2, "a database record found again by citation is a duplicate"
    log = client.get(f"/api/review/{rid}/searches").json()["searches"]
    r1 = [s for s in log if s["kind"] == "backward" and s["round"] == 1]
    assert len(r1) == 2 and all(s["seed_record_id"] for s in r1) and all(s["removed_offtopic"] == 1 for s in r1)
    sat = stops(st, "citation_saturation")
    assert sat and sat[0]["scope"] == "round 2", "round 2 found nothing relevant"
    assert c["removed_before_screening"]["automated_offtopic"] >= 2
    cited = client.get(f"/api/review/{rid}/records?filter=citation&limit=200").json()
    assert cited["total"] == c["identified_citations"] and all(r["origin"]["kind"] == "backward" for r in cited["records"])


def test_full_text_budget_counts_the_rest_and_raising_it_makes_a_new_trial(client, monkeypatch):
    titles = [f"Relevant {i}" for i in range(8)]
    model = install(monkeypatch, lambda t: True, full_text_access="full_text")
    openalex(monkeypatch, titles)
    from backend.memory import conversation_store as nb
    nb.write_section("p23b", "hypothesis", HYP, "user")
    rid = protocol(client, "p23b")["review_id"]
    run(client, rid, {"keyword_records": 100, "citation_rounds": 0, "stop_after_irrelevant": 0, "full_text": 5})
    st = state(client, rid)
    assert st["counts"]["not_retrieved_budget"] == 3 and st["counts"]["included"] == 5
    assert stops(st, "ft_budget") and any("full-text budget is 5" in x for x in st["limitations"])
    first = client.get(f"/api/trial/{st['trial_id']}").json()
    assert first["hypothesis_version"] == 1, "the review's trial is tied to the hypothesis version"
    assert first["strategy"]["coverage"]["kind"] == "systematic_review" and first["verdict"]["coverage"]["included"] == 5
    judge = [h for s, h in model.calls if "Thoth's Judge" in s][-1]
    assert "<evidence_base>" in judge and "<citation_neighbours>" in judge

    raised = client.post(f"/api/review/{rid}/budget", json={"full_text": 8}).json()
    assert raised["budget"]["full_text"] == 8 and "8 full texts" in raised["estimate"]["scope"]
    resume(client, rid)
    st2 = state(client, rid)
    assert st2["counts"]["not_retrieved_budget"] == 0 and st2["counts"]["included"] == 8
    assert all(s.get("superseded") for s in stops(st2, "ft_budget"))
    assert st2["trial_id"] != st["trial_id"], "a finished synthesis is never rewritten"
    assert client.get(f"/api/trial/{st['trial_id']}").json()["status"] == "complete"
    assert len(client.get(f"/api/trial/{st2['trial_id']}").json()["papers"]) == 8
    assert client.post(f"/api/review/{rid}/budget", json={"full_text": 9}).status_code == 200
    assert client.post("/api/review/nope/budget", json={}).status_code == 404


def test_stop_keeps_everything_and_continue_resumes_from_the_cursor(client, monkeypatch):
    from backend.research import review
    install(monkeypatch, lambda t: False)
    holder = {}
    pages = openalex(monkeypatch, [f"Paper {i}" for i in range(350)],
                     on_page=lambda p: review.request_stop(holder["rid"]) if p == 2 and not holder.get("stopped") else None)
    rid = protocol(client)["review_id"]
    holder["rid"] = rid
    events = run(client, rid, {"keyword_records": 300, "citation_rounds": 0, "stop_after_irrelevant": 0})
    holder["stopped"] = True
    assert "stopped" in [e["event"] for e in events]
    st = state(client, rid)
    assert st["status"] == "stopped" and st["counts"]["identified"] == 200 and stops(st, "user_stop")
    assert client.post(f"/api/review/{rid}/stop").status_code == 409, "only a running review can be stopped"
    resume(client, rid)
    st = state(client, rid)
    assert pages == [1, 2, 3], "Continue picked up at page 3"
    assert st["counts"]["identified"] == 300
    dois = [r["meta"]["doi"] for r in client.get(f"/api/review/{rid}/records?limit=200").json()["records"]] + \
           [r["meta"]["doi"] for r in client.get(f"/api/review/{rid}/records?offset=200&limit=200").json()["records"]]
    assert len(dois) == len(set(dois)) == 300, "no record was fetched twice"
    assert all(s.get("superseded") for s in stops(st, "user_stop"))


def test_a_review_left_running_by_a_crash_can_be_continued(client, monkeypatch):
    install(monkeypatch, lambda t: False)
    openalex(monkeypatch, [f"Paper {i}" for i in range(20)])
    from backend.research import review_store as rs
    rid = protocol(client)["review_id"]
    rs.update(rid, status="running", stage="identifying", mode="auto", budget_json={"citation_rounds": 0, "stop_after_irrelevant": 0})
    assert rs.reconcile_orphaned() == 1 and rs.get(rid)["status"] == "stopped"
    resume(client, rid)
    assert state(client, rid)["status"] == "complete" and state(client, rid)["counts"]["identified"] == 20


def test_estimate_follows_the_budget_and_clamps_it(client):
    out = client.post("/api/review/estimate", json={"budget": {"keyword_records": 5000, "stop_after_irrelevant": 5, "full_text": 1}}).json()
    assert out["budget"]["keyword_records"] == 1000 and out["budget"]["stop_after_irrelevant"] == 20 and out["budget"]["full_text"] == 5
    assert "up to 1000 records" in out["estimate"]["scope"] and out["estimate"]["model_calls"].startswith("up to")
    p = client.post("/api/review/protocol", json={"project_id": "p23e", "hypothesis": HYP}).json()
    assert p["budget"]["keyword_records"] == 300 and p["budget_bounds"]["full_text"] == [5, 80]
    assert client.get(f"/api/review/{p['review_id']}/searches").json() == {"searches": []}
    assert client.get("/api/review/nope/records").status_code == 404


def test_an_unparseable_screener_answer_is_retried_with_a_format_note(client, monkeypatch):
    """Seen live (29 Oct 2026): the Screener quoted the paper with double quotes inside its evidence, the JSON broke,
    and a retry at temperature 0 broke the same way. The retry now says why; nothing is decided on its behalf."""
    base = screener(lambda t: True)

    def flaky(human):
        return base(human) if "<format_note>" in human else {}

    install(monkeypatch, lambda t: True, full_text_access="full_text", extra={"Thoth's Screener": flaky})
    openalex(monkeypatch, ["Relevant 0", "Relevant 1"])
    rid = protocol(client, "p23f")["review_id"]
    run(client, rid, {"keyword_records": 100, "citation_rounds": 0, "stop_after_irrelevant": 0, "full_text": 5})
    st = state(client, rid)
    assert st["status"] == "complete" and st["counts"]["unscreened"] == 0 and st["counts"]["full_text_unscreened"] == 0
    assert st["counts"]["included"] == 2
