# Study design: user-seat walkthrough (25 Oct 2026)

Feature: `docs/features/07-study-design.md`. Live NVIDIA NIM, in-app browser on :8000, the night-shift nurses
project (which has a completed trial).

## What was built

- `backend/research/designer.py`: Designer role (prompt from doc 09), fed with the latest completed trial's
  lessons and the researcher's resources. Witnesses are numbered W1.. as the Judge numbered them. Code guardrails:
  - a measure cites a real witness, labelled **used by** (the witness reported that instrument) or **related to**
    (cited, but the witness didn't report it), or is marked **new · needs validation**;
  - non-causal designs cannot claim causation;
  - numeric sample sizes must state assumptions or call for a power analysis;
  - closed feasibility labels; the recommendation must be one of the candidates.
- `/api/design` (get, resources, propose, choose). Resources, candidates and the chosen design are versioned notebook
  sections (`resources`, `design_candidates`, `design`); no new table.
- Frontend `design.js`: a Design stage between Review and Draft. It appears as "ready" once a trial has a verdict.
  Resources form, candidate cards (can / cannot conclude, sub-claims tested, cited measures, sampling, threats by
  validity type, feasibility and blockers), choose with your own notes, "Ask thinkers to critique it". The trial's
  verdict message now offers "Design a study".

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Opened the Design stage | Hypothesis, six resource fields with examples, "Propose designs · one model call" | pass |
| 2 | Entered resources (4 months part-time, ~60 night / 120 day nurses at one hospital, no budget, basic SPSS, student ethics, survey software only) and proposed | After ~4 min (rate-limit backoff): 3 candidates. Recommended **prospective cohort, 4 waves over 8 weeks** (feasible with changes); cross-sectional with mediation (feasible); N-of-1 with actigraphy (not feasible: no devices) | pass |
| 3 | Read the recommended design | "Cannot conclude: Causation…"; measures tied to witnesses W3/W9 with honest notes; sample size given as power-analysis inputs; threats under all four validity types; blockers matched to the resources (no incentive budget, ethics timeline, no actigraphs) and what would make it feasible; explicitly targets the trial's gap | pass |
| 4 | Chose it with a note | Saved as Design v1, "chosen with your notes", note kept; Design stage marked done | pass |
| 5 | Asked thinkers to critique | Popper (objecting): "the design does not test it. It watches." Hume (mixed): the "because" the design cannot earn. Nightingale (objecting): "a proxy war", with survivor bias in the stable-schedule inclusion criterion | pass |

## Problems found and fixed

1. A measure could cite a witness that never used the instrument (MBI-EE cited to W3, which didn't name its
   instrument). Citations are now labelled *used by* or *related to* by checking the witness's own measures.
2. Clicking the Check stage re-planned a trial even when one existed; now it only opens the panel.
3. (Test-only) The note prompt is a native `window.prompt`, which blocks automation. It was stubbed for this
   walkthrough. Native prompts (here, "I say", notebook edits) should become in-page dialogs.

## Known gaps

- The Designer took ~4 minutes under rate-limit backoff (estimate says 1-2).
- "Approx. 80-100 completers suggested by simulation studies" cites unnamed studies; the guardrail only checks
  that assumptions are stated, not that such claims are sourced.
- Nightingale echoed a dossier heading verbatim ("the comparison that removes the excuse"): an early catchphrase sign.
- Thinker critiques are advisory; there is no "revise the design from the critiques" step yet.
