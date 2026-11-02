# Thoth · Developed by Shayan Azmi
"""
S27 · Plain words for the researcher .

User-seat criteria encoded here:
  - A ruling never shows internal field talk ("(adjacent_search.ran = false)"); a bare verdict label reads as words.
    Nothing else in the Judge's reasoning is changed.
  - Thoth's own example phrasings in quotation marks are not flagged as misquotes; words attributed to a thinker
    still are (S20 keeps the rest of that check).
  - When a literature source fails, the stopping rule and the limitations say so plainly ("the service was
    unavailable (HTTP 503)") without the provider's URL; the search record keeps the raw error.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage

from backend.tests.scenarios.test_s10_conductor_memory_and_offers import ScriptedModel, _install, _turn
from backend.tests.scenarios.test_s20_conductor_hears_the_thinkers import PID, _answer, _seed
from backend.tests.scenarios.test_s23_review_scale_and_stopping import install, openalex, protocol, run, state, stops

RAW_503 = ("Server error '503 Service Unavailable' for url "
           "'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=night%20shift'")


def test_the_ruling_never_shows_internal_field_names():
    from backend.research.judge import enforce
    papers = [{"access": "abstract_only"}]
    v = enforce({"overall": {"verdict": "insufficient_evidence",
                             "reason": "One witness, abstract only (adjacent_search.ran = false); the verdict is insufficient_evidence."},
                 "originality": {"label": "insufficiently_assessed", "reason": "Not assessed (citation.papers_found = 0)."},
                 "per_subclaim": [{"id": 1, "verdict": "contested", "case_for": "W1 suggests it, e.g. in week 2.",
                                   "case_against": "None (full_text_witnesses = 0)."}]},
                papers, {"ran": False}, [{"id": 1, "claim": "c"}])
    assert v["overall"]["reason"] == "One witness, abstract only; the verdict is insufficient evidence."
    assert v["originality"]["reason"] == "Not assessed."
    assert v["per_subclaim"][0]["case_for"] == "W1 suggests it, e.g. in week 2.", "ordinary text, e.g. abbreviations, is untouched"
    assert "full_text_witnesses" not in v["per_subclaim"][0]["case_against"]


def test_thoths_own_examples_in_quotes_are_not_flagged_but_a_thinkers_words_are(client, monkeypatch):
    _seed()
    example = ('You could ask each nurse something like "how tired did you feel during the final two hours of the shift" '
               'and compare it with incident reports.')
    attributed = 'As Karl Popper put it: "a diary of how tired you felt would never be enough to refute anything."'
    _install(monkeypatch, ScriptedModel([AIMessage(content=example), AIMessage(content=attributed)]))
    ok = _answer(_turn(client, {"message": "how would I measure fatigue?", "project_id": PID}))
    assert ok["misquotes"] == [] and "not in the record word for word" not in ok["answer"]
    bad = _answer(_turn(client, {"message": "what would Popper say?", "project_id": PID}))
    assert bad["misquotes"], "words put in a thinker's mouth are still flagged"


def test_a_failed_source_is_reported_plainly(client, monkeypatch):
    install(monkeypatch, relevant=set())
    import backend.research.librarian as L

    async def ep(client_, q, limit, dropped=None, cursor=None, page_info=None):
        if page_info is not None:
            page_info["error"] = RAW_503
        return []

    monkeypatch.setattr(L, "search_europepmc", ep)
    openalex(monkeypatch, [f"Unrelated record {i}" for i in range(3)])
    rid = protocol(client, "p27")["review_id"]
    run(client, rid, budget=50)
    st = state(client, rid)
    failed = stops(st, "source_error")
    assert failed and "the service was unavailable (HTTP 503)" in failed[0]["detail"]
    shown = " ".join(st["limitations"]) + " ".join(s["detail"] for s in st["stopping"])
    assert st["limitations"] and "https://" not in shown and "Server error" not in shown

    from backend.research.review import _tidy, plain_error
    assert _tidy(f"Europe PMC: the search failed ({RAW_503[:120]}); 4 record(s) were retrieved.") == \
        "Europe PMC: the search failed (the service was unavailable (HTTP 503)); 4 record(s) were retrieved.", "older records read plainly too"
    assert plain_error("ReadTimeout: timed out") == "the service did not answer in time"
    assert plain_error("Client error '429 Too Many Requests'") == "the service limited requests (HTTP 429)"
