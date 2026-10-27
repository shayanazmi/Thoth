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

`make test-vision`: 57 passed, 1 skipped (the live-model test).

## Open gaps (from the walkthroughs)

| Gap | Where it shows | Spec |
|---|---|---|
| Project state (hypothesis, question, panels) lives in browser localStorage; a project is created on the first message, not when a hypothesis is accepted | Switching browsers loses client state | `features/02` |
| Thinker replies are not written to the conductor's server-side memory | The conductor can't refer to what a thinker said on a new thread | `features/01`, `03` |
| Free-tier speed: ~1 analysed paper per minute; designer and writer slow down under 429s | A 15-paper trial takes 8–10 min | `features/06` |
| Fallback-model output is labelled (`written_by`, `checked_by`) but not treated as weaker | Proposal status | `features/08` |
| Reviews can't be revised and re-screened; a not-retrieved review record can't take an uploaded PDF | Systematic review | `features/05` |
| The design guardrail checks that assumptions are stated, not that they are sourced | Study design | `features/07` |
| Vault notes are global, not project-scoped | `vault/` | vision §9 |
| Demo tour: only the nurses hunch is recorded; there are no frontend tests | `frontend/scripted/` | — |

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
