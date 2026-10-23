# Thoth — Honest Baseline

**Date:** 2026-10-23
**Governing spec:** `THOTH.docx` (15 Oct 2026, v1.0) — the only trusted document.
**Audit evidence:** `A1_boot.md`, `A2_test_truth_table.md`, `A3_endpoint_truth_table.md`, `A4_reachable_modules.md`, `A5_vision_vs_running_system.md`, `A6_infra.md`.
**Audience:** the project owner. Target reading time: five minutes.

---

## 0. Framing (read before anything else)

**The engine returning 200s is not the same thing as the system working.**

Phase 0 measured what the code does at the request layer: endpoints respond,
SSE events emit, the FSM traverses, the circuit breaker trips. That is
engineering health, not product health.

**`THOTH.docx` is a specification of the user experience, not the code graph.**
The only measure that counts is: does a researcher opening Thoth, following their
own curiosity, actually get the journey §3 describes? Today they do not — the
frontend forces mode choices the vision rejects, there is no auto-detection of
a promising direction, PRISMA fires on every request instead of staying
lightweight, thinkers never surface during research, reports are rendered as
binary complete/incomplete.

A clean 200 on `/api/research/stream` does not refute any of that. **Do not let
any later phase's acceptance criterion reduce to 'the code works' — the
criterion is 'a user living the vision §3 journey experiences the vision §3
journey'.** Every phase ends with a walkthrough from a user's seat, not a
walkthrough from the server's.

The baseline below is useful anyway, because it tells us *how much of the
scaffolding we can reuse* on the way to that experience. It does not tell us
the product is close to done. It is not.

---

## 1. What actually works

Observed behaviours, with evidence.

- **Backend boots clean, SQLite-only, zero API keys.** `/health` 200. `/ready` 200, honestly reports `database:"sqlite_local"` + `redis:"memory_fallback"`. Clean lifespan start and shutdown. (A1)
- **Approval gate on the main research path is real.** `POST /api/research/stream` with just a `topic` emits an `approval_barrier` SSE event and `complete`, no pipeline fires. Prepare → approve → stream launches `approval_verified` → full FSM execution (SEARCH → WRITER → …) through to `complete`. Dispatcher trips its circuit breaker on 5 consecutive failures as designed. (A3)
- **Durable task lifecycle.** `research_tasks` table + atomic SQLite claims + orphan reconciliation at lifespan start. Verified in A1 (clean reconcile message) and A3 (real `task_id` emitted into SSE).
- **Brief lifecycle: prepare → persist → fetch → approve → mark APPROVED with version seal.** All endpoints round-trip cleanly. (A3)
- **Idea lifecycle: `TENTATIVE → PROMOTED → REVISED → ABANDONED` with lineage.** `research_ideas` table, revise/abandon/history endpoints — all 201 / 200 verified in A3.
- **Ingestion honesty.** `IngestionResult.extraction_quality` ∈ `{full | partial | snippet_only | inaccessible | empty | unsupported}` propagates end-to-end to the integrity gate's bibliography, which appends an honest badge. No upgrade path exists in code. (Explore, A4)
- **Truth Guard entailment checks.** `integrity_gate.evaluate_claim_support` + `audit_report_integrity` implement overgeneralization, direction inversion, causal leap, and predicate drift. Lazy-imported from `pipeline.py:959`. (A4)
- **Fail-open discipline.** Redis down → in-memory. Supabase absent → SQLite. NVIDIA unreachable → Groq → OpenAI; or heuristic for the thinker matcher. (A6)
- **70 registered routes.** Idea, brief, PRISMA, workspace, manuscripts, journal presets, vault, sessions, reports — all respond, mostly with empty collections from the clean DB. (A3)
- **Thinker frameworks are loadable.** `/api/brainstorm/thinkers` returns all 10 from `thinkers.yaml`. Classes load via `importlib.import_module` from the registry. (A3, A4)
- **PRISMA engine, snowball, clustering, journal formatter, dual-engine PDF compiler.** All reachable via lazy imports from `routes_prisma.py` / `routes_workspace.py`. Not yet exercised live for a complete run — no real research API output in this baseline — but the import graph and route surface are intact. (A4)

## 2. What is genuinely broken

- **Zero pytest test suites exist.** The last commit on `main` (`606da82 feat(working-model): ... and remove test suites`) deleted the entire `backend/tests/` directory. The `Makefile`'s `test:` target lists 20 files, none of which exist on disk. The "520 passing tests" claim in `docs/roadmap-status.md`, the "223 passed" badge in `README.md`, and the "308 passed" claim in `THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md` are all historical, not current. **The repository has no automated verification layer today.** (A2)
- **`POST /api/followup/stream` with `state=None` crashes.** `'NoneType' object has no attribute 'get'`. Vision §10 ("Allow users to steer, pause, redirect, or abandon") depends on this path. One-line guard required. (A3)
- **`POST /api/projects` schema mismatch.** Endpoint expects `title`; natural call uses `name`. Returns 422. Low-severity but a real contract bug. (A3)
- **Default `REDIS_URL` in `.env.example` points at a dead hosted instance.** Noisy warnings on every fresh boot. Trivial fix. (A6)

## 3. Aspirational scaffolding — present on disk, not reached from the running system

Candidates for either archive or revival in later phases.

- **`backend/models/schemas.py`.** Zero importers under `backend/`. Routers inline their Pydantic classes. The declared contracts here are unused. (A4)
- **`backend/repositories/{report_repo, session_repo, vault_repo}.py`.** Zero importers. Every router skipped the repo abstraction and talks directly to `backend/memory/db.py`. The pattern was planned, not adopted. (A4)
- **`backend/core/rate_limit.py`.** Zero importers. Despite the architecture docs' token-bucket claims, no rate limiting is enforced in-process. Resolve during Phase 10 deployment-model work. (A4)
- **`backend/eval/{datasets, judge_model, logical_integrity, metrics, runner}.py`.** Internal helpers for `backend/evals/*` benchmarks; not part of the request-serving graph. Keep as eval support, not production code. (A4)

## 4. The vision gap, in one picture

From A5, mapped to the ten §3 journey stages:

| § Stage | Status | Plan phase |
|---|---|---|
| 1. Open conversation | DIVERGES (UX modes impose lanes) | 1 |
| 2. Recognise a promising direction | MISSING (no auto-detection) | 2 |
| 3. Prepare without blocking | MOSTLY WORKS | 1 (UX frame) |
| 4. Seek approval | WORKS (one bypass to close) | 1 |
| 5. Brainstorm with thinkers | DIVERGES (thinkers severed from pipeline) | 4 |
| 6. Lightweight scan vs formal PRISMA | DIVERGES (always runs full PRISMA) | 3 |
| 7. Return to brainstorming | PARTIALLY WORKS (null-state crash) | 1 |
| 8. Refine one main hypothesis | MOSTLY WORKS (no explicit guard) | monitor |
| 9. Design the study | MISSING (no feasibility probe) | 8 |
| 10. Reports & manuscript | DIVERGES (binary status; PDF without approval) | 5 |

Off-journey vision gaps:

- **§4** Originality assessment with adjacent-field search → **Phase 6**.
- **§9.1** Project-scoped paper storage → **Phase 7**.
- **§10** Resource-awareness surface → **Phase 9**.
- **§12** Deployment model decision → **Phase 10**.

## 5. What this means in plain words

The owner's statement "the project doesn't work at all" was **directionally right about the user experience** and **wrong about the engine underneath**:

- The **engine** is more alive than the status docs made it sound. Approval gating, task lifecycle, ingestion honesty, truth guard, PRISMA engine, manuscript revisions, dual-engine PDF, 10 thinker frameworks, snowball + clustering, Supabase + Redis fail-open — all have real code behind them and most are reachable from a request.
- The **user journey** per `THOTH.docx` §3 is partial. The frontend forces mode choices the vision rejects. Thinkers are isolated from research. PRISMA runs full on every request instead of staying lightweight until escalation. Idea capture is manual. Study feasibility is unverified. Report status is binary. Originality is not independently assessed.
- The **verification layer is gone.** No pytest. No automated gate. Every public status claim about test counts is stale. **This is the single most dangerous aspect of the current state** — any future change ships without a safety net.

## 6. First concrete actions (translating this into Phase 1 start)

Order matters.

1. **Reinstate a test harness before any behavioural change.** The plan's `backend/tests/scenarios/*` convention is the first test home. `make test` becomes `make test-vision`; the old target either delegates or is removed. No code change ships without a scenario test.
2. **Fix the three small bugs flagged in §2 above** as part of Phase 1's chat router migration — they're on the hot path for any UX work:
   - follow-up `state=None` guard;
   - `/api/projects` body contract;
   - `.env.example` `REDIS_URL` default.
3. **Begin Phase 1 proper** — collapse the frontend to one surface, build `backend/api/routes_chat.py`, retire the `fast_chat` bypass, deprecate `/api/research/stream` + `/api/followup/stream`.
4. **Do not amend the stale status docs** (`roadmap-status.md`, `THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md`, `README.md`). Leave them as historical artefacts per `CLAUDE.md` §0 and `docs/SYSTEM_STATE.md`. Future state lives in `SYSTEM_STATE.md` + these verify notes only.

Phase 0 is done.
