"""
Scenario S1 — Conversation first, no mode lanes.

Vision anchors: THOTH.docx §2 (Conversation first), §10 (UX rules).
Phase: 1.

Covers:
  - A casual greeting routes to a direct, non-research reply.
  - A substantive observation produces a plan_pending card (brief prepared,
    PENDING_APPROVAL) without launching the pipeline.
  - The chat input is never gated server-side — two overlapping requests to
    /api/chat/stream both receive responses, neither mutex-blocks the other.
  - The approval path (approval block attached) launches the pipeline through
    the hardened approval gate and emits approval_recorded + approval_verified
    + complete.
  - Nothing in the response leaks the words "fast_chat", "deep_research",
    "brainstorm" as user-visible mode names — the vision rejects mode lanes.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Boot the app against an isolated SQLite db and empty env — honest fail-open."""
    monkeypatch.setenv("THOTH_DB_PATH", str(tmp_path / "scenario.db"))
    for k in (
        "NVIDIA_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "TAVILY_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
    ):
        monkeypatch.setenv(k, "")

    # Reload modules that cache the DB path at import time (DEFAULT_DB_PATH)
    # so each test lands on its own tmp_path.
    import importlib, sys
    for mod_name in [
        "backend.memory.db",
        "backend.memory.vault",
        "backend.conversation.brief",
        "backend.conversation.idea",
        "backend.core.config",
        "backend.main",
    ]:
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
    import backend.core.config as cfg
    cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    import backend.main as bm
    importlib.reload(bm)
    with TestClient(bm.app) as c:
        yield c


def _read_sse(resp, *, max_events: int = 60, max_seconds: float = 20.0):
    """Parse SSE line-by-line into a list of {event, payload} dicts; stop on 'complete'."""
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


def _kinds(events):
    return [e.get("event") for e in events]


# ---------------------------------------------------------------------------
# Scenario tests
# ---------------------------------------------------------------------------


def test_casual_greeting_routes_to_direct_answer(client):
    """A casual greeting must never produce a plan card or a pipeline run."""
    with client.stream("POST", "/api/chat/stream", json={"message": "hi thoth", "session_id": "s"}) as r:
        assert r.status_code == 200
        kinds = _kinds(_read_sse(r))
    assert "direct_answer" in kinds, f"casual turn missing direct_answer; got {kinds}"
    assert "plan_pending" not in kinds, "casual turn must not propose a research plan"
    assert "approval_verified" not in kinds, "casual turn must never launch the pipeline"
    assert "complete" in kinds


def test_research_intent_produces_plan_pending_without_launching(client):
    """A substantive observation must produce a plan_pending card and wait."""
    with client.stream("POST", "/api/chat/stream", json={
        "message": "rural anemia rates are higher despite similar iron intake — why?",
        "session_id": "s",
    }) as r:
        events = _read_sse(r)
    kinds = _kinds(events)
    assert "plan_pending" in kinds, f"research intent missing plan_pending; got {kinds}"
    assert "approval_verified" not in kinds, "pipeline must not launch without approval"

    pending = next(e for e in events if e.get("event") == "plan_pending")
    brief = pending["payload"]["brief"]
    assert brief["approval_status"] == "PENDING_APPROVAL"
    assert pending["payload"].get("requires_approval") is True


def test_approval_launches_pipeline_through_the_gate(client):
    """Approving the brief must emit approval_recorded + approval_verified +
    complete, and the pipeline must have been launched (even if external APIs
    are unreachable in this test environment)."""
    with client.stream("POST", "/api/chat/stream", json={
        "message": "iron absorption varies in rural populations",
        "session_id": "s",
    }) as r:
        prep = _read_sse(r)
    pending = next(e for e in prep if e.get("event") == "plan_pending")
    brief = pending["payload"]["brief"]
    bid, bv = brief["brief_id"], brief["version"]

    with client.stream("POST", "/api/chat/stream", json={
        "message": "go",
        "session_id": "s",
        "approval": {"brief_id": bid, "approved_version": bv},
    }) as r:
        events = _read_sse(r, max_events=40, max_seconds=25)
    kinds = _kinds(events)
    assert "approval_recorded" in kinds, kinds
    assert "approval_verified" in kinds, kinds
    assert "complete" in kinds, kinds


def test_approval_response_without_brief_id_is_rejected_cleanly(client):
    """Backdoor attempt: approval block with no brief_id must error, not launch."""
    with client.stream("POST", "/api/chat/stream", json={
        "message": "launch",
        "session_id": "s",
        "approval": {"approved_version": 1},
    }) as r:
        events = _read_sse(r)
    kinds = _kinds(events)
    assert "error" in kinds, f"expected error, got {kinds}"
    assert "approval_verified" not in kinds, "no approval token must not reach the pipeline"


def test_chat_input_stays_live_during_a_slow_prep(client):
    """Vision §2 + §10: the chat does not freeze while a brief is being prepared.
    This asserts that two concurrent /api/chat/stream requests both get responses
    (one casual, one research-intent) with no mutual blocking.
    """
    results = {}

    def _call(name, payload):
        with client.stream("POST", "/api/chat/stream", json=payload) as r:
            evts = _read_sse(r, max_events=8, max_seconds=10)
            results[name] = (r.status_code, _kinds(evts))

    t_intent = threading.Thread(target=_call, kwargs={
        "name": "intent",
        "payload": {"message": "iron absorption pathways in rural populations", "session_id": "live-a"},
    })
    t_intent.start()
    time.sleep(0.2)
    # Second request starts while the first is still running.
    _call("aside", {"message": "hi", "session_id": "live-b"})
    t_intent.join(timeout=15)

    assert "aside" in results, "concurrent casual turn did not complete"
    assert "intent" in results, "research-intent turn did not complete"
    assert results["aside"][0] == 200
    assert results["intent"][0] == 200
    assert "direct_answer" in results["aside"][1]
    assert "plan_pending" in results["intent"][1]


def test_no_mode_lanes_leak_in_sse_payloads(client):
    """The vision rejects mode lanes. No SSE payload from /api/chat/stream for
    an ordinary research-intent turn should surface the strings 'fast_chat',
    'deep_research', or 'brainstorm' as user-facing mode labels. (The internal
    strings may still appear in deeper pipeline logs; this guards the UI contract.)"""
    with client.stream("POST", "/api/chat/stream", json={
        "message": "noticing an uptick in deployed-model drift after fine-tuning",
        "session_id": "mode-test",
    }) as r:
        events = _read_sse(r)
    serialised = json.dumps(events)
    for banned in ("fast_chat", "deep_research", '"mode":"brainstorm"'):
        assert banned not in serialised, f"vision violation: {banned!r} surfaced in chat stream"
