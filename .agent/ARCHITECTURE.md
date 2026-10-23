# Thoth — Architecture Pointer

Full and current architecture lives in `/CLAUDE.md` §4. Short reference:

## Unified request lifecycle (post Phase 2)

```
User → POST /api/chat/stream (the only user-facing chat endpoint)
         │
         ▼
backend/api/routes_chat.py — _classify_turn()
   precedence (highest → lowest):
     idea_promotion → _run_idea_promotion         (Phase 2)
     approval       → _run_approval_response       (Phase 1)
     brief approved → _run_pipeline                (Phase 1)
     is_casual_query→ _run_casual                  (Phase 1)
     clarifier fires→ _run_clarification           (Phase 1)
     default        → _run_research_intent         (Phases 1, 2)
         │
         ▼
_run_research_intent runs the Phase 2 detector first
   (emits idea_candidate if a vision §4.1 trigger fires)
then prepare_research_brief → plan_pending (PENDING_APPROVAL).

Later turns with approval={brief_id, approved_version}:
   approve_research_brief → task_manager.register_task →
   stream_research_pipeline (orchestrator FSM: PLAN → SEARCH →
   SNOWBALL → SCRAPE → PRISMA → DRAFT → TRUTH_GUARD → CRITIC →
   [REPLAN?] → MINDMAP → VAULT → FOLLOW_UP → COMPLETE).
```

Phase 3 will split PRISMA into scan-first + formal-review-on-approval.

## Thinker frameworks

10 dirs under `backend/intellectual_rigour/frameworks/`. Loaded dynamically
from `thinkers.yaml` via `importlib.import_module`. **Not yet called by
the research pipeline** — reached only via `/api/brainstorm/*` and slash
commands on followups. Phase 4 wires them in.

## Dead code (confirmed in A4)

- `backend/models/schemas.py` — zero importers; routers inline their own.
- `backend/repositories/*_repo.py` — zero importers; routers go direct to `backend/memory/db.py`.
- `backend/core/rate_limit.py` — not wired; no in-process rate limiting today.

## Deployed topology (per architecture docs, unverified past boot)

- **Frontend:** static SPA served by Nginx on Railway (one textarea, no modes).
- **Backend:** FastAPI/Uvicorn on Railway.
- **Auth + DB:** Supabase (GoTrue, Postgres with RLS, pgvector) — optional
  for dev (SQLite fallback works end-to-end).
- **Cache:** Redis — optional (in-memory fail-open works end-to-end).
- **LLM:** NVIDIA → Groq → OpenAI via `FallbackLLMWrapper`.
