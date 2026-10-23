"""
Scenario-suite shared fixtures.

Phase 2 note (23 Oct 2026): scenario tests that go through
_run_pipeline hit the real scholarly fetchers under
`backend/scholarly.py`. ArXiv, Semantic Scholar, OpenAlex, PubMed and
Europe PMC require no API key, so on a developer machine with live
internet the tests wait on real HTTP + the dispatcher's retry window —
each approval-path scenario burns 30-90 seconds that way, and the
whole gate can take 7+ minutes.

The vision-level test is "the approval flow fires and the FSM makes
forward progress", not "we actually fetched papers". So we neutralize
the scholarly fetchers for the scenario suite only. Nothing in
production code changes.

If a future scenario specifically asserts on scholarly fetch
behaviour, it can opt out by setting `request.node.add_marker("live_scholarly")`
and the fixture will skip the patch for that test.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _neutralize_scholarly(request, monkeypatch):
    """Stub all live scholarly fetchers to empty lists in the scenario suite.

    Opt out by marking a test with ``@pytest.mark.live_scholarly``.
    """
    if request.node.get_closest_marker("live_scholarly"):
        return

    try:
        import backend.scholarly as sch
    except Exception:
        return

    async def _async_empty(*a, **kw):
        return []

    def _sync_empty(*a, **kw):
        return []

    # Cover both the public and the raw fetcher names.
    for name in (
        "search_scholarly_sources",
        "search_arxiv",
        "search_semantic_scholar",
        "search_openalex",
        "search_tavily",
        "search_pubmed",
        "search_europepmc",
        "get_paper_recommendations",
        "get_paper_citations",
        "get_paper_references",
        "snowball_literature_graph",
    ):
        fn = getattr(sch, name, None)
        if fn is None:
            continue
        import inspect
        stub = _async_empty if inspect.iscoroutinefunction(fn) else _sync_empty
        monkeypatch.setattr(sch, name, stub, raising=False)

    # Also neutralize the module-level dispatcher calls so pipeline.search_node
    # that imports symbols from scholarly picks up the stubs if it late-binds.
    try:
        import backend.pipeline as pl
        for name in ("search_scholarly_sources",):
            if hasattr(pl, name):
                monkeypatch.setattr(pl, name, _async_empty, raising=False)
    except Exception:
        pass
