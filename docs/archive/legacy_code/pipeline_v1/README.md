# pipeline_v1: the retired plan-and-pipeline path (archived 25 Oct 2026)

Before the redesign (docs/features/), a substantive chat message became a research brief. You approved
it, and an FSM pipeline (`orchestrator.py` + `pipeline.py`) ran a lightweight scan or a formal PRISMA
review and wrote a synthesis report. The redesign replaced it:

| Old | Replaced by |
|---|---|
| Brief → approval → `stream_research_pipeline` (scan / formal) | The trial (`backend/research/trial.py`) and the systematic review (`backend/research/review.py`), each with its own plan and approval |
| Heuristic idea detector (`conversation/idea_detector.py`) | The conductor's notebook proposals (`conversation/conductor.py`) |
| `/api/research`, `/api/followup`, `/api/brainstorm`, `/api/ideas`, `/api/prisma`, `/api/vault` | `/api/chat/stream`, `/api/thinkers`, `/api/trial`, `/api/review`, `/api/design`, `/api/proposal` |
| `intellectual_rigour/` lightweight_scan, originality, prisma, snowball, clustering, thinker_hook; `reports/status.py` | The trial's Judge and the review's PRISMA counts |
| `frontend/lib`, `frontend/components` (Supabase auth modal) | Nothing: the UI never imported them |
| `models/schemas.py`, `repositories/*_repo.py`, `core/auth.py`, `core/rate_limit.py` | Nothing: no importers left |
| Evaluation suites `backend/eval`, `backend/evals`, `scripts/eval`, `scripts/dev/diagnostic_test.py` | Measured the old pipeline; the gate is `backend/tests/scenarios/` |
| Scenario tests S1, S2, S3 | S19 (`test_s19_ui_surface_after_retirement.py`); still-valid guarantees moved there and to S10 |

`backend/api/routes_chat.py` here is the full pre-retirement router. The live one keeps only conductor
turns, explicit idea promotion and proposal resolution. The old request shapes (`approval`,
`step_accept`, `brief_id`) now get an honest "retired" error.

Files keep their original relative paths. Nothing here is imported by the app.
