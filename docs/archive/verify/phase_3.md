# Phase 3 — Lightweight scan first, formal PRISMA on approval (+ PoC slices of 4/5/6/9)

**Date:** 2026-10-23
**Vision anchors:** `THOTH/THOTH.docx` §5.4, §5.5 (primary); proof-of-concept slices of §6.3/§6.4 (thinkers), §4 (originality), §8.1–§8.3 (status, PDF), §10 (effort before approval).
**Gate:** `backend/tests/scenarios/test_s3_lightweight_scan_then_formal.py` (5 tests) plus S1 and S2.
**Demo script:** `docs/DEMO.md`.

## Walkthrough from the user's seat (observed live, real APIs, 23 Oct 2026)

1. The user types *"Why do night-shift nurses report more burnout despite similar workloads?"* on the landing page.
   The browser shows an **idea candidate** card (contradiction trigger) and a **plan card**:
   *Mode: Lightweight literature scan (v1)*, *Estimated effort: up to 20 papers (abstracts only) · no full texts · ~4–8 LLM calls · 1–4 min*, plus an **Approve this plan** button.
2. **Approve** → `approval_recorded` → `approval_verified` → search (17 sources) →
   **Lightweight scan: 17 papers (cap 20)**, each labelled `abstract_only` / `title_only`, with the note that no full texts, snowballing or screening counts were involved.
3. **Recommend formal review** appears because 2 potentially disconfirming papers surfaced. It shows the extra effort and starts nothing.
4. Writer → verifier → critic (max one revision in scan mode) → **thinker perspective** (Hume on a causal question; advisory, no veto) → **originality** (`substantially_covered` for an anaemia question with 15 adjacent-field results; lists closest prior work and limits) → **Report status: PROVISIONAL** with explicit gaps → follow-ups → manuscript.
   Scan run: **1 min 53 s** live.
5. *"ok this is serious, run a formal review"* → brief **v2**, `review_mode=formal`, `PENDING_APPROVAL`, formal effort estimate. The v1 approval is **rejected** (`approval_rejected`). Approving v2 runs **search → snowball → scrape → prisma** → write/verify loop → thinker → originality → status (observed live).

## What changed

| File | Change |
|---|---|
| `backend/intellectual_rigour/lightweight_scan.py` (new) | Bounded scan summary (≤20 papers, reading-depth labels), maturity signals, formal-review recommendation and effort figures. |
| `backend/intellectual_rigour/originality.py` (new) | `generate_adjacent_queries`, `assess_originality` with four verdicts; `likely_novel` impossible without adjacent-field results. |
| `backend/intellectual_rigour/thinker_hook.py` (new) | `invoke_thinker_when_useful`: heuristic matcher, or Hume for causal questions; framework review; severity mapped to the §6.4 gate; never blocking. |
| `backend/reports/status.py` (new) | Claim labels (supported / contradicted / uncertain / insufficiently_assessed) and `provisional \| fully_reviewed` with listed gaps. Scan-only output is always provisional. |
| `backend/orchestrator.py` | Scan branch replaces the unconditional snowball → scrape → PRISMA unless `brief.review_mode == "formal"`. New rigour passes before vault persistence. |
| `backend/conversation/brief.py`, `backend/memory/db.py`, `db/migrations/005_review_mode.sql` | `review_mode` field (default `scan`), persisted in SQLite and Postgres. Changing it bumps the version, which invalidates earlier approval. |
| `backend/api/routes_chat.py` | `formal_review_request` turn ("run a formal review" + `brief_id`); `cost_estimate` on every `plan_pending`. |
| `frontend/js/app.js`, `frontend/index.html` | See "pre-existing bugs" below, plus approve button, `approve` reply, formal-review routing, and cards for `scan_result`, `recommend_formal_review`, `prisma`, `thinker_perspective`, `originality_assessment`, `report_status`, final report and follow-ups. The landing "Investigate" box now uses the unified chat instead of legacy mode lanes. |
| `backend/tests/scenarios/conftest.py` | Stub fixed: the pipeline's `search_scholarly_sources` is awaited, so it now gets an async stub. Snowball/citation fetchers are also stubbed. |

## Pre-existing bugs found and fixed (Phases 1–2 frontend never rendered in a browser)

The S1/S2 scenarios test only the backend, so these were invisible:

1. `appendAssistantMessage` was called 31 times but **never defined**, so every chat card threw.
2. The SSE parser split on `\n\n`, but sse-starlette emits `\r\n`, so **no event was ever parsed**.
3. `index.html` hard-coded `API_BASE_URL` to the Railway production backend, so a locally served UI talked to production. It now uses same-origin on localhost.
4. The plan card said "reply approve", but there was no approve handler or button.

## Not done (honest scope)

- `routes_prisma.py` direct-trigger endpoints are not yet gated on an approved formal brief.
- Thinkers fire only at the critical-review stage, not during brainstorming or hypothesis work.
- Effort estimates are fixed ranges, not metered costs (Phase 9 proper).
- No browser-level scenario test. A Playwright check of the card rendering would have caught the four bugs above.
- Phases 7 (project-scoped storage), 8 (feasibility) and 10 (deployment ADR) are not started.
