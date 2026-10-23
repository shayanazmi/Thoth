"""
Scenario S3 — Lightweight scan first, formal PRISMA only on approval.

Vision anchor: THOTH.docx §5.4 (plus §10 effort shown before approval,
§4 originality guardrail, §8.3 provisional status).
Phase: 3.

Covers:
  - A fresh research plan defaults to review_mode="scan" and its approval
    card carries a cost estimate.
  - Approving it runs the lightweight scan: a `scan_result` event labelled
    abstract-only, and no `prisma` event.
  - "run a formal review" on that brief creates a NEW brief version with
    review_mode="formal" that needs its own approval; the old approval
    cannot launch it.
  - Originality can never be `likely_novel` without adjacent-field results.
  - A scan-only report is always `provisional`.
"""
from __future__ import annotations

from backend.tests.scenarios.test_s2_idea_detect_suggest_promote import _read_sse, client  # noqa: F401

OBSERVATION = "rural anemia rates are higher despite similar iron intake — why?"


def _events(client, body, max_seconds=20):
    with client.stream("POST", "/api/chat/stream", json=body) as resp:
        assert resp.status_code == 200
        return _read_sse(resp, max_events=200, max_seconds=max_seconds)


def _plan(events):
    plans = [e for e in events if e.get("event") == "plan_pending"]
    assert plans, [e.get("event") for e in events]
    return plans[-1]["payload"]


def test_plan_defaults_to_scan_with_cost_estimate(client):
    plan = _plan(_events(client, {"message": OBSERVATION, "session_id": "s3-a"}))
    assert plan["brief"]["review_mode"] == "scan"
    assert plan["cost_estimate"]["review_mode"] == "scan"
    assert plan["cost_estimate"]["full_text_attempts"] == "none"


def test_scan_phase_is_bounded_labelled_and_skips_prisma():
    """The orchestrator's scan branch: <=20 papers, abstract-level labels, no
    full-text upgrade, a formal-review recommendation, and no PRISMA ledger.
    (The full live path is exercised in docs/archive/verify/phase_3.md.)"""
    from backend.orchestrator import _run_scan_phase

    sources = [
        {"title": f"Paper {i}", "abstract": "night shift burnout", "url": f"https://x/{i}",
         "extraction_quality": "full", "relation": "counter_evidence" if i == 0 else None}
        for i in range(25)
    ]
    state = {
        "cumulative_sources": sources,
        "max_retries": 2,
        "brief": {"brief_id": "b1", "review_mode": "scan", "hypotheses": ["h"], "falsification_criteria": ["f"]},
    }
    events = list(_run_scan_phase(state))
    names = [e[0] for e in events]
    assert names == ["scan_result", "recommend_formal_review"], names
    scan = events[0][1]
    assert scan["kind"] == "lightweight_scan" and scan["paper_count"] == 20
    assert all(p["reading_depth"] == "abstract_only" for p in scan["papers"])
    # Never upgrade: only abstracts were seen, so nothing may stay labelled "full".
    assert all(s["extraction_quality"] == "snippet_only" for s in state["cumulative_sources"])
    assert state["max_retries"] == 1
    assert "prisma_review" not in state


def test_formal_review_needs_its_own_approval(client):
    brief = _plan(_events(client, {"message": OBSERVATION, "session_id": "s3-c"}))["brief"]

    formal = _plan(_events(client, {
        "message": "this is serious now, run a formal review",
        "session_id": "s3-c",
        "brief_id": brief["brief_id"],
    }))
    assert formal["brief"]["review_mode"] == "formal"
    assert formal["brief"]["version"] == brief["version"] + 1
    assert formal["brief"]["approval_status"] == "PENDING_APPROVAL"
    assert formal["cost_estimate"]["review_mode"] == "formal"

    # Approving the stale scan version must not launch the formal review.
    stale = _events(client, {
        "session_id": "s3-c",
        "approval": {"brief_id": brief["brief_id"], "approved_version": brief["version"]},
    })
    names = [e.get("event") for e in stale]
    assert "approval_rejected" in names and "approval_verified" not in names, names


def test_originality_never_likely_novel_without_adjacent_search():
    from backend.intellectual_rigour.originality import assess_originality

    result = assess_originality(
        "iron absorption inhibitors in rural diets explain anemia gaps",
        primary_sources=[{"title": "Unrelated paper on astronomy", "abstract": "galaxies"}],
        adjacent_sources=[],
        adjacent_queries_run=[],
    )
    assert result["verdict"] != "likely_novel"


def test_scan_only_report_is_provisional():
    from backend.reports.status import compute_report_status

    status = compute_report_status({
        "is_verified": True,
        "integrity_result": {"claims": [{"claim": "x", "verification_status": "DIRECTLY_SUPPORTED"}]},
        "brief": {"review_mode": "scan"},
    })
    assert status["report_status"] == "provisional"
    assert any("Lightweight scan" in g for g in status["gaps"])


def test_mentioning_prisma_does_not_escalate(client):
    """A side question about PRISMA must not silently turn the plan into a formal review."""
    brief = _plan(_events(client, {"message": OBSERVATION, "session_id": "s3-d"}))["brief"]
    events = _events(client, {
        "message": "quick aside - what does PRISMA stand for?",
        "session_id": "s3-d",
        "brief_id": brief["brief_id"],
    })
    kinds = [e["payload"].get("kind") for e in events if e.get("event") == "turn_start"]
    assert "formal_review_request" not in kinds, kinds
