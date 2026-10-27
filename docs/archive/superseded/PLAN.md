# Plan — Transform the existing Thoth build into the product-vision system

> **Source of truth for this plan:** this file plus `/CLAUDE.md` plus the
> walkthroughs in `docs/archive/verify/phase_*.md`.
>
> The complete 383-line plan was produced inside the claude.ai session that
> drove Phases 0, 1, and 2. If you need the full text, the owner has it in
> their chat history. The structure below reproduces the plan's phases at
> enough resolution to pick up Phase 3 from a fresh Claude Code session.

## North star

Only `THOTH.docx` is trusted. See `/CLAUDE.md` §0b. Everything else
(including this file) is live documentation that must be kept honest.

## Keep what works, build what's missing

Phase 0's `BASELINE.md` found the engine has real honest spine:
approval gate, task lifecycle, ingestion with access-quality propagation,
Truth Guard entailment checks, LLM fallback wrapper. The transformation
is additive — build the missing vision behaviours as new modules the
spine calls into, not a rewrite.

## Phases (one per vision section it realises)

### Phase 0 — Honest baseline (COMPLETE)
Vision anchor: `/CLAUDE.md` §0 trust model. Output:
`docs/archive/verify/BASELINE.md` + `A1..A6`.

### Phase 1 — One conversation, one surface (COMPLETE)
Vision: §2, §10. Output: `backend/api/routes_chat.py`,
`frontend/index.html` + `frontend/js/app.js` collapsed, three bugs fixed,
`make test-vision` reinstated. Walkthrough:
`docs/archive/verify/phase_1.md`.

### Phase 2 — Idea capture: detect, suggest, promote (COMPLETE)
Vision: §3.1. Output: `backend/conversation/idea_detector.py`,
`idea_candidate` + `idea_promoted` SSE events. No DB write without
explicit user action. Walkthrough: `docs/archive/verify/phase_2.md`.

### Phase 3 — Lightweight scan vs formal PRISMA (NEXT)
Vision: §5.4, §5.5. **Behaviour:** early-stage research gets a fast,
bounded, honestly-labelled scan. Formal PRISMA 2020 runs only when
(a) brief carries `review_mode="formal"`, (b) user explicitly approves,
(c) the resource cost is shown first.

Changes:
- New `backend/intellectual_rigour/lightweight_scan.py` with caps
  (≤20 papers, abstract-only, no snowball, no appraisal matrix).
  Output carries `kind: "lightweight_scan"` in SSE.
- `backend/orchestrator.py` splits FSM: `SCAN` replaces unconditional
  `PRISMA`. `prisma_node` becomes `formal_review_node`, gated on
  `brief.review_mode == "formal"` AND `approved_version == version`.
- A `recommend_formal_review` SSE event fires when maturity signals
  are present (sharp falsifiable hypothesis, counter-evidence
  candidates found, user has promoted a linked idea).
- `backend/api/routes_prisma.py` direct-trigger endpoints require an
  approved formal-review brief.
- New `review_mode` field on `ResearchBrief` in
  `backend/conversation/brief.py`.

Files touched: new `backend/intellectual_rigour/lightweight_scan.py`;
modified `backend/orchestrator.py`, `backend/pipeline.py` (new
`scan_node`), `backend/intellectual_rigour/prisma.py`,
`backend/api/routes_prisma.py`, `backend/conversation/brief.py`.

Scenario test: `backend/tests/scenarios/test_s3_lightweight_scan_then_formal.py`
asserting fresh turn → scan (fast, labelled); follow-up "run a proper
review" → cost estimate → user approval → formal PRISMA with the same
artefacts as today.

### Phase 4 — Thinkers integrated into the research journey
Vision: §6.3. Behaviour: 10 frameworks apply across brainstorming,
hypothesis formulation, literature interpretation, critical review.
Not mechanical: gated via `detect_attack_surfaces`. Severity gating:
`critical | serious | substantive | non_critical`. Bounded retries
(cap `REPLAN` to 2 iterations).

### Phase 5 — Honest report & claim status
Vision: §8.2, §8.3. Behaviour: claims carry
`supported / contradicted / uncertain / insufficiently_assessed`.
Reports carry `provisional | fully_reviewed`. PDF export requires
`fully_reviewed` OR explicit watermarked override.

### Phase 6 — Originality assessment
Vision: §4. New `backend/intellectual_rigour/originality.py` with
`generate_adjacent_queries` + `assess_originality`. Verdict:
`likely_novel | partial_overlap | substantially_covered |
insufficiently_assessed`. Guardrail: `likely_novel` is impossible
without actual adjacent-field search.

### Phase 7 — Project-scoped storage with retention
Vision: §9.1, §9.2. Add `project_id` to `notes`/`embeddings`/`edges`.
`write_note` requires `project_id`. Three retention actions:
`delete_note_retain_analysis`, `purge_rebuildable_caches`,
`delete_paper_fully`. New Postgres migration `005_project_scoped_notes.sql`.

### Phase 8 — Feasibility probe on study designs
Vision: §7.2, §7.3. New `backend/workspace/feasibility.py` with
`probe_design(design, user_resources) -> FeasibilityReport`.
Verdict: `accessible | gated | not_found | unverified`. Pipeline
node after design proposal.

### Phase 9 — Resource awareness surface
Vision: §10. New `backend/core/budget.py` with
`estimate_cost(operation, inputs) -> CostEstimate`. SSE approval
cards carry `cost_estimate`. Session telemetry counter.

### Phase 10 — Deployment model decision
Vision: §9.3, §12. New ADR-005. README replacement. Verify SQLite-only
path end-to-end.

## Cross-phase: tests we trust

Each phase adds a scenario in `backend/tests/scenarios/test_sN_*.py`.
S1 and S2 are already in. The canonical gate is `make test-vision`.
Legacy mock-heavy `backend/tests/` suites were wiped on `main` prior
to Phase 0 — not revived. See `docs/archive/verify/A2_test_truth_table.md`.

## Verification approach

- Each phase ends with a user-seat walkthrough in
  `docs/archive/verify/phase_N.md`.
- Current state is stamped into `docs/SYSTEM_STATE.md`.
- `README.md`, `docs/roadmap-status.md`, and the alignment audit
  stay as historical artefacts — never updated.

## Risks & defaults

- **LLM cost of always-on idea detector.** Default is `use_llm=False`
  (regex pre-filter + heuristic candidate). LLM refinement is opt-in.
- **Chat router becomes the hot path.** Keep it stateless; state in
  brief/task tables. No feature flags.
- **Scenario tests cost real API calls.** VCR-style cassettes planned;
  refresh deliberately, not on CI.
- **Deployment model open until Phase 10.** Everything runs in
  SQLite-only mode until then.

Owner defaults (recorded as reversible):
1. LLM providers: NVIDIA + Groq; OpenAI optional.
2. Scenario-test refresh: manual, not on CI.
3. SQLite primary; Supabase arrives in Phase 7 or 10.

## File-touching summary

Grouped by phase:

- Phase 1: `frontend/index.html`, `frontend/js/app.js`, new
  `backend/api/routes_chat.py`, `backend/main.py`,
  `backend/api/routes_research.py`, `backend/api/routes_followup.py`.
- Phase 2: new `backend/conversation/idea_detector.py`,
  `backend/api/routes_chat.py`, `backend/conversation/idea.py`.
- Phase 3: new `backend/intellectual_rigour/lightweight_scan.py`,
  `backend/orchestrator.py`, `backend/pipeline.py`,
  `backend/intellectual_rigour/prisma.py`,
  `backend/api/routes_prisma.py`, `backend/conversation/brief.py`.
- Phase 4: `backend/intellectual_rigour/__init__.py`,
  `backend/intellectual_rigour/attack_surface.py`,
  `backend/pipeline.py`, `backend/orchestrator.py`,
  `backend/intellectual_rigour/models.py`.
- Phase 5: `backend/intellectual_rigour/integrity_gate.py`,
  `backend/workspace/manuscript.py`,
  `backend/workspace/exporter.py`,
  `backend/workspace/pdf_compiler.py`,
  `backend/api/routes_workspace.py`, `backend/memory/db.py`, frontend.
- Phase 6: new `backend/intellectual_rigour/originality.py`,
  `backend/intellectual_rigour/clustering.py`,
  `backend/api/routes_chat.py`, `backend/conversation/idea.py`.
- Phase 7: `backend/memory/db.py`, `backend/memory/vault.py`,
  `backend/memory/index.py`, `backend/memory/graph.py`,
  `backend/repositories/vault_repo.py`, `backend/api/routes_vault.py`,
  `backend/api/routes_workspace.py`, new
  `db/migrations/005_project_scoped_notes.sql`, frontend.
- Phase 8: new `backend/workspace/feasibility.py`,
  `backend/pipeline.py`, `backend/orchestrator.py`,
  `backend/api/routes_chat.py`.
- Phase 9: new `backend/core/budget.py`,
  `backend/api/routes_chat.py`, `backend/telemetry.py`, frontend.
- Phase 10: new `docs/decisions/ADR-005-deployment-model.md`,
  `README.md`, `docs/setup.md`, `docs/deployment.md`.

---

*If this plan contradicts `THOTH.docx`, the vision wins and the plan
is wrong — flag it and we revise.*
