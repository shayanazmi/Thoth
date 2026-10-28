# 06 · The trial ("Check")

> **Built 24 Oct 2026**: walkthrough and known gaps in [`docs/archive/verify/trial.md`](../archive/verify/trial.md).

> Vision: §4 (originality with adjacent-field search), §5, §8 (honest claim status), §11.

## What the owner wants

Stop treating the literature as an annotated bibliography. **The hypothesis is the thesis on trial;
each paper is a witness.** Evaluate every paper on four dimensions and build a **synthesis matrix**
(papers as rows, hypothesis sub-claims as columns), not article-by-article notes.

1. **Epistemological and variable alignment**: construct validity and operationalisation (how did they
   measure "burnout"?). "They Say / I Say" (Graff & Birkenstein): is this paper the floor my hypothesis
   stands on, or the ceiling it tries to break?
2. **Evidence vectoring**: direction (convergent / divergent / null), weight, and **boundary
   conditions**. A contradiction marks the limits of the hypothesis; it isn't discarded as wrong.
3. **Methodological asymmetry**: when papers conflict, the tie-breaker is usually in the methods
   (sample, controls, a cross-sectional design making causal claims). Use the Matrix Method (Garrard)
   with columns for sample, data collection and controls.
4. **Strategic gap interrogation**: blind spots (stated limitations the hypothesis could target) and
   premise testing (an unproven assumption treated as fact).

Each paper gets a stance in the write-up: **advancement**, **reconciliation** or **pivoting**.
Thoth drafts the per-paper "I say"; the user edits it.

Agreed refinements (from my pushback):
- **A neutral court, not a prosecution.** Thoth argues both sides with equal effort. The verdict can go
  against the hypothesis.
- **Witness weight** comes from design strength and access level, not just direction.
- **Pivoting** must show the specific evidence that justifies it. Otherwise the Judge refuses it, because
  manufacturing gaps is forbidden (vision §11).
- **Paywalled witnesses** fill what's known, mark the rest "not reported in abstract", and carry a lower weight.

## Answers the trial gives (kept separate)

1. **What does the evidence say?** A verdict per sub-claim and overall.
2. **Has this been done?** Originality against prior work, including adjacent fields.

### Verdicts (per sub-claim and overall)

| Verdict | Meaning |
|---|---|
| `already_established` | Strong convergent evidence; the hypothesis restates known findings → the originality answer flags it |
| `supported_within_limits` | Convergent, with boundary conditions identified (populations, settings, measures) |
| `contested` | Credible witnesses on both sides; the methodological asymmetry explains (or doesn't explain) the split |
| `contradicted` | Weighted evidence goes against it |
| `insufficient_evidence` | Too few or too weak witnesses, or mostly abstract-only. Never upgraded to a stronger verdict |

### Originality

`likely_novel | partial_overlap | substantially_covered | insufficiently_assessed`.
`likely_novel` is impossible without at least one adjacent-field search (the existing guardrail in
`originality.py`) and is never based on a model saying "this is novel" (vision §11).

## The synthesis matrix

Rows = papers (witnesses). Per-paper columns:

| Column | Filled by | Source |
|---|---|---|
| Design · sample · setting | Reader (neutral) | paper record |
| Operationalisation of each construct | Reader → Analyst compares to the hypothesis' constructs | paper record |
| Construct match | Analyst: `same | proxy | different` + why | |
| Direction **per sub-claim** | Analyst: `convergent | divergent | null | not_addressed` | with locator |
| Boundary conditions | Analyst | where the effect held or failed |
| Methodological strength | Analyst, using a CASP-style checklist per design | design, controls, bias risks |
| Witness weight | computed: design tier × appraisal × access level | |
| Blind spots / premises | Analyst | limitations the hypothesis could target; unproven assumptions |
| Floor or ceiling | Analyst | They Say / I Say |
| "I say" + stance | Analyst drafts → **user edits** | advancement / reconciliation / pivoting |

Every cell links to its locator in the paper record. A cell built from an abstract-only record is greyed and tagged.

The matrix fills live during a run (02 "Live work").

## Pipeline

```
hypothesis vN + sub-claims
   │
   ├─ Librarian: search (incl. adjacent fields for originality) → library
   ├─ Reader (hypothesis-blind, parallel): paper records
   ├─ Analyst (per paper, parallel): matrix row against sub-claims
   ├─ Judge (once): weigh witnesses → verdict per sub-claim + overall, originality,
   │                 explanation of conflicts via methodological asymmetry,
   │                 the strongest case FOR and the strongest case AGAINST
   └─ Thinker reviews (optional, independent) of the verdict
```

The Judge must write **the case for and the case against**, each from the strongest witnesses, before it
gives a verdict. That's what makes the court neutral.

### As built (29 Oct 2026): appraisal and citation neighbours

- **Appraiser** (role `appraiser`, `backend/research/appraisal.py`): hypothesis-blind, one call per readable paper,
  right after the Reader. The checklist is chosen in code from the Reader's design:
  - Cochrane RoB 2 domains for RCTs;
  - JBI for quasi-experimental, cohort, case-control, cross-sectional, qualitative and systematic reviews;
  - MMAT for mixed methods; SANRA for narrative reviews;
  - core questions only for anything else, which the paper says.

  Code turns an answer without a locator into "unclear", and makes items that need the full text "not assessable"
  when only the abstract was read. The overall judgement is computed from the items: critical "no" → high;
  critical unclear → some concerns.
- **Weight v2** = design tier × access factor × appraisal factor (low 1.0, some concerns 0.85, high 0.6, not assessable
  0.8 only when read in full, core only 0.9). The basis is stored in `appraisal.weight_basis` and shown on hover.
  Papers from older runs keep their weight.
- **Judge**: each witness carries its appraisal summary. Code lowers certainty when every supporting witness is high
  risk or not assessable.
- **Citation neighbours**: papers citing, or cited by, the 3 strongest witnesses (OpenAlex, then Semantic Scholar;
  abstracts only; never witnesses), stored in `adjacent_json.citation`. The Judge names the closest prior work by
  W#/C# id. `likely_novel` is refused when this run's citation search did not run; older trials are only noted.
- **Coverage**, set in code on every verdict: a lightweight scan, or the systematic review's counts and limitations.
- Cost: about 3 calls per paper plus 3 (about 48 for 15 papers). Evidence: `docs/archive/verify/evidence_depth.md`; tests S22, S24.

## Output (what the user sees)

1. **Verdict strip**: overall verdict, originality, and a one-sentence reason.
2. **Per sub-claim**: verdict, top witnesses on each side, and the boundary conditions.
3. **The matrix**: sortable and filterable (e.g. "show divergent, high-weight").
4. **Gaps**: blind spots and premises worth targeting, each tied to the witnesses that reveal it.
   No gap without a witness.
5. **Provisional / reviewed status**, with an explicit list of what's unresolved.

## Agents

| Agent | Job | Model |
|---|---|---|
| Analyst | Sub-claims (04) + matrix rows | Ultra |
| Judge | Weighting, case for and against, verdicts, originality | Ultra |

Reused: `originality.py` (adjacent queries, guardrail), `counter_evidence.py` (divergent search),
`integrity_gate.py` (locator checks on cells).

## Prompts

[09 § Analyst](09-agents-and-prompts.md#analyst), [§ Judge](09-agents-and-prompts.md#judge).

## Walkthrough (acceptance)

1. Put a hypothesis on trial → rows appear live, and every cell opens its locator.
2. Pick a divergent, high-weight paper: its boundary conditions are filled, and the Judge's "case against" cites it.
3. Make most of the library abstract-only (test fixture) → the verdict is `insufficient_evidence` or carries
   an explicit caveat; it is never `already_established`.
4. Edit an "I say" cell → it's marked as user-authored, and the Writer (08) uses the user's text.
5. With no adjacent-field search run, originality is never `likely_novel`.

Scenario tests: `test_s16_trial_neutral_court.py`, `test_s6_originality_adjacent_search.py` (planned).
