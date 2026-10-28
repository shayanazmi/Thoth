"""
Scenario-suite shared fixtures and helpers.

- ``client``: the app booted on an isolated SQLite db per test, provider keys blank (honest fail-open).
- ``read_sse`` / ``kinds``: parse an /api/chat-style SSE stream into ``{event, payload}`` dicts.
- Live scholarly fetchers and every model are stubbed so the gate never touches the network
  (opt out with ``@pytest.mark.live_scholarly`` / ``@pytest.mark.live_llm``).
"""
from __future__ import annotations

import importlib
import json
import sys
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Boot the app against an isolated SQLite db and empty env."""
    monkeypatch.setenv("THOTH_DB_PATH", str(tmp_path / "scenario.db"))
    for k in ("NVIDIA_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY",
              "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET"):
        monkeypatch.setenv(k, "")
    # Modules that cache the DB path at import time are reloaded so each test lands on its own tmp_path.
    for mod_name in ("backend.memory.db", "backend.memory.vault", "backend.conversation.brief",
                     "backend.conversation.idea", "backend.core.config", "backend.main"):
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
    import backend.core.config as cfg
    cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    import backend.main as bm
    importlib.reload(bm)
    with TestClient(bm.app) as c:
        yield c


def read_sse(resp, *, max_events: int = 60, max_seconds: float = 20.0):
    """Parse SSE line by line into a list of {event, payload} dicts; stop on 'complete'."""
    events = []
    start = time.time()
    for raw in resp.iter_lines():
        if raw.startswith("data: "):
            try:
                events.append(json.loads(raw[6:]))
            except Exception:
                pass
        if len(events) >= max_events or (time.time() - start) > max_seconds:
            break
        if events and events[-1].get("event") == "complete":
            break
    return events


def kinds(events):
    return [e.get("event") for e in events]

# Provider keys and hosted-service URLs are blanked in the repo-root conftest.py,
# which pytest loads before importing the backend package (see the note there).


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
        # Called directly by backend/research/citations.py so that rate limits are recorded as errors.
        "_fetch_s2_citations_raw",
        "_fetch_s2_references_raw",
        "snowball_literature_graph",
    ):
        fn = getattr(sch, name, None)
        if fn is None:
            continue
        import inspect
        stub = _async_empty if inspect.iscoroutinefunction(fn) else _sync_empty
        monkeypatch.setattr(sch, name, stub, raising=False)


@pytest.fixture(autouse=True)
def _no_live_conductor_model(request, monkeypatch):
    """The conductor (docs/features/01) never calls a real model in the scenario
    suite. By default it behaves as if no provider is reachable (degraded reply);
    tests that need behaviour install a scripted fake. Opt out with
    ``@pytest.mark.live_llm``."""
    if request.node.get_closest_marker("live_llm"):
        return
    # Blank provider keys BEFORE the import below: importing the conductor imports
    # backend.agents, whose load_dotenv() would otherwise pull real keys from .env
    # and make the scenarios call live models.
    for k in ("NVIDIA_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.setenv(k, "")
    try:
        import backend.conversation.conductor as cd
    except Exception:
        return

    def _unavailable():
        raise RuntimeError("no model in scenario tests")

    monkeypatch.setattr(cd, "_llm", _unavailable, raising=False)
    try:
        import backend.thinkers.modes as tm
        monkeypatch.setattr(tm, "_llm", lambda role: _unavailable(), raising=False)
    except Exception:
        pass
    try:
        import backend.research.llm as rl
        monkeypatch.setattr(rl, "_llm", lambda role: _unavailable(), raising=False)
    except Exception:
        pass
