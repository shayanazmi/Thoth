# Thoth: system state

> Last updated **25 Oct 2026**. The spec is `THOTH/THOTH.docx`. The working context (folder map, rules) is `/CLAUDE.md`.
> The phase-by-phase log this page used to hold is in `docs/archive/superseded/SYSTEM_STATE_phase_log.md`.

## What a user can do today

1. **Arrive.** The cinematic intro plays: gold dust, the bust, three title cards. The question asked there opens a project.
2. **Talk.** The conductor answers like a colleague and marks general-knowledge claims as unchecked. It proposes notebook entries and offers heavier work, but never starts it.
3. **Think with thinkers.** A council of ten gives independent first takes. Thinkers can also debate, review blind, or talk one to one.
4. **Pin a hypothesis.** Every edit is kept as a version.
5. **Put it on trial.** The hypothesis is split into sub-claims. The plan and cost are shown, nothing runs until you approve, and then each paper is a witness. The ruling says how many papers were read in full.
6. **Run a systematic review.** Protocol, then approval, then search and screening. PRISMA counts come only from recorded decisions.
7. **Design the study** from the resources you actually have.
8. **Draft a proposal.** Outline, then approval, then writing, Verifier and Reviewer. It stays **provisional** until the gaps are closed. Export asks first and watermarks a provisional draft.
9. **Optionally, watch the demo** ("Try the demo" on the landing page): a recorded real run of the whole journey.

Evidence for each step is in `docs/archive/verify/`: `conversation_core`, `thinkers`, `trial`, `systematic_review`, `study_design`, `proposal`, `demo_tour`.

## Gate

`make test-vision`: 83 passed, 1 skipped (the live-model test), 27 Oct 2026.

## Open gaps (from the walkthroughs)

| Gap | Where it shows | Spec |
|---|---|---|
| ~~Project state lives in browser localStorage~~ (27 Oct: question, hypothesis versions, rivals and the conversation are on the server; chats are threads until a hypothesis is accepted; delete removes everything after a count confirmation: `verify/projects_on_server.md`). Chat cards are still only in the browser | A second browser gets the conversation text, not the cards | `features/02` |
| ~~Thinker replies are not in the conductor's memory~~ (28 Oct: rooms and stances reach Thoth, recall covers rooms, quotations are checked against the record: `verify/thinkers_heard.md`). Paraphrase is not checked | A thinker's view can still be misstated without quotation marks | `features/01`, `03` |
| Modes and Stop (27 Oct: Autopilot / Co-pilot with per-step overrides, live-work header, Stop for the trial: `verify/modes_live_work_stop.md`): Stop only for the trial; the screening override is not applied in the review panel; no `activity` table | Long proposal / review runs can't be stopped | `features/02` |
| Hypothesis (27 Oct: strength markers, rivals on the server, version-tied trials and re-map built: `verify/hypothesis.md`): the Judge isn't given the computed markers; Writer and Designer don't check the trial is for the current version | Proposal / design after a swap | `features/04` |
| Free-tier speed: ~1 analysed paper per minute; designer and writer slow down under 429s | A 15-paper trial takes 8–10 min | `features/06` |
| Fallback-model output is labelled (`written_by`, `checked_by`) but not treated as weaker | Proposal status | `features/08` |
| ~~A review is capped at 50 records with no stopping rule~~ (29 Oct: budgeted, paged, logged search; recorded stopping rules; citation rounds; Stop/Continue: `verify/evidence_depth.md`). Reviews can't be revised and re-screened; a not-retrieved review record can't take an uploaded PDF; Semantic Scholar's relevance search stops at 1000 | Systematic review | `features/05` |
| ~~Appraisal is free text; no citation following~~ (29 Oct: design-specific checklists, weight × appraisal, citation neighbours for originality: `verify/evidence_depth.md`) | Trial | `features/06` |
| ~~A version doesn't record why it changed~~ (29 Oct: reason, trigger, evidence and context on every version: `verify/revision_history_and_design_loop.md`). The Reviewer renumbers findings in every review | Hypothesis, design | `features/04`, `07`, `08` |
| ~~The design guardrail checks only that assumptions are stated~~ (28 Oct: unsourced claims flagged; design-level FATALs go back to the Design tab; stale proposal sections marked: `verify/design_revision.md`). Stale sections are brought up to the new design in one step, then re-reviewed; resolved findings are recorded (29 Oct) | Study design, proposal | `features/07`, `08` |
| Vault notes are global, not project-scoped | `vault/` | vision §9 |
| Demo tour: "nurses" is recorded in full; "trust" is recorded but its trial has no verdict; "cities" is not recorded. There are no frontend tests | `frontend/scripted/` | — |

## Retired (25 Oct 2026)

The old plan-and-pipeline path is in `docs/archive/legacy_code/pipeline_v1/`, with a README mapping old to new:
- the FSM research pipeline and its "scan" offer;
- six old routers;
- the heuristic idea detector;
- the pipeline-only rigour modules;
- dead code and the old evaluation suites;
- `frontend/lib` and `frontend/components`.

The conductor now offers only the trial and the systematic review. Walkthrough: `docs/archive/verify/legacy_retirement.md`.

Still in the tree but worth a look later:
- the older thinker engine (`intellectual_rigour/frameworks/`, `registry`, `thinkers.yaml`), reached through the rigour modules;
- `workspace/` manuscripts and exports (pre-redesign; the proposal has its own export).
