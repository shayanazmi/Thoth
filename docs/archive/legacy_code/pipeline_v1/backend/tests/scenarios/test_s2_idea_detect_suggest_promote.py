"""
Scenario S2 — Idea capture: detect, suggest, promote.

Vision anchor: THOTH.docx §3.1 ("Idea capture: detect, suggest, then promote").
Phase: 2.

Covers:
  - Casual turns and definition lookups do NOT emit idea_candidate.
  - A sharp observation (contradiction / new explanation / etc.) DOES emit
    idea_candidate, with a non-empty rationale naming which trigger fired.
  - The candidate is a *suggestion*, never persisted. After a research_intent
    turn fires the detector, the ideas table remains empty.
  - An explicit idea_promotion turn with {title, hypothesis} creates an idea
    row and persists it with status PROMOTED (the TENTATIVE→PROMOTED
    lifecycle happens atomically on explicit user action).
  - An idea_promotion missing title or hypothesis is rejected cleanly.
  - Approving a plan does NOT auto-promote the detected idea; the two
    actions are independent per vision §3.1.
"""
from __future__ import annotations

import json
import time
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "scenario_s2.db")
    monkeypatch.setenv("THOTH_DB_PATH", db_path)
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

    import importlib, sys
    # Modules that cache the DB path at import time (DEFAULT_DB_PATH) must be
    # reloaded so each test lands on its own tmp_path.
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
        c._db_path = db_path  # type: ignore[attr-defined]
        yield c


def _read_sse(resp, max_events=60, max_seconds=20):
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


def _count_ideas(client):
    r = client.get("/api/ideas")
    assert r.status_code == 200, r.text
    return len(r.json().get("ideas", []))


# ---------------------------------------------------------------------------
# Non-detection: casual and definition-lookup turns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("message", [
    "hi there",
    "thanks for that",
    "what is PRISMA?",
    "/popper",
])
def test_mundane_turns_do_not_emit_idea_candidate(client, message):
    with client.stream("POST", "/api/chat/stream", json={
        "message": message,
        "session_id": "s2-mundane",
    }) as r:
        events = _read_sse(r)
    assert "idea_candidate" not in _kinds(events), (
        f"mundane turn {message!r} wrongly emitted idea_candidate; kinds={_kinds(events)}"
    )


# ---------------------------------------------------------------------------
# Detection: a sharp observation emits a well-formed candidate
# ---------------------------------------------------------------------------


def test_sharp_observation_emits_candidate_without_persisting(client):
    assert _count_ideas(client) == 0

    with client.stream("POST", "/api/chat/stream", json={
        "message": "rural anemia rates are higher despite similar iron intake — why?",
        "session_id": "s2-detect",
        "step_accept": {"step": "scan"},  # docs/features/01: plans come from an accepted offer
    }) as r:
        events = _read_sse(r)

    kinds = _kinds(events)
    assert "idea_candidate" in kinds, f"detector failed to fire: {kinds}"

    cand_event = next(e for e in events if e.get("event") == "idea_candidate")
    cand = cand_event["payload"]["candidate"]
    assert cand["title"]
    assert cand["hypothesis"]
    assert cand["rationale"]
    assert cand["trigger"]  # one of the five vision triggers
    assert cand["status"] == "tentative"
    assert cand_event["payload"].get("requires_approval") is True

    # Vision §3.1: the suggestion must NOT have been persisted.
    assert _count_ideas(client) == 0, "detector persisted an idea without user approval"


# ---------------------------------------------------------------------------
# Promotion: an explicit user action persists an idea atomically.
# ---------------------------------------------------------------------------


def test_idea_promotion_persists_as_promoted(client):
    assert _count_ideas(client) == 0

    with client.stream("POST", "/api/chat/stream", json={
        "message": "promote",
        "session_id": "s2-promote",
        "idea_promotion": {
            "title": "Non-dietary mediator of iron absorption",
            "hypothesis": "Rural anemia prevalence is driven by a non-dietary factor that mediates iron absorption.",
            "rationale": "Observed higher anemia despite comparable iron intake.",
        },
    }) as r:
        events = _read_sse(r)

    kinds = _kinds(events)
    assert "idea_promoted" in kinds, f"promotion did not land: {kinds}"
    assert "error" not in kinds, f"promotion errored: {events}"

    promoted = next(e for e in events if e.get("event") == "idea_promoted")["payload"]["idea"]
    assert promoted["status"] == "PROMOTED"
    assert promoted["title"].startswith("Non-dietary")

    # And the ideas listing now contains exactly one row.
    r = client.get("/api/ideas")
    rows = r.json().get("ideas", [])
    assert len(rows) == 1
    assert rows[0]["status"] == "PROMOTED"


def test_idea_promotion_without_required_fields_is_rejected(client):
    assert _count_ideas(client) == 0

    with client.stream("POST", "/api/chat/stream", json={
        "message": "promote",
        "session_id": "s2-reject",
        "idea_promotion": {"title": "", "hypothesis": ""},
    }) as r:
        events = _read_sse(r)

    kinds = _kinds(events)
    assert "error" in kinds, f"expected error, got {kinds}"
    assert "idea_promoted" not in kinds
    assert _count_ideas(client) == 0


# ---------------------------------------------------------------------------
# Independence: detection and plan approval are separate user actions.
# ---------------------------------------------------------------------------


def test_approving_plan_does_not_auto_promote_detected_idea(client):
    """A plan approval approves the brief, not the idea candidate. Vision §3.1."""
    assert _count_ideas(client) == 0

    with client.stream("POST", "/api/chat/stream", json={
        "message": "what if ribosome stalling drives neurodegeneration in these aging mutants?",
        "session_id": "s2-indep",
        "step_accept": {"step": "scan"},  # docs/features/01: plans come from an accepted offer
    }) as r:
        prep = _read_sse(r)
    assert "idea_candidate" in _kinds(prep), "detector did not fire on 'what if' phrasing"
    brief = next(e for e in prep if e.get("event") == "plan_pending")["payload"]["brief"]
    bid, bv = brief["brief_id"], brief["version"]

    # No ideas yet.
    assert _count_ideas(client) == 0

    # Approve the plan only.
    with client.stream("POST", "/api/chat/stream", json={
        "message": "go",
        "session_id": "s2-indep",
        "approval": {"brief_id": bid, "approved_version": bv},
    }) as r:
        approval_events = _read_sse(r, max_events=40, max_seconds=25)

    assert "approval_recorded" in _kinds(approval_events)
    # Still no idea persisted — approval must not silently promote.
    assert _count_ideas(client) == 0, "plan approval wrongly auto-promoted the detected idea"
