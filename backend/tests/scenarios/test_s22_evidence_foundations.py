"""
S22 · Evidence foundations (plan: evidence depth, Phase 1). No user-visible change yet; these are the parts the
review, the trial and the research file build on.

Criteria encoded here:
  - One paper is one record whatever id it arrives with: DOI variants, OpenAlex ids, PubMed ids and titles match.
  - A paged search reports the next cursor and the total number of matches, so a review can say what it did
    not fetch; without a cursor the search behaves exactly as before.
  - Citation following finds references (backward) and citing papers (forward) from OpenAlex, falls back to
    Semantic Scholar, counts what an off-topic filter removed, and never raises.
  - The appraisal checklist is chosen in code from the study design (not one checklist for all); an answer
    without a locator is "unclear"; abstract-only text cannot answer items that need the full text; the
    overall judgement follows from the item answers; an empty or failed appraisal changes no weight.
  - The new columns exist on a fresh database and are added to an old one.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

from backend.research import appraisal, citations, librarian


# ---------------------------------------------------------------- a fake OpenAlex / Europe PMC

class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Client:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    async def get(self, url, params=None):
        self.calls.append((url, params or {}))
        for key, fn in self.routes.items():
            if key in url:
                return fn(url, params or {})
        return Resp({}, 404)


def work(n, title=None, doi=None, refs=(), abstract=("nurses", "night", "shift")):
    return {"id": f"https://openalex.org/W{n}", "doi": f"https://doi.org/{doi}" if doi else None, "title": title or f"Paper {n} about nurses night shift",
            "publication_year": 2020, "authorships": [], "primary_location": {}, "abstract_inverted_index": {w: [i] for i, w in enumerate(abstract)},
            "open_access": {}, "best_oa_location": {}, "ids": {"pmid": f"https://pubmed.ncbi.nlm.nih.gov/{n}"}, "cited_by_count": 1,
            "referenced_works": [f"https://openalex.org/W{r}" for r in refs]}


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- identity

def test_one_paper_is_one_record_whatever_id_it_arrives_with():
    assert librarian.norm_doi("https://doi.org/10.1/ABC.") == "10.1/abc"
    assert librarian.norm_doi("doi:10.1/abc") == "10.1/abc"
    assert librarian.norm_openalex("https://openalex.org/w123") == "W123"
    assert librarian.norm_openalex("nonsense") == ""

    d = librarian.Deduper()
    a = {"title": "Sleep and burnout", "doi": "https://doi.org/10.1/X"}
    d.add(a, "rec_a")
    assert d.match({"title": "Something else", "doi": "10.1/x"}) == "rec_a", "DOI variants match"
    assert d.match({"title": "Sleep and Burnout!"}) == "rec_a", "normalised titles match"
    b = {"title": "Another", "openalex_id": "W9"}
    d.add(b, "rec_b")
    assert d.match({"title": "Different title", "openalex_id": "https://openalex.org/W9"}) == "rec_b"
    assert d.match({"title": "Unrelated paper"}) is None


def test_paging_reports_cursor_and_total_and_default_is_unchanged(monkeypatch):
    def works(url, params):
        return Resp({"meta": {"count": 412, "next_cursor": "abc"}, "results": [work(1, doi="10.1/a")]})
    client = Client({"api.openalex.org/works": works})

    # Without an API key OpenAlex refuses cursor paging past page 1, so basic page numbers are used.
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    info = {}
    out = run(librarian.search_openalex(client, "nurses night shift", 50, cursor="*", page_info=info))
    assert info == {"next_cursor": "2", "total": 412} and client.calls[-1][1]["page"] == 1
    run(librarian.search_openalex(client, "nurses night shift", 50, cursor="9", page_info=info))
    assert info["next_cursor"] is None, "page 9 × 50 covers all 412 matches"
    assert out[0]["openalex_id"] == "W1" and out[0]["pmid"] == "1" and out[0]["doi"] == "10.1/a"

    monkeypatch.setenv("OPENALEX_API_KEY", "k")
    info = {}
    run(librarian.search_openalex(client, "nurses night shift", 50, cursor="*", page_info=info))
    assert info == {"next_cursor": "abc", "total": 412}
    assert client.calls[-1][1]["cursor"] == "*" and client.calls[-1][1]["api_key"] == "k"

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    run(librarian.search_openalex(client, "nurses night shift", 15))
    assert not {"cursor", "page", "api_key"} & set(client.calls[-1][1]), "without a cursor the request is as before"
    assert set(out[0]) >= {"title", "year", "venue", "authors", "doi", "abstract", "pmcid", "oa_pdf", "is_oa", "url", "citations", "found_via"}


def test_rate_limit_is_retried_once(monkeypatch):
    calls = {"n": 0}

    def works(url, params):
        calls["n"] += 1
        return Resp({"error": "Rate limit exceeded", "retryAfter": 0.01}, 429) if calls["n"] == 1 else Resp({"meta": {"count": 1}, "results": [work(5)]})
    out = run(librarian.search_openalex(Client({"api.openalex.org/works": works}), "nurses", 5))
    assert calls["n"] == 2 and out[0]["openalex_id"] == "W5"


def test_europepmc_paging_and_pmid():
    def search(url, params):
        return Resp({"hitCount": 90, "nextCursorMark": "n2", "resultList": {"result": [
            {"title": "Night shift nurses fatigue study.", "pubYear": "2021", "doi": "10.2/b", "abstractText": "nurses night shift fatigue",
             "pmid": "777", "authorString": "A, B"}]}})
    client = Client({"europepmc": search})
    info = {}
    out = run(librarian.search_europepmc(client, "nurses night shift", 50, cursor="*", page_info=info))
    assert info == {"next_cursor": "n2", "total": 90} and out[0]["pmid"] == "777"
    assert client.calls[-1][1]["cursorMark"] == "*"


# ---------------------------------------------------------------- citations

def test_backward_and_forward_from_openalex():
    seed = {"title": "Seed", "openalex_id": "W1", "doi": "10.1/seed"}

    def single(url, params):
        return Resp({"referenced_works": ["https://openalex.org/W2", "https://openalex.org/W3"]})

    def many(url, params):
        f = params.get("filter", "")
        if f.startswith("openalex:"):
            return Resp({"results": [work(2), work(3, title="Quantum chromodynamics lattice", abstract=("gluons", "quarks"))]})
        if f.startswith("cites:W1"):
            return Resp({"meta": {"count": 7}, "results": [work(4)]})
        return Resp({}, 404)

    client = Client({"api.openalex.org/works/W1": single, "api.openalex.org/works": many})
    refs, info = run(citations.backward(client, seed, 40, query="nurses night shift"))
    assert [p["openalex_id"] for p in refs] == ["W2"]
    assert info["provider"] == "OpenAlex" and info["total_available"] == 2 and info["removed_offtopic"] == 1
    assert refs[0]["found_via"].startswith("Citation search: reference")
    cites, info = run(citations.forward(client, seed, 20, query="nurses night shift"))
    assert [p["openalex_id"] for p in cites] == ["W4"] and info["total_available"] == 7
    assert any("cites:W1" in (c[1].get("filter") or "") and c[1].get("search") for c in client.calls)


def test_semantic_scholar_fallback_and_fail_open(monkeypatch):
    from backend import scholarly

    async def refs(pid, limit=5):
        assert pid == "10.9/seed"
        return {"data": [{"citedPaper": {"title": "Nurses night shift sleep", "abstract": "nurses night shift", "paperId": "s2a",
                                         "externalIds": {"DOI": "10.9/R1", "PubMed": "55"}, "year": 2019}}]}

    monkeypatch.setattr(scholarly, "_fetch_s2_references_raw", refs)
    down = Client({"api.openalex.org": lambda u, p: Resp({}, 500)})
    out, info = run(citations.backward(down, {"title": "Seed", "doi": "10.9/seed"}, 10, query="nurses night shift"))
    assert info["provider"] == "Semantic Scholar" and out[0]["s2_id"] == "s2a" and out[0]["doi"] == "10.9/r1" and out[0]["pmid"] == "55"

    async def limited(pid, limit=5):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(scholarly, "_fetch_s2_citations_raw", limited)
    monkeypatch.setattr(scholarly.s2_dispatcher, "max_attempts", 1)
    out, info = run(citations.forward(down, {"title": "Seed", "doi": "10.9/seed"}, 10))
    assert out == [] and "429" in info["error"], "a rate limit is recorded as an error, not as 'no citing papers'"

    out, info = run(citations.forward(down, {"title": "No ids at all"}, 10))
    assert out == [] and info["error"], "no identifier: reported, never raised"


# ---------------------------------------------------------------- appraisal

def test_checklist_is_chosen_by_design():
    assert appraisal.checklist_for("rct", "from_full_text") == ("rob2", False)
    assert appraisal.checklist_for("cohort_retrospective", "from_full_text")[0] == "jbi_cohort"
    assert appraisal.checklist_for("cross_sectional", "from_abstract")[0] == "jbi_cross_sectional"
    assert appraisal.checklist_for("meta_analysis", "from_full_text")[0] == "jbi_sr"
    assert appraisal.checklist_for("narrative_review", "x")[0] == "sanra"
    assert appraisal.checklist_for("modelling", "from_full_text") == (None, False)
    assert appraisal.checklist_for("other:delphi", "from_full_text") == (None, True)
    assert appraisal.checklist_for(None, "not_reported") == (None, True)
    used = {c for d in ("rct", "quasi_experimental", "cohort_prospective", "case_control", "cross_sectional", "qualitative",
                        "systematic_review", "mixed_methods", "narrative_review") for c in [appraisal.checklist_for(d)[0]]}
    assert len(used) == 9, "not one checklist for every design"


def _answers(**kw):
    return {"items": [{"id": k, "answer": v[0], "evidence": "quote", "locator": v[1]} for k, v in kw.items()],
            "core": {"methods_fit": {"answer": "yes", "why": "w", "locator": "Methods"},
                     "conclusions_beyond_evidence": [{"claim": "shift work causes burnout", "why": "cross-sectional", "locator": "Discussion"}]}}


def test_enforcement_and_overall_follow_the_items():
    full = {f"x{i}": ("yes", "Methods") for i in range(1, 9)}
    a = appraisal.enforce(_answers(**full), "jbi_cross_sectional", "full_text", "cross_sectional", False)
    assert a["overall"] == "low" and a["counts"]["yes"] == 8 and a["core"]["conclusions_beyond_evidence"][0]["claim"]

    no_loc = dict(full, x5=("no", ""))
    a = appraisal.enforce(_answers(**no_loc), "jbi_cross_sectional", "full_text", "cross_sectional", False)
    assert next(i for i in a["items"] if i["id"] == "x5")["answer"] == "unclear", "no locator, no verdict"
    assert a["overall"] == "some_concerns", "a critical item left unclear"

    crit_no = dict(full, x6=("no", "Table 1"))
    a = appraisal.enforce(_answers(**crit_no), "jbi_cross_sectional", "full_text", "cross_sectional", False)
    assert a["overall"] == "high" and "confounding" in a["overall_why"]

    a = appraisal.enforce(_answers(**full), "jbi_cross_sectional", "abstract_only", "cross_sectional", False)
    assert all(i["answer"] == "not_assessable" for i in a["items"]) and a["overall"] == "not_assessable"
    assert all(i["provenance"] == "from_abstract" for i in a["items"])

    a = appraisal.enforce({"items": [{"id": "bogus", "answer": "yes", "locator": "x"}]}, "rob2", "full_text", "rct", False)
    assert [i["id"] for i in a["items"]] == ["d1", "d2", "d3", "d4", "d5"], "unknown ids dropped, every item present"

    a = appraisal.enforce(_answers(), None, "full_text", "modelling", False)
    assert a["overall"] == "core_only" and a["selection_note"]


def test_weight_factor_and_empty_or_failed_appraisal(monkeypatch):
    assert appraisal.factor({}) == 1.0 and appraisal.factor(None) == 1.0
    assert appraisal.factor({"overall": "high"}) == 0.6 and appraisal.factor({"overall": "not_appraised"}) == 1.0

    import backend.research.llm as rl
    from langchain_core.messages import AIMessage

    class Empty:
        def invoke(self, messages, **kw):
            self.human = messages[-1].content
            return AIMessage(content="{}")

    m = Empty()
    monkeypatch.setattr(rl, "_llm", lambda role: m)
    a = run(appraisal.appraise({"title": "T"}, "text", "full_text", {"value": "rct", "provenance": "from_full_text"}))
    assert a["overall"] == "not_appraised" and appraisal.factor(a) == 1.0
    assert "<checklist>" in m.human and "d1" in m.human and "<untrusted>" in m.human

    def boom(role):
        raise RuntimeError("no key")
    monkeypatch.setattr(rl, "_llm", boom)
    a = run(appraisal.appraise({"title": "T"}, "text", "full_text", {"value": "rct"}))
    assert a["overall"] == "not_appraised" and a["error"]


# ---------------------------------------------------------------- schema

def test_new_columns_on_fresh_and_old_databases(client, tmp_path):
    from backend.memory import db
    from backend.research import review_store as rs, store
    conn = db.get_connection(db.DEFAULT_DB_PATH)
    cols = lambda t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    assert {"budget_json", "stopping_json"} <= cols("sys_reviews")
    assert {"ids_json", "origin_json", "rank"} <= cols("sys_review_records")
    assert "appraisal_json" in cols("trial_papers") and "rationale_json" in cols("notebook_sections")
    assert "next_cursor" in cols("sys_review_searches")

    rid = rs.create("p22", "h", {}, [])
    rec = rs.add_record(rid, {"title": "t"}, "OpenAlex", ids={"doi": "10.1/a"}, origin={"kind": "keyword"}, rank=3)
    assert rs.records(rid)[0]["ids"] == {"doi": "10.1/a"} and rs.records(rid)[0]["rank"] == 3
    assert rs.add_record(rid, {"title": "u"}, "OpenAlex")  # the old call still works
    sid = rs.add_search(rid, kind="keyword", source="OpenAlex", query="q", page=1, returned=50, total_available=400, next_cursor="c")
    assert rs.searches(rid)[0]["search_id"] == sid and rs.get(rid)["budget"] == {} and rs.get(rid)["stopping"] == []
    tid = store.create_trial("p22", "h", [])
    pid = store.add_paper(tid, {"title": "t"})
    store.update_paper(pid, appraisal_json={"overall": "low"})
    assert store.get_paper(pid)["appraisal"] == {"overall": "low"}

    old = tmp_path / "old.db"
    c = sqlite3.connect(old)
    c.executescript("CREATE TABLE notebook_sections (section_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, kind TEXT NOT NULL, "
                    "version INTEGER NOT NULL, content TEXT NOT NULL, author TEXT NOT NULL, created_at REAL NOT NULL);")
    c.close()
    db.init_db(str(old))
    assert "rationale_json" in {r[1] for r in sqlite3.connect(old).execute("PRAGMA table_info(notebook_sections)")}
