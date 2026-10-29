# A design-level FATAL goes back to the Design tab: user-seat walkthrough (28 Oct 2026)

Checklist item 5. Specs: `docs/features/07-study-design.md`, `08-writing.md`. Live NVIDIA NIM (slow free tier),
in-app browser on :8002 against a scratch copy of the database, the night-shift nurses project. The real database
was not changed.

## Why

In the proposal walkthrough (`verify/proposal.md`) the peer Reviewer's FATAL ("biweekly waves cannot establish that
misalignment precedes exhaustion") was about the chosen design. The Writer spent two revision rounds rewording the
Methods and the FATAL stayed open, because no wording can fix a design. Separately, the Designer's guardrail only
checked that assumptions were *stated*, so "approx. 80-100 completers suggested by simulation studies" passed.

## What was built

- **Reviewer** (`research/reviewer.py`): each finding says where it must be fixed, `fix_in`: `writing`, `design` or
  `evidence`. **Revision loop** (`proposal.review_loop`): only writing FATALs go to the Writer. Design and evidence
  FATALs are held, and the status says what they need ("FATAL R1 needs a change to the study design (Design tab:
  Revise the design)").
- **Revise the design** (`designer.revise`, `POST /api/design/revise`): the held design findings, the chosen design,
  the resources and the trial's lessons go to the Designer, which returns one revised design under the same
  guardrails, with `changes` per finding and what stays `unresolved`. It is offered first among the candidates.
  Choosing it is still the researcher's call, and makes the next design version.
- **Witness ids belong to a trial** (`designer.trial_for_design`): designs record the trial their ids come from. For
  older designs it is inferred from the titles their measures cite. The revision and the proposal's Writer both
  read that trial, not simply the newest one.
- **Stale sections** (`proposal.design_stale`): sections that restate the design (title and abstract, methods,
  expected outcomes, limitations, timeline) record the design version they were written from. When the design
  changes they are marked "written for design v1; the design is now v2". Sections from before this change are
  compared by time ("written before design v2 was chosen"). Shown as a badge and in the status.
- **Sourcing check** (`designer.unsourced`): a sentence that appeals to unnamed studies ("simulation studies
  suggest…") or states an effect size or ICC, with neither a witness id nor "assumed", is flagged on the design and
  in the guardrail notes.
- Frontend: findings show "fix in the study design" or "needs more evidence"; "Revise the design for this" in the
  Reviewer block; revision cards show what changed per finding and what is still open; unsourced sentences on
  cards and on the chosen design; the stale badge on proposal sections. The design panel now fetches the server's
  copy once per page load.
- `backend/tests/scenarios/test_s21_design_revision_loop.py`: 5 tests, written before the code.
  Gate: 83 passed, 1 skipped.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Ran the peer Reviewer again on the nurses proposal | R1 FATAL (the biweekly-waves problem) tagged **design** and held; 0 revision rounds spent (2 in the earlier run). Three MAJORs tagged design, two MINORs writing, one MINOR evidence | pass |
| 2 | "Revise the design for this" | "A revised design is ready: Prospective Cohort with Daily EMA (14 days) - Revision 1": morning surveys for the prior night's sleep timing, evening surveys for exhaustion, a one-day lag. Still open: no budget or lab for a melatonin marker, so the subjective proxy remains a limitation | pass (after fix 1) |
| 3 | Read the revision card | "Revision of 'Prospective Cohort with Repeated Measures (4 waves over 8 weeks)' answering the peer Reviewer (R1)", the change, "Still open…", and an **Unsourced** flag on a sample size from a "Monte Carlo simulation" with no stated assumptions | pass |
| 4 | Chose it | Design v2 | pass |
| 5 | Opened the Draft tab | Five sections badged "written before design v2 was chosen"; status lists them with "Regenerate it", plus the held FATAL | pass (after fix 2) |
| 6 | Regenerated Methods | Methods now describes the 14-day EMA burst ("which biweekly waves could not achieve"); its stale badge is gone | pass |

## Problems found and fixed

1. **Witness ids read against the wrong trial.** The first revision rejected W9 ("not a witness in this trial") because
   it used the project's newest trial (a later 1-paper trial), not the 15-paper trial the design was built from.
   Designs now carry their trial, older ones get it inferred, and the revision and the Writer use it. After the
   fix, rMEQ is "used by W9" (the chronotype study that did use it).
2. **No section was marked stale after choosing v2.** The proposal's sections predate recording design versions;
   they are now compared by time with the current design version.

## Known gaps

- Choosing a revised design doesn't offer to regenerate the stale sections in one step; each section is
  regenerated by hand.
- The `fix_in` tag is the Reviewer's judgement. A design problem it labels "writing" still goes to the Writer.
- The sourcing check is lexical. It catches "studies suggest" and effect sizes, not every unsourced number.
- Evidence-level findings are held and listed, but there is no "find more evidence" step from the proposal yet.
- The held FATAL stays in the status until the Reviewer is run again on the revised proposal.
