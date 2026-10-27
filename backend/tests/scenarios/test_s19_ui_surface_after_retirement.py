"""
S19 · The UI still works after the legacy pipeline was retired (25 Oct 2026).

The old plan-and-pipeline path (orchestrator, pipeline, its "scan" offer, six old routers, the idea
detector, frontend/lib and frontend/components) now lives in docs/archive/legacy_code/pipeline_v1/.

User-seat criteria encoded here:
  - Every endpoint the browser UI calls is still served, and the UI shell and its modules load.
  - The retired routes are gone, and nothing in the UI refers to them or to the archived folders.
  - The chat still talks: an ordinary message gets a reply and completes.
  - The old plan / approval / scan request shapes start nothing; they get an honest "retired" error.
  - The conductor only offers work that the UI can run (the trial, the systematic review).
  - An idea is still kept only when the user explicitly asks for it.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from backend.tests.scenarios.conftest import kinds, read_sse

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"
ARCHIVE = ROOT / "docs" / "archive" / "legacy_code" / "pipeline_v1"
RETIRED_PREFIXES = ("/api/research", "/api/followup", "/api/brainstorm", "/api/ideas", "/api/prisma", "/api/vault")
RETIRED_MODULES = (
    "backend.orchestrator", "backend.pipeline", "backend.models.schemas",
    "backend.api.routes_research", "backend.api.routes_followup", "backend.api.routes_brainstorm",
    "backend.api.routes_ideas", "backend.api.routes_prisma", "backend.api.routes_vault",
    "backend.conversation.idea_detector", "backend.intellectual_rigour.lightweight_scan",
    "backend.intellectual_rigour.thinker_hook", "backend.core.auth", "backend.core.rate_limit",
)


def _ui_sources():
    files = sorted((FRONTEND / "js").glob("*.js")) + sorted((FRONTEND / "scripted").glob("*.js"))
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def _ui_api_paths():
    """Every /api/... path literal the UI builds, with ${…} placeholders as one path segment."""
    paths = set()
    for src in _ui_sources().values():
        for m in re.finditer(r"""['"`](/api/[^'"`?]*)""", src):
            p = re.sub(r"\$\{[^}]*\}", "X", m.group(1)).rstrip("/")
            if p != "/api":
                paths.add(p)
    return paths


def _route_regex(path):
    return re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path.rstrip("/")) + "$")


def _served_api_paths(app):
    # Routers are mounted lazily in this FastAPI version; the OpenAPI schema lists every served path.
    return list(app.openapi()["paths"].keys())


def test_every_endpoint_the_ui_calls_is_served(client):
    routes = _served_api_paths(client.app)
    patterns = [_route_regex(r) for r in routes]
    ui_paths = _ui_api_paths()
    assert len(ui_paths) >= 20, ui_paths  # the scan found the UI's calls, not nothing
    # A ${…} in the UI may stand for a literal segment too (e.g. sections/${key}/${action}).
    ui_rx = lambda p: re.compile("^" + "/".join("[^/]+" if seg == "X" else re.escape(seg) for seg in p.split("/")) + "$")
    filled = [re.sub(r"\{[^}]+\}", "X", r) for r in routes]
    missing = sorted(p for p in ui_paths
                     if not any(rx.match(p) for rx in patterns) and not any(ui_rx(p).match(r) for r in filled))
    assert not missing, f"the UI calls endpoints the server no longer serves: {missing}"


def test_ui_shell_and_modules_load(client):
    home = client.get("/")
    assert home.status_code == 200 and "/js/main.js" in home.text
    for name in ("main", "chat", "store", "api", "workspace", "trial", "review", "design", "proposal", "thinkers", "intro-cinema", "motion"):
        r = client.get(f"/js/{name}.js")
        assert r.status_code == 200, name
    for sheet in ("tokens", "app", "folio", "motion"):
        assert client.get(f"/styles/{sheet}.css").status_code == 200, sheet


def test_retired_routes_are_gone_and_unreferenced(client):
    served = _served_api_paths(client.app)
    assert not [p for p in served if p.startswith(RETIRED_PREFIXES)], "a retired router is still mounted"
    assert client.post("/api/research/stream", json={"topic": "x"}).status_code == 404
    for name, src in _ui_sources().items():
        for prefix in RETIRED_PREFIXES:
            assert prefix not in src, f"{name} still calls {prefix}"
        assert "/lib/" not in src and "/components/" not in src, f"{name} imports an archived frontend folder"
        assert "step_accept" not in src, f"{name} still sends the retired step_accept turn"
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "/lib/" not in html and "/components/" not in html
    assert not (FRONTEND / "lib").exists() and not (FRONTEND / "components").exists()


def test_legacy_code_is_archived_not_importable():
    for mod in RETIRED_MODULES:
        try:
            spec = importlib.util.find_spec(mod)
        except ModuleNotFoundError:  # the parent package itself is gone (backend.models)
            spec = None
        assert spec is None, f"{mod} is still importable"
    for rel in ("backend/orchestrator.py", "backend/pipeline.py", "backend/api/routes_research.py", "frontend/lib", "frontend/components"):
        assert (ARCHIVE / rel).exists(), f"{rel} missing from the archive (history must be preserved)"


def test_ordinary_message_still_gets_a_reply(client):
    with client.stream("POST", "/api/chat/stream", json={"message": "why do night nurses seem to slip near dawn?", "project_id": "p19a"}) as r:
        assert r.status_code == 200
        events = read_sse(r, max_events=20, max_seconds=15)
    ks = kinds(events)
    assert "direct_answer" in ks and ks[-1] == "complete", ks
    assert "error" not in ks, events


@pytest.mark.parametrize("shape", [
    {"approval": {"brief_id": "b1", "approved_version": 1}},
    {"step_accept": {"step": "scan", "topic": "night nurses"}},
    {"message": "run a formal review", "brief_id": "b1"},
])
def test_retired_request_shapes_start_nothing(client, shape):
    with client.stream("POST", "/api/chat/stream", json={"session_id": "p19b", **shape}) as r:
        events = read_sse(r, max_events=10, max_seconds=10)
    ks = kinds(events)
    assert ks == ["error", "complete"], ks
    assert events[0]["payload"].get("retired") is True
    for banned in ("plan_pending", "approval_verified", "approval_recorded", "search", "writer"):
        assert banned not in ks


def test_conductor_only_offers_work_the_ui_can_run():
    from backend.conversation import conductor
    assert set(conductor.OFFERABLE_STEPS) == {"trial", "systematic_review"}
    assert "scan" not in conductor.STEP_ESTIMATES
    chat_js = (FRONTEND / "js" / "chat.js").read_text(encoding="utf-8")
    assert "startTrial" in chat_js and "startSystematicReview" in chat_js


def test_idea_is_kept_only_on_explicit_promotion(client):
    from backend.conversation.idea import list_ideas
    assert list_ideas() == []
    with client.stream("POST", "/api/chat/stream", json={"session_id": "p19c", "idea_promotion": {"title": "", "hypothesis": ""}}) as r:
        assert "error" in kinds(read_sse(r))
    assert list_ideas() == [], "an incomplete promotion must not persist anything"
    with client.stream("POST", "/api/chat/stream", json={"session_id": "p19c", "idea_promotion": {
            "title": "End-of-shift errors", "hypothesis": "Errors rise in the last two hours of a night shift.", "rationale": "observed"}}) as r:
        events = read_sse(r)
    assert "idea_promoted" in kinds(events), events
    ideas = list_ideas()
    assert len(ideas) == 1 and ideas[0].title == "End-of-shift errors"
