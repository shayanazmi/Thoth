# CLAUDE.md — Thoth Working Context

> **Read this file in full before touching anything.** It is the single
> primary context for any Claude session working on Thoth, whether in
> claude.ai or Claude Code CLI. If this file conflicts with any other
> document in the repository, this file and `THOTH.docx` win.

---

## 0. What counts as "working"

`THOTH.docx` specifies a **user experience**, not a code graph. The only
evidence that Thoth works is a user living the vision §3 journey and
experiencing the vision §3 journey. Endpoints returning 200, SSE events
emitting, tests passing, FSMs traversing — none of that counts on its own.
A session where every call succeeds and the user still gets a mode-toggle
UI, an unprompted PRISMA review, a report labelled "complete" with no
status surface, and no thinker in sight is a **failing session** no matter
how green the logs are.

**Every phase's acceptance criterion is a walkthrough from the user's seat.**
A server-side probe is a debugging aid; it is never evidence that a phase is
done.

---

## 0b. Ground truth and trust model

There is exactly **one** trusted document in this repository:

- **`THOTH/THOTH.docx`** (also attached to the claude.ai project)
  — the product vision, 15 Oct 2026, v1.0.

Everything else is **untrusted** until independently verified:

- `README.md` — marketing copy; claims features that may not run.
- `docs/roadmap-status.md` — a phase ledger claiming Phases 0–7 shipped
  and 520 passing tests. **Historical.** The last commit on `main`
  (`606da82 feat(working-model): ... and remove test suites`) wiped the
  entire `backend/tests/` directory. The 520-test claim refers to a
  prior state that no longer exists on disk.
- `THOTH/THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md` — written against those
  same unverified claims. Useful as a *map of the code*, not as a
  statement of behaviour.
- `docs/architecture.md`, `docs/*.md`, `docs/decisions/ADR-*.md` — the
  design the authors *intended*, not necessarily what the code does.
- Any inline comment, docstring, or log line asserting behaviour. The
  code may say "server-enforced approval gate"; whether a specific path
  can bypass it is an empirical question answered by `docs/archive/verify/`.

**Working rule:** before relying on any claim about Thoth's behaviour,
confirm it one of three ways:

1. Run the relevant code path end-to-end and observe the actual output.
2. Read the implementation and trace it through — not just the test that
   asserts it, since legacy tests may have been mocked around the real
   failure surface. (The new scenario tests under `backend/tests/scenarios/`
   are the trustworthy gate.)
3. Ask the project owner.

Do not quote the roadmap, audit, or README to the user as evidence of
anything. Do not re-publish their numbers.

---

## 1. North Star (the only spec)

The product vision is `THOTH.docx`. Short form in the owner's words:

> Thoth should not merely answer questions a researcher already knows how
> to ask. It should help people discover which questions are worth asking,
> understand what existing scholarship establishes, and investigate what
> might meaningfully add to that knowledge.

Thoth is a research **companion**, not a report generator. It fulfils
three roles at the same time, with context flowing freely between them:

1. **Conversational intellectual companion** — curiosity, brainstorming,
   interdisciplinary chatter, no formal research prompt required.
2. **Rigorous research investigator** — discovery, reading, comparison,
   critical appraisal, honest originality assessment.
3. **Research-development partner** — hypothesis refinement, feasible
   study design, evidence-grounded manuscript development.

### Core principles (vision §2)

| Principle | What it forbids | What it enables |
|---|---|---|
| Conversation first | Blocking the UI while research runs | Natural chat while prep happens in parallel |
| Originality over sophistication | Novel-sounding wording as proxy for novelty | Substantive comparison against prior art |
| Evidence before confidence | Confident claims without traceable sources | Visible uncertainty, honest "insufficiently assessed" |
| Depth when it matters | Deep analysis by default on everything | Lightweight scans early, deep passes on demand |
| Simplicity over complexity | Thinkers / agents / variables that serve no purpose | Minimal design that answers the question |
| User agency | Launching formal reviews or expensive compute without approval | Explicit approval gates |
| Technical feasibility | New services for every responsibility | Reusing logical roles pragmatically |
| Resource awareness | Permanent cross-project hoarding; unlimited free compute promises | Project-scoped storage, explicit retention and costs |

### Non-negotiable guardrails (vision §11)

- **Never** fabricate citations, screening counts, source access, methods,
  experiments, results, or claims of originality.
- **Never** present abstract-level inspection as full-text analysis.
- **Never** label a report "complete" when critical evidence or review
  is unresolved — use a provisional status with explicit gaps.
- **Never** declare an idea original solely because a model called it original.
- **Never** manufacture a research gap to justify continuing a project.
- **Never** create PDF exports without explicit user approval.
- A quotation being present in a source is **not** proof it supports the claim.
- Philosophical disagreement alone must not invalidate a report. Severity-
  gated criticism, bounded retries, no single thinker gets veto.

Read the full vision in `THOTH.docx` before making any non-trivial change.

---

## 2. Current state (as of 23 Oct 2026)

Phase 0 (verification baseline), Phase 1 (unified conversational surface),
and Phase 2 (idea capture: detect → suggest → promote) are complete.

### Vision §3 journey scorecard

Five of the ten vision §3 stages are now closed; five remain.

| Stage | Vision §3 | Status | Phase |
|---|---|---|---|
| 1 | Open conversation | **WORKS** | 1 |
| 2 | Recognise a promising direction | **WORKS** | 2 |
| 3 | Prepare without blocking | **WORKS** | 1 |
| 4 | Seek approval for substantial work | **WORKS** | 1 |
| 5 | Brainstorm with thinkers | PARTIAL (thinker fires at critical review) | 4 |
| 6 | Lightweight scan vs formal PRISMA | **WORKS** | 3 |
| 7 | Return to brainstorming | **WORKS** | 1 |
| 8 | Refine one main hypothesis | MOSTLY WORKS | monitor |
| 9 | Design the study | MISSING (no feasibility probe) | 8 |
| 10 | Reports & manuscript | PARTIAL (provisional/fully_reviewed status shown) | 5 |

Off-journey:
- **§4** Originality assessment with adjacent-field search → **Phase 6**.
- **§9.1** Project-scoped paper storage → **Phase 7**.
- **§10** Resource-awareness surface → **Phase 9**.
- **§12** Deployment model decision → **Phase 10**.

### Test gate (the canonical trust signal)

```
$ make test-vision                        # 14/14 scenarios in ~10s (scholarly fetchers stubbed in-test)
$ pytest backend/tests/scenarios/ -v
```

Six S1 (Phase 1) + eight S2 (Phase 2) behavioural tests. Each future
phase adds its own `backend/tests/scenarios/test_sN_*.py` file. The old
`make test` target now aliases `make test-vision`.

### The approved plan

The plan driving the ten phases is saved at **`docs/PLAN.md`** in the
repo. It is phase-structured, vision-anchored, and specifies for each
phase: the vision section it realises, the behavioural change, the
files to touch, the acceptance test.

---

## 3. Repository map (physical, with Phase 1-2 additions marked ⊕)

```
thoth/
├── CLAUDE.md                             ⊕ this file (primary context)
├── THOTH/
│   ├── THOTH.docx                          product vision (the only spec)
│   ├── THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md   UNTRUSTED legacy audit
│   └── thoth_visual_architecture_guide.png
├── README.md                                UNTRUSTED marketing copy
├── Makefile                                ⊕ test target now aliases test-vision
├── main.py                                   ASGI entrypoint → backend.main:app
├── requirements.txt                          -> backend/requirements.txt
├── pytest.ini
├── railway.toml                              root Railway service
├── .env  /  .env.example                     secrets never committed
├── .agents/  .agent/                       ⊕ refreshed pointer files (mirrored)
│
├── backend/
│   ├── main.py                             ⊕ registers chat_router
│   ├── __init__.py                           package public surface
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── railway.toml
│   │
│   ├── api/
│   │   ├── routes_chat.py                  ⊕ NEW — unified /api/chat/stream
│   │   │                                     entrypoint (vision §2, §10)
│   │   ├── routes_research.py                legacy SSE /api/research/stream
│   │   │                                     (still active; retires after Phase 2
│   │   │                                     frontend paths all migrated)
│   │   ├── routes_followup.py              ⊕ null-state crash guarded
│   │   ├── routes_brainstorm.py              thinker sparring endpoints
│   │   ├── routes_ideas.py                   explicit idea lifecycle endpoints
│   │   ├── routes_prisma.py                  PRISMA review protocol + screening
│   │   ├── routes_workspace.py             ⊕ ProjectCreateRequest accepts name alias
│   │   ├── routes_vault.py                   vault notes + graph
│   │   └── routes_health.py                  /health, /ready, /api/status
│   │
│   ├── core/                                 config, auth, cache, rate_limit, errors, logging
│   ├── conversation/
│   │   ├── mandate.py                        ResearchMandate dataclass
│   │   ├── brief.py                          ResearchBrief + ResearchTaskManager
│   │   ├── idea.py                           idea lifecycle (TENTATIVE…ABANDONED)
│   │   ├── idea_detector.py                ⊕ NEW — Phase 2 §3.1 detector
│   │   ├── escalation.py                     detect_escalation_intent
│   │   ├── clarification.py                  evaluate_clarification_need
│   │   └── resolver.py                       continuation / topic-correction / pronoun
│   │
│   ├── intellectual_rigour/
│   │   ├── frameworks/                       10 thinker dirs (dynamic-import via thinkers.yaml)
│   │   ├── thinkers.yaml  registry.py  matcher.py
│   │   ├── attack_surface.py  integrity_gate.py  counter_evidence.py
│   │   ├── prisma.py  snowball.py  clustering.py  sparring.py  synthesis.py
│   │   └── models.py                         ReviewTarget / Request / Finding types
│   │
│   ├── reports/                              sections / patch / validation
│   ├── workspace/                            project / manuscript / exporter /
│   │                                         pdf_compiler / journal_formatter /
│   │                                         traceability
│   ├── collaboration/                        membership (RBAC) + sync (outbox)
│   ├── memory/                               db (SQLite, 24+ tables), graph, index,
│   │                                         session, vault
│   ├── repositories/                         DEAD CODE (zero importers; routers go
│   │                                         direct to memory/db.py) — see A4
│   ├── models/schemas.py                     DEAD CODE (routers inline their own)
│   ├── agents.py                             LLM chain factory + FallbackLLMWrapper
│   ├── scholarly.py                          ArXiv / S2 / OpenAlex / PubMed / Tavily
│   ├── ingestion.py                          pypdf, HTML cleaner, access-quality badges
│   ├── tools.py                              @tool web_search / scrape_url
│   ├── dispatcher.py                         async semaphore + circuit breaker
│   ├── pipeline.py                           LangGraph-style node definitions
│   ├── orchestrator.py                       FSM + stream_research_pipeline
│   ├── telemetry.py                          DeepEval optional tracing
│   ├── eval/   evals/                        internal + external benchmarks
│   └── tests/
│       ├── __init__.py                     ⊕ NEW — package marker + Phase 0 note
│       └── scenarios/                      ⊕ NEW — the canonical test gate
│           ├── __init__.py
│           ├── test_s1_conversation_never_blocks.py        (Phase 1, 6 tests)
│           └── test_s2_idea_detect_suggest_promote.py      (Phase 2, 8 tests)
│
├── frontend/
│   ├── index.html                          ⊕ collapsed to one textarea
│   │                                         (469 → 363 lines; mode UI deleted)
│   ├── js/app.js                           ⊕ sendUnifiedTurn + renderChatEvent
│   │                                         (hits /api/chat/stream)
│   ├── js/animations.js                      unchanged
│   ├── components/auth_modal.js              unchanged
│   ├── styles/   lib/   assets/              unchanged
│   └── Dockerfile  nginx.conf  railway.toml  unchanged
│
├── docs/
│   ├── architecture.md                       UNTRUSTED design intent
│   ├── setup.md  env-vars.md  auth-flow.md
│   ├── database-schema.md  caching.md  deployment.md  api-limits.md
│   ├── runbook.md
│   ├── roadmap-status.md                     UNTRUSTED phase ledger
│   ├── Thoth_Architecture_Suite.{html,pdf}
│   ├── diagrams/   archive/
│   ├── decisions/                            ADR-001..004 (design intent)
│   ├── SYSTEM_STATE.md                     ⊕ live gap + per-phase stamp
│   └── archive/verify/                     ⊕ NEW — honest observations
│       ├── BASELINE.md                       Phase 0 memo (works/broken/aspirational)
│       ├── A1_boot.md .. A6_infra.md         Phase 0 detailed per-step reports
│       ├── phase_1.md                        Phase 1 user-seat walkthrough
│       ├── phase_2.md                        Phase 2 user-seat walkthrough
│       └── _logs/                            raw tool output
│
├── db/migrations/                            Postgres migrations 001..004
├── supabase/   scripts/                      scripts/{dev,db,ops,eval}/
├── vault/                                    Obsidian-style notes (global today;
│                                             project-scoped lands in Phase 7)
├── scratch/                                  throwaway scripts
└── venv/                                     local virtualenv (gitignored; see §5
                                              for the dangling-symlink gotcha)
```

---

## 4. Architecture at a glance (post-Phase 2)

### Unified request lifecycle (one endpoint for the whole conversation)

```
User
  │
  ├── POST /api/chat/stream  ← the only user-facing endpoint for chat
  │       body: {message, session_id, chat_turns?, conversation_summary?,
  │              brief_id?, approval?, idea_promotion?}
  │
  ▼
backend/api/routes_chat.py — _classify_turn()
  │  precedence (highest first):
  │   1. idea_promotion     → _run_idea_promotion       (Phase 2)
  │   2. approval           → _run_approval_response    (Phase 1)
  │   3. brief_id APPROVED  → _run_pipeline             (Phase 1)
  │   4. is_casual_query    → _run_casual               (Phase 1)
  │   5. clarifier fires    → _run_clarification        (Phase 1)
  │   6. default            → _run_research_intent      (Phases 1, 2)
  │
  ▼
_run_research_intent
  │
  ├── detect_promising_direction(…)  (Phase 2, use_llm=False by default)
  │       └─ emits idea_candidate SSE if a trigger fires
  │
  └── prepare_research_brief(…) → emits plan_pending (PENDING_APPROVAL)
  │       (the chat input stays live — vision §2, §10)
  │
  ▼
On a later turn with approval={brief_id, approved_version}:
  │
  _run_approval_response
  │
  ├── approve_research_brief(brief_id, version) → (ok, brief, msg)
  │       └─ emits approval_recorded
  │
  └── _run_pipeline(brief_obj, body)
       │
       ├── task_manager.register_task(…)  (atomic SQLite claim)
       ├── emits approval_verified(task_id)
       │
       └── stream_research_pipeline(…)  from backend.orchestrator
           │  FSM: PLAN → SEARCH → SNOWBALL → SCRAPE → PRISMA →
           │        DRAFT → TRUTH_GUARD → CRITIC → [REPLAN?] →
           │        MINDMAP → VAULT → FOLLOW_UP → COMPLETE
           │  (Phase 3 will split PRISMA into scan-first + formal-review-on-approval)
```

### Typed SSE card contract (what the frontend renders)

Current events emitted by `/api/chat/stream`:

| Event | Phase | Carries |
|---|---|---|
| `turn_start` | 1 | `kind`, optional `message` |
| `direct_answer` | 1 | `answer`, `fallback`, `degraded` |
| `plan_preparing` | 1 | `note` (ephemeral chat affordance) |
| `plan_pending` | 1 | `brief` (full ResearchBrief dict), `requires_approval`, `guidance` |
| `clarification_needed` | 1 | `prompt`, `options` |
| `brief_updated` | 1 | `brief` (post-edit) |
| `approval_recorded` | 1 | `brief_id`, `approved_version`, `message` |
| `approval_rejected` | 1 | `reason` |
| `approval_verified` | 1 | `task_id`, `brief_id`, `version`, `approved_at`, `message` |
| `duplicate_execution_rejected` | 1 | `error` |
| `idea_candidate` | 2 | `candidate` (title / hypothesis / rationale / trigger / trigger_label / score / status="tentative"), `guidance`, `requires_approval` |
| `idea_promoted` | 2 | `idea` (full ResearchIdea dict), `message` |
| Pipeline nodes (`search`, `scrape`, `writer`, `truth_guard`, `critic`, `mindmap`, `vault`, `cancelled`, …) | 1 (passthrough) | node-specific `update` dict |
| `error` | 1 | `error` (sanitized message) |
| `complete` | 1 | `kind` or `task_id` |

### Why this looks like it does

- **Mandate / Brief / Approval** is a three-step barrier so we never
  launch expensive compute without the exact server-validated brief
  version the user signed off on. Any substantive edit bumps `version`
  and invalidates prior approval. See `conversation/brief.py`.
- **Durable task lifecycle** (`research_tasks` table): states
  `QUEUED → CLAIMED → RUNNING → COMPLETED | FAILED | CANCELLED`.
  Startup reconciliation marks orphans `FAILED_ORPHANED`. The chat
  router participates in this lifecycle fully.
- **Ingestion** classifies every source as `full | partial | snippet_only
  | inaccessible | empty | unsupported` and that badge rides along to
  the bibliography. **No upgrade path exists.**
- **Truth Guard** (`integrity_gate.py`) does entailment, not string
  match: four adversarial checks (`overgeneralization`,
  `direction_inversion`, `causal_leap`, `predicate_drift`) plus
  passage-containment locator checks.
- **Idea detector** (`idea_detector.py`) runs on `research_intent`
  turns, matches against five vision §4.1 triggers, emits a *suggestion*
  without persisting. Explicit `idea_promotion` turn is the only path
  into the idea network. (Phase 2.)
- **Thinker frameworks** (10 of them) are loaded dynamically from
  `thinkers.yaml` via `importlib.import_module`. **Not yet invoked
  inside the research pipeline** — reached only via `/api/brainstorm/*`
  and slash commands on followup turns. Phase 4 wires them in.

### Legacy endpoints still active (retirement follow-up)

`/api/research/stream` and `/api/followup/stream` still work. The
frontend's main send path now hits `/api/chat/stream`; some auxiliary
code paths (slash commands, bookmark restore, mindmap QA) still
reference the old endpoints. They retire with `410 Gone` once every
frontend caller is migrated and a scenario test proves the UX stays
intact.

---

## 5. Running the system (practicals)

### Required

- Python **3.10** (3.11+ works too).
- `make`, `git`.
- Internet access for `pip install` the first time.
- At least one LLM API key for a real research run (NVIDIA preferred,
  Groq / OpenAI as fallbacks). Boot works with no keys at all; first
  real LLM call will fail cleanly with no key.

### First-time setup

```bash
cd thoth
make setup       # creates venv/, installs backend/requirements.txt, copies .env.example
# edit .env with at least NVIDIA_API_KEY + TAVILY_API_KEY for a real research run
```

**⚠ Gotcha for Claude Code migration:** the `venv/` committed in this
repository was created on a macOS host and its `python` symlink points
at `/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10`.
That path **does not exist** on a Linux host or on a different Mac
layout. If `make setup` leaves a broken `venv/`, delete it and run
again — or create a disposable venv anywhere outside the project folder
and point `make` at it with `VENV=/path/to/disposable-venv make dev`.

For the Claude Code / verification work this session, the disposable
venv lives at `$HOME/thoth-verify-venv` on the sandbox disk; the user's
`venv/` was never touched. See `docs/archive/verify/A1_boot.md`.

### Running

```bash
make dev            # Uvicorn on :8000 with reload
make dev-web        # Static frontend on :3000 (or serve by opening frontend/index.html)
```

Backend starts cleanly with **no API keys**; it degrades on first LLM
call. `/health` + `/ready` honestly report `database=sqlite_local` and
`redis=memory_fallback` when hosted infra is absent.

### Testing

```bash
make test            # alias for test-vision — the canonical gate
make test-vision     # runs backend/tests/scenarios/ (S1-S3)
make test-legacy-all # runs anything else under backend/tests/ (forensic only)
```

If `pytest` is missing from the venv:

```bash
./venv/bin/pip install pytest pytest-asyncio pytest-subtests httpx
```

### Supabase / Redis

Both are **optional** for development. The code fails open to SQLite
and in-memory cache. See `docs/archive/verify/A6_infra.md` for the
precise observed behaviour.

---

## 6. The verification trail

Every observation that matters lives under `docs/archive/verify/`.
Read in order:

| File | What's in it |
|---|---|
| `BASELINE.md` | Phase 0 memo — **start here**. Three sections: Works / Broken / Aspirational scaffolding. Honest baseline. |
| `A1_boot.md` | Backend boot confirmed on empty env (SQLite + in-memory fallback). |
| `A2_test_truth_table.md` | **No pytest tests on disk** — the deleted-test-suite finding. |
| `A3_endpoint_truth_table.md` | 25 endpoints probed. Approval gate is real; three bugs found (two fixed in Phase 1). |
| `A4_reachable_modules.md` | Which modules are live, test-only, or dead. |
| `A5_vision_vs_running_system.md` | Vision §3 journey walked against the running system before Phase 1. |
| `A6_infra.md` | Fail-open discipline confirmed across Redis, Supabase, LLMs, scholarly APIs. |
| `phase_1.md` | Phase 1 walkthrough (unified `/api/chat/stream`, mode UI removed, three bugs fixed, test gate reinstated). |
| `phase_2.md` | Phase 2 walkthrough (detect-suggest-promote idea capture; no DB write without explicit user approval). |

A fresh Claude Code session can read `BASELINE.md` and the two
`phase_*.md` files (~15 minutes) and have everything needed to continue.

---

## 7. What comes next (Phase 3 onwards)

Each phase lives in the saved plan at **`docs/PLAN.md`**. Thumbnails below.

- **Phase 3 — Lightweight scan vs formal PRISMA (vision §5.4).** New
  `backend/intellectual_rigour/lightweight_scan.py`. Split the FSM in
  `backend/orchestrator.py` so a brief approval triggers a fast scan;
  formal PRISMA runs only when the brief carries `review_mode="formal"`
  and the user approves the cost. New SSE event `scan_result` and
  `recommend_formal_review`. New scenario `test_s3_lightweight_scan_then_formal.py`.

- **Phase 4 — Thinkers integrated into the pipeline (vision §6.3).**
  New `invoke_thinker_when_useful(stage, context)` helper in
  `backend/intellectual_rigour/__init__.py`. Three hook points inside
  `backend/pipeline.py`: brainstorming, critical review, hypothesis
  revision. Severity gating (`critical / serious / substantive /
  non_critical`), bounded retries, no veto. New scenario
  `test_s4_thinker_fires_only_when_useful.py`.

- **Phase 5 — Honest report & claim status (vision §8).** Extend
  `evaluate_claim_support` in `integrity_gate.py` to emit the four
  labels. Wire them onto `manuscript_claims`. Report-level
  `provisional | fully_reviewed`. Frontend status strip. PDF export
  requires explicit approval or a `PROVISIONAL` watermark. Scenario
  `test_s5_provisional_vs_reviewed.py`.

- **Phase 6 — Originality assessment (vision §4).** New
  `backend/intellectual_rigour/originality.py`:
  `generate_adjacent_queries` + `assess_originality` returning one of
  `likely_novel | partial_overlap | substantially_covered |
  insufficiently_assessed`. Guardrail: `likely_novel` is impossible
  without at least one adjacent-field search. Scenario
  `test_s6_originality_adjacent_search.py`.

- **Phase 7 — Project-scoped storage (vision §9).** Add `project_id`
  to `notes`, `embeddings`, `edges` (SQLite + Postgres migration 005).
  `write_note` requires `project_id`. Three retention actions:
  `delete_note_retain_analysis`, `purge_rebuildable_caches`,
  `delete_paper_fully`. Scenario `test_s7_project_scoped_retention.py`.

- **Phase 8 — Feasibility probe (vision §7.2).** New
  `backend/workspace/feasibility.py` with `probe_design(design,
  user_resources)`. Pipeline node after design proposal. Scenario
  `test_s8_feasibility_probe.py`.

- **Phase 9 — Resource awareness (vision §10).** New
  `backend/core/budget.py` with `estimate_cost(operation, inputs)`.
  SSE approval cards carry `cost_estimate`. Session telemetry counter.
  Scenario `test_s9_cost_shown_before_approval.py`.

- **Phase 10 — Deployment model decision (vision §9.3, §12).**
  `docs/decisions/ADR-005-deployment-model.md`. Replace the UNTRUSTED
  `README.md` quickstart. Verify SQLite-only path still runs
  end-to-end.

Each phase ends with a user-seat walkthrough in `docs/archive/verify/phase_N.md`
and a scenario test in `backend/tests/scenarios/`.

---

## 8. Working rules (apply to every change)

### Process

- **Think, then act.** State the plan before touching files for anything
  beyond a one-liner.
- **Verify before trusting.** Running output > a passing test > a status doc.
- **One phase in flight at a time.** Finish → scenario green → walkthrough
  recorded → commit → next.
- **Preserve history.** Use `git mv` for renames. Move suspect code to
  `docs/archive/legacy_code/<phase>/` rather than deleting until the owner
  approves.
- **Never push to GitHub from an agent.** The owner handles `git push`,
  PR creation, and remote branches. You may stage locally; stop there.
- **Secrets never leave `.env`.** `.env.example` stays current with keys
  only (empty values). Route provider error strings through
  `sanitize_log_message` from `backend/agents.py`.

### Code

- **Pydantic v2** for every domain and transport object. Field aliases
  via `model_validator(mode="before")` when a legacy key name is in
  circulation (see `ProjectCreateRequest`).
- **Fail-open on external services.** Redis down → in-memory. Supabase
  absent → SQLite. LLM provider down → fallback wrapper.
- **SQLite schema and Postgres migrations move together.**
  `backend/memory/db.py:init_db` and `db/migrations/*.sql` must agree
  on every table shape. Changing one without the other is a bug.
- **New LLM chains route through `FallbackLLMWrapper`.** Do not hard-code
  a provider.
- **New test code goes in `backend/tests/scenarios/`.** The old
  mock-heavy `backend/tests/` layout is retired. Every behavioural
  change ships with a scenario test that would catch the regression.
- **Fixture isolation for scenario tests:** reload cache-pinned modules
  (`backend.memory.db`, `backend.conversation.brief`,
  `backend.conversation.idea`) in the fixture so each test lands on its
  own `tmp_path` DB. The S1 and S2 fixtures demonstrate the pattern.

### Research integrity (code-level, non-negotiable)

- A citation's locator must point inside the actual passage its claim
  depends on. `verify_passage_locator` fails closed on unindexed sources.
- `extraction_quality` from `ingestion.py` propagates end-to-end — never
  upgrade `partial` or `snippet_only` to `full` downstream.
- `is_approved()` on `ResearchBrief` is the only path into expensive
  compute. **No test-only bypasses.**
- Truth Guard findings degrade reports to `provisional`. They do not
  silently delete claims.
- The idea detector returns `None` on anything short, casual, or
  slash-command. It never fabricates a hypothesis stronger than what
  the user said.

---

## 9. Quick start for a fresh Claude Code session

If you're a new session picking this up — in Claude Code CLI, in a new
claude.ai thread, or anywhere else — do this in order:

1. **Open `THOTH/THOTH.docx`** in Word/Pages (or convert to PDF).
   The vision doc lives only in that subfolder. 25 minutes.
   Read the whole thing.
2. **Read this file (CLAUDE.md).** Especially §0, §0b, §1, §2, §8.
3. **Read `docs/archive/verify/BASELINE.md`.** 5 minutes. Three
   sections: Works / Broken / Aspirational scaffolding.
4. **Read `docs/archive/verify/phase_1.md` and `phase_2.md`.** 10
   minutes. What's been built so far.
5. **Read `docs/SYSTEM_STATE.md`.** Which phase is next, which gaps
   remain.
6. **Run the gate.** `make test-vision` must return 14/14 green. If it
   doesn't, that's the first thing to fix. Use the disposable-venv
   workflow in §5 if the committed `venv/` is a dangling symlink on
   your platform.
7. **Verify the current state matches the written state.**
   `curl http://localhost:8000/ready` after `make dev` should return
   `{"database":"sqlite_local","redis":"memory_fallback",...}` — the
   written contract.
8. **Pick up Phase 3** (vision §5.4 — lightweight scan vs formal
   PRISMA). Full plan: `docs/PLAN.md`. Phase 3 thumbnail: `/CLAUDE.md` §7.

For every phase you work on:

- Open the vision section it addresses in `THOTH.docx` first.
- Write the scenario test *before* the production code when the vision
  behaviour is new. The scenario encodes the user-seat criterion.
- End the phase with a `docs/archive/verify/phase_N.md` walkthrough
  that would let someone starting cold understand what changed.
- Stamp `docs/SYSTEM_STATE.md` with the completion note.
- Keep this file (`CLAUDE.md`) accurate — update §2 and §3 in the
  same change that closes the phase.

### What NOT to do

- **Do not update the UNTRUSTED docs** (`README.md`,
  `docs/roadmap-status.md`, `THOTH/THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md`).
  They are historical artefacts. Current state lives in `SYSTEM_STATE.md`
  and `docs/archive/verify/` only.
- **Do not revive deleted test suites.** `backend/tests/` was wiped on
  purpose; the scenarios directory is the honest replacement.
- **Do not commit or push.** The owner handles git.
- **Do not open the `fast_chat` / `deep_research` / `brainstorm` mode
  surface again.** The frontend is unified by design.

---

*Last updated 23 Oct 2026, after Phase 2 landed. Next phase: 3
(lightweight scan vs formal PRISMA). Keep this file accurate.*
