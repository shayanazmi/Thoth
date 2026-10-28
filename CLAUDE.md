# CLAUDE.md: Thoth working context

> Read this in full before touching anything. It is the single working context for any agent on
> Thoth. If it conflicts with any other file, `THOTH/THOTH.docx` wins, then this file.
> Last updated **27 Oct 2026**.

---

## 1. What Thoth is (and what "working" means)

Thoth is a research **companion**, not a report generator. The spec is `THOTH/THOTH.docx` (vision v1.0,
15 Oct 2026), the only trusted document. In the owner's words:

> Thoth should not merely answer questions a researcher already knows how to ask. It should help people
> discover which questions are worth asking, understand what existing scholarship establishes, and
> investigate what might meaningfully add to that knowledge.

**The only evidence that something works is a walkthrough from the user's seat.** Green tests, 200s and
streaming events are debugging aids. A feature is done when its `docs/archive/verify/<feature>.md` records
a real run in the browser.

### Non-negotiables (vision §2, §11)

- Never fabricate citations, counts, source access, methods, results or originality.
- Never present abstract-level reading as full-text analysis (`extraction_quality` is never upgraded).
- Never label work "complete" while critical evidence or review is open. Use **provisional**, with the gaps listed.
- Never declare an idea original because a model said so. Never manufacture a gap.
- Nothing costly runs, and nothing is exported, without explicit user approval.
- Conversation first: the chat never blocks while work runs.
- Thinkers criticise with severity; none gets a veto.

---

## 2. Current state (25 Oct 2026)

The product is the 24 Oct redesign in `docs/features/`. One conversation, a living research file, and a
journey: **Explore → Thinkers → Hypothesis → Check → Review → Design → Draft**.

| Feature (spec) | Status | Evidence |
|---|---|---|
| Conversation core: the conductor (`01`) | Built | `verify/conversation_core.md` |
| Threads, projects, research file (`02`) | Mostly. Project state on the server (a second browser rebuilds it), thread → project on an accepted hypothesis, delete with counts; Autopilot / Co-pilot with per-step overrides; live-work header and Stop for the trial | `verify/projects_on_server.md`, `verify/modes_live_work_stop.md` |
| Thinkers as co-authors: roster, council, debate, reviews (`03`) | Built | `verify/thinkers.md` |
| Hypothesis: versions, strength markers, rivals, version-tied trials, re-map (`04`) | Built | `verify/hypothesis.md` |
| Literature + the trial / neutral court (`05`, `06`) | Built | `verify/trial.md` |
| Systematic review, PRISMA (`05` tier 3) | Built | `verify/systematic_review.md` |
| Study design + feasibility (`07`) | Built; revises itself from the peer Reviewer's design-level FATALs; unsourced claims flagged | `verify/study_design.md`, `verify/design_revision.md` |
| Writing: research proposal, verifier, reviewer, export gate (`08`) | Built | `verify/proposal.md` |
| UI: Folio layout, Obsidian & Gold palette, motion, cinematic intro (`10`) | Built | `verify/demo_tour.md` |
| Guided demo tour (optional, `frontend/scripted/`) | Built. "Nurses" recorded in full. "Trust" recorded 27 Oct, but its trial stopped before a verdict (the autopilot moved on), so that chapter replays without a ruling. "Cities" not recorded | `verify/demo_tour.md` |

**Known gaps** (details are in each walkthrough):
- free-tier speed (~1 paper/min);
- fallback-model output is labelled but not weighted lower;
- Thoth's quotations of thinkers are checked against the record, but its paraphrases are not;
- chat cards still live in the browser (the conversation text and project state are on the server);
- Stop exists for the trial only;
- no "revise and re-screen" for reviews;
- no frontend tests.

The old plan-and-pipeline path, its six routers and the dead code were retired on 25 Oct 2026, to
`docs/archive/legacy_code/pipeline_v1/` (see `verify/legacy_retirement.md`).

**Test gate:** `make test-vision` → **83 passed, 1 skipped** (28 Oct 2026). The skip is a live-model test; set `THOTH_LIVE_TESTS=1` to run it.

---

## 3. Folder map

```
thoth/
├── CLAUDE.md                 this file
├── THOTH/THOTH.docx          the spec (only trusted document) · thoth_visual_architecture_guide.png
├── README.md                 public overview: idea, journey, reel, quick start (points here for working rules)
├── Makefile                  setup · dev · test(-vision) · migrate · seed · health …
├── main.py                   ASGI entry → backend.main:app
├── conftest.py               blanks provider keys + hosted URLs so tests never call live services
├── pytest.ini  requirements.txt (→ backend/)  railway.toml  .env(.example)
├── .agent/  .agents/         one-line pointers to this file
│
├── backend/
│   ├── main.py               FastAPI app: routers, static mounts (/js /styles /assets /scripted), no-cache for UI files
│   │                         (it creates backend/backend → backend at startup on purpose, for Railway; gitignored)
│   ├── agents.py             LLM factory (get_role_llm), FallbackLLMWrapper, sanitize_log_message
│   ├── api/                  routes_chat (/api/chat/stream: conductor turns, idea promotion, proposal resolution)
│   │                         routes_thinkers · routes_trial · routes_review · routes_design · routes_proposal
│   │                         routes_workspace (/api/projects, manuscripts, exports) · routes_health
│   ├── conversation/         conductor.py (one agent per chat turn) · idea.py (explicit idea promotion)
│   │                         brief.py (task lifecycle + orphan reconciliation at startup) · mandate · escalation
│   │                         · clarification · resolver
│   ├── thinkers/             roster.py · persona.py · modes.py · dossiers/ (one per thinker)
│   ├── research/             the trial: librarian · reader · analyst · judge · trial · store
│   │                         review · review_store (systematic review) · designer (study design)
│   │                         writer · verifier · reviewer · proposal (writing) · llm.py
│   ├── memory/               db.py (SQLite schema, init_db) · conversation_store · vault · graph · index · session
│   ├── intellectual_rigour/  integrity_gate (Truth Guard) · attack_surface · counter_evidence · sparring · synthesis
│   │                         · matcher · registry + frameworks/ + thinkers.yaml (older thinker engine)
│   ├── core/                 config · cache (Redis → memory) · errors · logging
│   ├── scholarly.py  ingestion.py  tools.py  dispatcher.py  telemetry.py
│   ├── reports/  workspace/  collaboration/   sections/patch/validation · manuscripts/exports · membership + sync
│   ├── repositories/base.py  supabase_provider (used by health)
│   └── tests/scenarios/      THE test gate: S10 S11 S12(×2) S13 S14 S15 S16 S17 S18 S19 S20 S21 (fixtures + SSE helpers in conftest.py)
│
├── frontend/                 vanilla ES modules, no build step
│   ├── index.html            shell: sidebar · journey · conversation · workspace · intro
│   ├── styles/               tokens.css (Obsidian & Gold, motion tokens) · app.css · folio.css · motion.css
│   ├── js/                   main (boot, home, journey, layout, theme) · chat (conversation, slash commands)
│   │                         store · api · workspace · thinkers · trial · review · design · proposal
│   │                         ui (dialog, toast) · util · motion (scenes, once-only entrances)
│   │                         intro-cinema.js (the intro; always plays) · intro-lantern.js (?intro=lantern)
│   ├── scripted/             OPTIONAL guided demo. Delete the folder to remove it (see its README.md)
│   ├── assets/               bust, scales, logo, favicon, social preview
│   └── Dockerfile  nginx.conf  railway.toml
│
├── db/migrations/            Postgres 001–008, 010 (must match backend/memory/db.py) · db/seed · db/store.db (local)
├── docs/                     see §7
├── scripts/                  db/ (migrate, seed) · ops/ (health, cache flush)
├── vault/                    Obsidian-style notes (global; not yet project-scoped)
├── scratch/                  throwaway
└── venv/                     local virtualenv (gitignored)
```

---

## 4. How a session flows

```
Browser (frontend/js)
  ├─ POST /api/chat/stream ── routes_chat._classify_turn
  │     ├─ ordinary turn      → conductor.run_conductor_turn  (replies, quick looks, notebook proposals,
  │     │                       offers of the trial / systematic review, which the UI opens on accept)
  │     ├─ idea promotion     → idea network (only on an explicit user action)
  │     └─ approval / step_accept / brief_id → "retired" error; nothing runs
  ├─ /api/thinkers/*   council · debate · reviews · one-to-one reply (dossier-driven personas)
  ├─ /api/trial/*      plan (sub-claims, cost) → approve → run (SSE: papers → matrix → verdict)
  ├─ /api/review/*     protocol → approve (Auto / Human-in-the-loop) → PRISMA counts from recorded decisions
  ├─ /api/design/*     resources → candidate designs → choose
  ├─ /api/proposal/*   outline → approve → write (SSE) → verify → review → export (approval, PROVISIONAL watermark)
  └─ /api/projects     project list / create
```

- Every costly step shows its plan and cost first and runs only on an explicit approval.
- Streams are SSE: `data: {"event": …, "payload": …}`.
- Storage is SQLite locally. Postgres/Supabase and Redis are optional and fail open (`/ready` reports `sqlite_local` / `memory_fallback`).
- LLMs go through `get_role_llm` / `FallbackLLMWrapper`: NVIDIA NIM first, with Groq and OpenAI as fallbacks.

---

## 5. Run and test

```bash
make setup          # venv + backend/requirements.txt + .env from .env.example
make dev            # uvicorn on :8000, serves the UI at /
make test-vision    # the gate (backend/tests/scenarios); `make test` is an alias
```

- **Keys:** the app boots with no keys and degrades on the first model call. A real run needs `NVIDIA_API_KEY` and `TAVILY_API_KEY` (Groq and OpenAI are optional fallbacks).
- **venv gotcha:** the committed `venv/` was made on macOS. If its python symlink is dangling, delete it and run `make setup`, or point make at another venv: `VENV=/path make dev`.
- **Missing pytest:** `./venv/bin/pip install pytest pytest-asyncio pytest-subtests httpx`.
- **UI caching:** the UI is unversioned ES modules served with `Cache-Control: no-cache`, so a reload never mixes old and new modules.

---

## 6. Working rules

**Process**
- Think, then act. State the plan before anything bigger than a one-liner.
- Verify before trusting: a running walkthrough beats a passing test, which beats a doc.
- Every behaviour change ships with a scenario test in `backend/tests/scenarios/` and a walkthrough in `docs/archive/verify/`.
- Keep this file current in the same change that alters state, the folder map or rules.
- Preserve history: move superseded code and docs to `docs/archive/` (`git mv`), don't delete them.
- **Never commit or push.** The owner handles git.
- Secrets stay in `.env`. `.env.example` lists keys only. Route provider errors through `sanitize_log_message`.

**Code**
- Use Pydantic v2 for domain and transport objects.
- Fail open on external services.
- New LLM calls go through `get_role_llm` / `FallbackLLMWrapper`. Never hard-code a provider.
- `backend/memory/db.py:init_db` and `db/migrations/*.sql` change together.
- Scenario test fixtures reload cache-pinned modules (`backend.memory.db`, `backend.conversation.brief`, `backend.conversation.idea`) so each test gets its own `tmp_path` DB (see the S1/S2 fixtures).
- Frontend: vanilla modules and CSS tokens only. Wrap storage access in try/catch. Respect `prefers-reduced-motion`.
- **Do not reopen** the `fast_chat` / `deep_research` / `brainstorm` mode surface: the UI is one conversation by design.

**Research integrity (code level)**
- A citation's locator must point inside the passage its claim depends on. `verify_passage_locator` fails closed.
- The approve flags on trial, review and proposal runs are the only paths into expensive compute. The chat never starts heavy work. There are no test-only bypasses.
- Truth Guard and Verifier findings degrade status to provisional. They never silently delete claims.
- The idea detector returns `None` on anything short, casual or a slash command, and never states a hypothesis more strongly than the user did.
- The demo tour replays **recorded real runs only**. Fixtures are never hand-written.

---

## 7. Documentation map

| Where | What |
|---|---|
| `THOTH/THOTH.docx` | The spec |
| `CLAUDE.md` | This file: state, map, rules |
| `docs/SYSTEM_STATE.md` | Short status page: what's built, what's next |
| `docs/features/00–10` | The redesign specs, one per feature (architecture, agents, prompts, acceptance walkthrough) |
| `docs/archive/verify/*.md` | User-seat walkthroughs: the evidence (current: `conversation_core`, `thinkers`, `thinkers_heard`, `trial`, `systematic_review`, `study_design`, `design_revision`, `proposal`, `projects_on_server`, `hypothesis`, `modes_live_work_stop`, `demo_tour`, `legacy_retirement`) |
| `frontend/scripted/README.md` | Playing, recording and deleting the demo tour |
| `docs/media/` | The 18s product reel used by the README (`thoth-reel.mp4`, GIF preview, poster), cut from the real "trust" recording |
| `docs/setup.md` `env-vars.md` `deployment.md` `runbook.md` `database-schema.md` `caching.md` `auth-flow.md` `api-limits.md` | Ops reference, written before the redesign. Check against the code before relying on details. |
| `docs/decisions/ADR-001…004` | Infrastructure decisions (monorepo, Supabase, Redis, decoupled client) |
| `docs/archive/superseded/` | Retired material: the old 10-phase plan, handoff, demo script, UI v3 plan, roadmap ledger, alignment audit, architecture suite and diagrams, UI prototype, old agent pointers. **Historical only.** |
| `docs/archive/verify/` (A1–A6, BASELINE, phase_1–3, ui_v2) and `docs/archive/legacy_code/` | Earlier baselines and retired code (`pipeline_v1` with its README, UI v1, intro v2, redesign v3) |
