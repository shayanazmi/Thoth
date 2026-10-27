# Thoth — System State: Verification Plan & Build Plan

> **Status at 23 Oct 2026 (post-Phase 0):** Honest baseline established.
> The engine is more alive than the status docs claimed; the vision journey
> is only partially realised; the test suite has been deleted entirely.
> See `docs/archive/verify/BASELINE.md` — read first before planning any change.
> The only trusted spec is `THOTH.docx`. Everything in `README.md`,
> `docs/roadmap-status.md`, and `THOTH/THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md`
> remains unverified and should be read as historical artefact only.
>
> **Guided tour + visual refresh (25 Oct 2026).** Obsidian & Gold palette, a motion system
> (`frontend/js/motion.js`), a new intro (`intro-cinema.js`), and an optional cinematic tour in
> `frontend/scripted/` that replays a recorded real run (or coaches a Live one). No backend behaviour
> changed beyond mounting `/scripted`. Walkthrough: `docs/archive/verify/demo_tour.md`.

> **UX-first rule:** every phase below is judged by a walkthrough from the
> user's seat against `THOTH.docx` §3, not by server-side probes. Code that
> works but produces an off-vision journey is still broken.

> **Phase 1 complete (23 Oct 2026).** One unified `/api/chat/stream` endpoint;
> frontend collapsed to one textarea; server classifies the turn; approval
> gate re-asserted with no `fast_chat` bypass; three bug fixes landed;
> `make test-vision` reinstated with 6 scenario tests passing. Full
> walkthrough: `docs/archive/verify/phase_1.md`.

> **Phase 2 complete (23 Oct 2026).** Vision §3.1 landed: a conservative
> five-trigger idea detector (`backend/conversation/idea_detector.py`)
> suggests, never persists. Explicit `idea_promotion` turn is the only
> path into the idea network. 14/14 scenarios passing. Walkthrough:
> `docs/archive/verify/phase_2.md`.

> **Phase 3 complete, plus proof-of-concept slices of Phases 4/5/6/9 (23 Oct 2026).**
> Approval runs a bounded, abstract-only lightweight scan by default; formal
> PRISMA runs only after "run a formal review" creates a new brief version
> (`review_mode=formal`) and that version is approved. Plan cards carry effort
> estimates; runs end with a thinker perspective, an originality verdict and a
> provisional/fully_reviewed status. Four pre-existing frontend bugs that had
> stopped every chat card rendering were fixed. Walkthrough:
> `docs/archive/verify/phase_3.md`. Demo script: `docs/DEMO.md`.

> **UI v2 (24 Oct 2026).** New journey-based interface (plan: `docs/UI_REVAMP_PLAN.md`; build steps 1–3 plus thinkers): home with doors, moon-phase journey path, projects sidebar, pinned hypothesis with versions, council / join / debate / one-on-one thinkers, stage-aware workspace with Check view, activity timeline, slash commands, light/dark, responsive. Old UI archived in `docs/archive/legacy_code/ui_v1/`. Walkthrough: `docs/archive/verify/ui_v2.md`.

## Current scorecard (vision §3 journey)

Five of ten stages closed, five remaining. Phase 3 is next.

| Stage | Vision §3 | Status | Realised in |
|---|---|---|---|
| 1 | Open conversation | **WORKS** | Phase 1 |
| 2 | Recognise a promising direction | **WORKS** | Phase 2 |
| 3 | Prepare without blocking | **WORKS** | Phase 1 |
| 4 | Seek approval for substantial work | **WORKS** | Phase 1 |
| 5 | Brainstorm with thinkers | PARTIAL (thinker at critical review only) | Phase 4 |
| 6 | Lightweight scan vs formal PRISMA | **WORKS** | Phase 3 |
| 7 | Return to brainstorming | **WORKS** | Phase 1 |
| 8 | Refine one main hypothesis | MOSTLY WORKS | monitor |
| 9 | Design the study | MISSING | Phase 8 (planned) |
| 10 | Reports & manuscript | PARTIAL (provisional status, no auto-PDF in chat path) | Phase 5 |

Off-journey vision gaps:

- **§4** Originality assessment with adjacent-field search → **Phase 6**.
- **§9.1** Project-scoped paper storage → **Phase 7**.
- **§10** Resource-awareness surface → **Phase 9**.
- **§12** Deployment model decision → **Phase 10**.

## Gate

```
$ make test-vision
================= 14 passed in ~39s =================
```

14 scenario tests across `test_s1_conversation_never_blocks.py` (6)
and `test_s2_idea_detect_suggest_promote.py` (8). Every future phase
adds its own `test_sN_*.py` scenario file as part of the acceptance
criterion.

---

---

## 0. Why this file exists

We cannot plan a realignment to the vision until we know what, if anything,
in the current repository actually behaves as advertised. Any plan that
starts from the roadmap or the audit inherits their inaccuracies. So the
plan is in two phases:

- **Phase A — Verification.** Build an honest baseline of what works, what
  is broken, and what is aspirational scaffolding. No new features.
- **Phase B — Rebuild to vision.** Only against `THOTH.docx`. Reuse what
  Phase A proved works. Replace or discard the rest.

Finish A before touching B.

---

## 1. Phase A — Verification (do this first)

Each step is a concrete, bounded task. Do them in order; each one's output
is the input for the next.

### A1. Does the backend start?

- [ ] Fresh `make setup` from the repo root in a disposable venv.
- [ ] `make dev` — note any import error, missing env var, or startup
      exception. Record the full first failure in `docs/archive/verify/A1.md`
      (create the dir).
- [ ] If it starts, hit `/health` and `/ready`. Record responses.
- **Decision point:** if it does not start without substantial fixes,
  stop and discuss with the owner. Do not go hunting for other failures
  until the entry point is honest.

### A2. Which test suites actually pass on a clean checkout?

- [ ] Run `make test` and capture the full output to `docs/archive/verify/A2_make_test.log`.
- [ ] Run `make test-all` and capture to `A2_make_test_all.log`.
- [ ] For each failing suite, record: file name, first failure, whether
      it is an import error, a missing fixture, a mock misalignment, or a
      genuine behaviour failure.
- [ ] For each *passing* suite, read the test file briefly and record
      whether the test exercises a real code path or a heavily mocked
      shell. A test that mocks the thing it is testing is not evidence.
- **Output:** `docs/archive/verify/A2_test_truth_table.md` — one row per
  suite, with columns `name | runs? | real coverage? | notes`.

### A3. Which endpoints respond?

- [ ] With the backend running, exercise each router with a minimal
      realistic payload: `/api/research/stream`, `/api/followup/stream`,
      `/api/brainstorm/*`, `/api/ideas/*`, `/api/prisma/*`,
      `/api/workspace/*`, `/api/vault/*`.
- [ ] For each endpoint, record: HTTP status, whether the SSE stream
      produces real events or stalls, whether external APIs (NVIDIA, Groq,
      Tavily, S2) are actually reached or short-circuit on a missing key.
- **Output:** `docs/archive/verify/A3_endpoint_truth_table.md`.

### A4. Which modules are reachable from a user-facing path?

- [ ] Starting from each router, trace the call graph down and note the
      modules that are actually imported *and executed* on a real request.
- [ ] Everything in `backend/` that is not reachable from the router graph
      is either dead code, scaffolding, or only used by tests. Mark it as
      such; do not delete.
- **Output:** `docs/archive/verify/A4_reachable_modules.md` with three
  columns: `path | reached by | status (live / test-only / dead)`.

### A5. The core research journey, end to end

The vision brief (`THOTH.docx` §3) names the stages: open conversation →
recognise promising direction → prepare brief (non-blocking) → seek
approval → brainstorm with evidence → lightweight scan → formal review on
approval → refine one hypothesis → design study → manuscript.

- [ ] Walk through those stages against the running system, one by one,
      with realistic input. For each stage, record: does it work at all,
      does it work as `THOTH.docx` specifies, or does it diverge.
- **Output:** `docs/archive/verify/A5_vision_vs_running_system.md`.

### A6. Infra reality check

- [ ] Is Supabase actually required for a minimum dev run, or does the
      SQLite fallback carry? Record which paths depend on which.
- [ ] Does Redis fail open as the code claims? Kill Redis locally and
      verify.
- [ ] Which `.env` keys are strictly required to boot vs. required for
      a real research run?
- **Output:** `docs/archive/verify/A6_infra.md`.

### A7. Honest baseline summary

Collate A1–A6 into a single short memo at
`docs/archive/verify/BASELINE.md` with three sections:

1. **Works** — behaviours we have observed end-to-end, with evidence
   links.
2. **Broken** — behaviours that fail or do not exist, with the specific
   failure.
3. **Aspirational scaffolding** — modules present but not reachable or
   not functional; candidates for salvage, rewrite, or archive.

That memo is the input to Phase B. Nothing in Phase B starts until it exists.

---

## 2. Phase B — Rebuild to vision (do not start until A7 exists)

Phase B is organised by the vision's structure, not by the repo's. For
each item below, the first step is: **read the relevant section of
`THOTH.docx` and write down what "done" means in behavioural terms,
before touching code.**

### B1. Conversation first (vision §2, §10, §3)

- The user can hold ordinary conversation.
- When a research direction emerges, Thoth notices and *proposes*
  without blocking the conversation.
- Preparation happens in parallel. The chat does not freeze.
- No distinct "modes" imposed on the user.

### B2. Approval gate that is user-controlled (vision §2, §10)

- Any substantive, time- or compute-consuming action (formal literature
  review, deep paper analysis, PDF export) presents a plan and waits.
- Approval is per exact proposed plan. Edits re-prompt.
- "Lightweight scan" during exploration is distinct from "formal review"
  and does not require approval; "formal review" does.

### B3. Idea capture: detect → suggest → promote (vision §3.1)

- Tentative ideas live in the current conversational context.
- Promotion to the persistent project idea network is explicit and
  user-approved.
- Connections between promoted ideas are *reasoned*, not surface-similar.
- The network is not a stream of auto-generated suggestions.

### B4. Brainstorming-to-research handoff (vision §3.2)

- When the user escalates, Thoth produces a structured brief carrying
  the hypothesis + motivation + assumptions + critiques + unresolved
  questions + intended outcome.
- The brief evolves with evidence but preserves original motivation and
  a traceable record of substantive revisions.

### B5. Originality assessment (vision §4)

- Compare substance, not phrasing.
- Search adjacent disciplines and alternative terminology.
- If an idea is already covered, say so clearly and show the overlap.
- Never fabricate a gap. Keep insufficiently-assessed directions as
  "unresolved" rather than falsely labelling them original.

### B6. Literature discovery and paper analysis (vision §5)

- Progressive depth: broad scan → targeted deep reads with approval.
- Automatic open-access retrieval; user-uploaded PDFs when needed.
- Honest access-quality labels; abstract-only is clearly marked.
- Inaccessible papers do not block the review; they are noted and the
  review continues.

### B7. Lightweight scans vs. PRISMA (vision §5.4–§5.6)

- Early brainstorming uses a lightweight scan.
- When a serious research project emerges, Thoth recommends PRISMA with
  a protocol proposal and waits for approval.
- PRISMA records are honest: real queries, dates, counts, exclusion
  reasons. No invented screening numbers.

### B8. Multi-agent rigour with simplicity (vision §6)

- The seven logical responsibilities (researcher, analyst, synthesis,
  verifier, methodological critic, thinkers, integrator) are *roles*,
  not seven services. Combine where it makes sense.
- Independent judgement over a shared evidence collection.
- Severity-gated criticism, bounded retries, no veto power.

### B9. Thinkers integrated into the whole research journey (vision §6.3)

- Thinker perspectives are available across brainstorming, hypothesis
  formulation, literature interpretation, and critical review.
- Invoked when they add value, not mechanically.
- When the user doesn't know which perspective to pick, Thoth recommends.

### B10. One main hypothesis, feasible design (vision §7)

- Thoth refines one primary hypothesis at a time; considers alternatives
  only when they materially affect the investigation.
- Proposes the simplest adequate design. Verifies that required data,
  tools, repositories actually exist. Offers alternatives when the
  preferred design is impractical.

### B11. Reports, manuscript, honest status (vision §8)

- Report and claim statuses: `supported` / `contradicted` / `uncertain` /
  `insufficiently assessed`.
- Provisional vs. fully reviewed distinction is user-visible.
- Evolving manuscript. No fabrication. Pending sections marked.
- PDF export only on explicit approval.

### B12. Storage and openness (vision §9)

- Papers belong to the project they were supplied in. No cross-project
  library.
- User-controlled retention: delete PDF but keep extracted analysis,
  clear rebuildable caches, full removal with explained consequences.
- Open-source. Sustainable resource model. Local-first vs. hosted vs.
  both is deferred (vision §12) — do not silently assume unlimited
  hosted compute.

Each Bn is "done" only when it satisfies the vision end-to-end on the
running system and has a direct behavioural test (not a mock-heavy unit
test). Order within Phase B will be decided after A7 is in hand.

---

## 3. What is explicitly deferred until Phase B is well under way

From `THOTH.docx` §12:

- Deployment model (local-first / hosted / both; resource limits).
- Concrete search stopping criteria with resource budgets.
- Depth and resource thresholds (when to recommend deeper analysis).
- Minimum viable PRISMA + appraisal set for the first stable release.

These are decisions, not features. Each becomes a new ADR when settled.

---

## Redesign stamp (24 Oct 2026, design only, nothing built)

An owner interview found the current flow foundationally flawed: chat has no memory, almost every
message becomes a plan card, one report shape serves every tier, the writer is graded by its own
model, each thinker exists in 3-4 conflicting forms, and every agent runs on a small model.
The agreed redesign lives in `docs/features/` (one file per feature, with draft prompts for all
11 agent roles in `09-agents-and-prompts.md`). Build order: conversation core + notebook → literature
+ trial → thinkers (after roster research) → hypothesis, design, proposal.

## Conversation core stamp (24 Oct 2026, built)

Feature 01 (+ notebook proposals from 02) is built: `backend/conversation/conductor.py` (one conductor on
NIM Ultra with five tools), `backend/memory/conversation_store.py` + migration `006_conversation_core.sql`,
`POST /api/chat/proposals/{id}`, and frontend cards. Plain messages no longer create plan cards; plans come
from an accepted offer (`step_accept`). Gate: 27/27 in ~2s (S10 added; S1-S3 updated to go through `step_accept`). Also fixed: the gate had been
making live LLM / web-search / Redis calls (~10 min) because `backend/__init__.py` loads `.env` before the
scenario conftest ran; a repo-root `conftest.py` now blanks those variables first.
Walkthrough: `docs/archive/verify/conversation_core.md`. Thinker roster swaps approved (code swap lands with 03).

## Thinkers stamp (24 Oct 2026, built)

Feature 03 is built: `backend/thinkers/` (dossiers, roster, persona engine, modes), `thinker_memory` +
migration 007, `/api/thinkers`. Approved roster live (Aristotle, Ibn al-Haytham, Hume, Darwin, Nightingale,
Weber, Popper, Kuhn, Simon, Ostrom). Gate 36/36 in ~2s (S12 added); live blind attribution 28/30.
Walkthrough: `docs/archive/verify/thinkers.md`. Pipeline thinker pass still on old frameworks until feature 08.

## Trial + literature stamp (24 Oct 2026, built)

Features 05/06 (first version): `backend/research/` (librarian: OpenAlex + Europe PMC + per-sub-claim queries,
legal open full text; reader: hypothesis-blind records with enforced provenance; analyst: sub-claims + matrix
rows; judge: GRADE-style weighing with code-enforced guardrails; trial runner), tables `trials`, `trial_papers`
(+ migration 008), `/api/trial/*` with an explicit approval gate, live matrix in the Check panel, "I say",
PDF upload, add-by-DOI, re-weigh. Pipeline thinker check now uses the co-author engine. Gate 46/46.
Not yet: systematic-review tier (Screener/PRISMA rebuild), Autopilot/Co-pilot switch, token streaming.
Walkthrough: `docs/archive/verify/trial.md`.

## Study design stamp (25 Oct 2026, built)

Feature 07: `backend/research/designer.py` (2-3 candidates from the latest trial's lessons + the researcher's
resources; code-enforced guardrails: witness-cited measures or "new: needs validation", no causal claims from
non-causal designs, stated sample-size assumptions, closed feasibility labels), `/api/design/*`, a Design stage
between Review and Draft. Resources, candidates and the chosen design live in versioned notebook sections
(no new table). Thinkers can critique the chosen design. Gate 50/50. Walkthrough: `docs/archive/verify/study_design.md`.

## Research proposal stamp (25 Oct 2026, built)

Feature 08: outline (Writer, editable and reorderable) → explicit approval with an estimate → sections written
one at a time from the research file only (trial witnesses, verdict, chosen design, resources, "I say") →
Verifier per sentence (deterministic witness/number/marker checks, then entailment; soften or remove, every
removal listed; uncited claims flagged) → peer Reviewer (FATAL → at most 2 revision rounds) → thinker reviews
whose critical concerns must be answered. `reviewed` vs `provisional` with the explicit open items; references
built deterministically from cited witnesses only; Markdown export only with approval, provisional watermarked.
`backend/research/{writer,verifier,reviewer,proposal}.py`, `/api/proposal/*`, Draft tab (`frontend/js/proposal.js`).
Versioned notebook sections, no new table. Gate 59 passed, 1 skipped. Walkthrough: `docs/archive/verify/proposal.md`
(live run on the nurses project ended provisional: 1 FATAL about the chosen design's recall windows, 4 open
critical thinker concerns).

## Systematic review stamp (25 Oct 2026, built)

Feature 05 tier 3: `backend/research/review.py` + `review_store.py`, tables `sys_reviews`, `sys_review_records`
(+ migration 010), `/api/review/*`, `frontend/js/review.js`. Protocol → approval (once) → identification
(duplicates counted) → Screener at title/abstract and full text (reasons required, hypothesis-blind) with a per-review
Auto / Human-in-the-loop switch → included studies into a linked trial. PRISMA counts are computed from records only.
Old formal-review pipeline unreachable from the UI (code kept). S15 added. Walkthrough: `docs/archive/verify/systematic_review.md`.

---

## 4. Working with this file

- Update this file in the same change that moves any task above.
- Append new findings. Do not rewrite old entries silently — strike
  through with a dated note.
- The file is small on purpose. If you want to add a long analysis,
  put it in `docs/archive/verify/` and link to it from here.

This file plus `CLAUDE.md` plus `THOTH.docx` is the complete working
context. Nothing else in the repository is a substitute.
