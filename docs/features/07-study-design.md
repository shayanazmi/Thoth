# 07 · Study design

> **Built 24-25 Oct 2026**: walkthrough in [`docs/archive/verify/study_design.md`](../archive/verify/study_design.md).

> Vision: §3 stage 9, §7.2 (feasibility). The owner chose a **separate stage before the draft**.

## What the owner wants

A dedicated stage, between the trial and the proposal, where a feasible study is designed for the
hypothesis.

## Design

### Inputs

- The hypothesis and its sub-claims (04).
- The trial's **methodological lessons**: which designs produced the high-weight witnesses, which
  operationalisations were contested, and the boundary conditions and blind spots worth targeting (06).
- The user's resources, asked once and remembered: time, access to a population, budget, skills
  (stats, qualitative), ethics route (student/IRB), tools.

### Steps

1. **Designer proposes 2-3 candidate designs** (e.g. a prospective cohort with actigraphy; a
   cross-sectional survey with MBI and PSQI; a mixed-methods design). For each:
   - what it can and cannot conclude (causal? correlational?);
   - which sub-claims it tests;
   - measures, borrowing the best operationalisations from the matrix, with citations;
   - sample size reasoning, with the assumptions shown, or "needs a power analysis with X";
   - main threats to validity, and how each one is handled.
2. **Feasibility check** against the user's resources: `feasible | feasible_with_changes | not_feasible`,
   with the specific blockers.
3. **Thinker critique** (optional, independent): e.g. Bacon on the crucial experiment, Nightingale on measurement.
4. The user picks one and edits it → it becomes the Design section of the research file (02), versioned.

### Honesty rules

- Never invent sample sizes, effect sizes or instrument properties. Each number either cites a source or is
  shown as an assumption.
- Never imply a design can show causation when it can't.

## Agent

**Designer**: [09 § Designer](09-agents-and-prompts.md#designer). Model: Ultra.
Replaces the planned `workspace/feasibility.py` probe (`CLAUDE.md` Phase 8).

## Walkthrough (acceptance)

1. After a trial, open Design → enter resources (3 months, one hospital, no budget).
2. Get 2-3 candidates, each with its limits stated; any needing funding is marked `not_feasible` with the reason.
3. Every measure cites the matrix paper it came from.
4. Pick one, edit it → the Design section is saved as v1.

Scenario test: `test_s17_design_feasibility.py`.

## Build note (28 Oct 2026): revision from the peer Reviewer; sourcing

`designer.revise` and `POST /api/design/revise`: the proposal Reviewer's design-level FATALs (`fix_in: design`) go
back to the Designer, which returns one revised design with changes per finding and what stays unresolved, under
the same guardrails. Designs record the trial their witness ids come from (`trial_for_design`). A sourcing check
flags appeals to unnamed studies and effect sizes with neither a witness id nor "assumed". Walkthrough:
`docs/archive/verify/design_revision.md`. Scenario: `test_s21_design_revision_loop.py`.

