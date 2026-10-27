# Systematic review (PRISMA): user-seat walkthrough (25 Oct 2026)

Feature: `docs/features/05-literature.md` tier 3 (systematic review), rebuilt on the trial engine.
Live NVIDIA NIM, in-app browser on :8000, the night-shift nurses project.

## What was built

- `backend/research/review.py` + `review_store.py`:
  - **Protocol**: drafted by the Librarian (PEO/PICO, eligibility criteria, search strings). The researcher
    edits it; nothing runs.
  - **Run**: only on `approve: true`, claimed once.
  - **Identification**: OpenAlex + Europe PMC. Duplicates are kept as records and counted, never hidden.
  - **Screening**: a new Screener role (batched title/abstract, one-by-one full text) with code guardrails:
    - every exclusion needs one protocol criterion as its reason;
    - "maybe" is forbidden at full text;
    - the Screener never sees the hypothesis.
  - **Mode switch per review**:
    - *Human-in-the-loop* pauses at each stage until every decision is confirmed (keyboard I / E / M,
      "accept the rest").
    - *Auto* applies decisions and queues confidence < 0.7 for audit.
  - **Included studies** become a linked trial (records, matrix rows, verdict).
  - **PRISMA 2020 counts** are computed only from stored records, after every change.
  - **Blocked state**: when the Screener can't decide, records stay `unscreened` and "Try again" resumes.
- Tables `sys_reviews`, `sys_review_records` (+ `db/migrations/010_systematic_reviews.sql`); `/api/review/*`.
- Frontend `review.js`: protocol card (editable criteria, search strings, mode switch, estimate), live PRISMA flow,
  screening queue with quoted evidence per criterion, audit queue, blocked / try-again, completion messages. "/review",
  the Review stage and the conductor's systematic-review offer all start this flow; the old formal-review pipeline
  is no longer reachable from the UI (code kept, to archive).
- Tests: `backend/tests/scenarios/test_s15_systematic_review.py` (6 tests).

## Walkthrough 1: Human-in-the-loop (strict protocol)

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Pinned the hypothesis, typed `/review` | Protocol in ~30s: population (licensed hospital nurses), exposure (night or rotating-with-nights), comparison (**permanent day shifts required**), outcomes (**validated emotional-exhaustion subscale required**), designs, dates, languages; a three-block Europe PMC string | pass |
| 2 | Edited "dates" to "2005 or later", kept Human-in-the-loop, approved | Search: 50 records (25 + 25), 1 duplicate removed | pass |
| 3 | Waited | First batch screened with quoted evidence per criterion. **Second batch blocked**: the answer parsed to no decisions (truncation). Fixed (below); "Try again" resumed from where it stopped | fail → fixed |
| 4 | Screened 10 by keyboard | M ×8, I ×1, and an override: the Lebanese MBI psychometrics study excluded for *designs*. Counts updated live and added up (17 excluded with reasons + 32 sought = 49 screened) | pass |
| 5 | Accepted the remaining 39, continued | 32 sought: **13 not retrieved** (no legal open full text), 19 assessed in full | pass |
| 6 | Full-text pause | The Screener excluded all 19 (exposure 10, comparison 7, outcomes 1, population 1; 95% confident): none had both a permanent-day comparison group and an emotional-exhaustion subscale | pass (honest) |
| 7 | Accepted, continued | Complete, **0 included**. The closing message first said "0 studies included… read in full and weighed" and created an empty trial. Fixed (below) | fail → fixed |

## Problems found and fixed

1. **Screener batch truncated** (5 records × 7 criteria × quotes > 3000 tokens): budget raised to 6000, evidence
   quotes capped at 15 words, batches of 4, and records a batch misses are retried one by one before blocking.
2. **"Blocked" wording** said "couldn't be reached" when the model answered without decisions; reworded, and the
   stale note now clears on resume.
3. **Zero included**: now reported as "no study met every criterion", naming the criterion that excluded most
   and suggesting loosening it or uploading paywalled PDFs. No empty trial is created (test added).
4. **Browser state**: this tab had lost its saved project state, so the hypothesis had to be re-pinned. The hypothesis
   and question live only in localStorage on the client, although the server stores accepted notebook sections.
   Not fixed here (feature 02: server-side project state).

## Walkthrough 2: Auto mode (broader protocol)

Run from a script on the same project, with comparison broadened to any shift-pattern contrast and outcomes to any
validated burnout measure. Log: `_logs/systematic_review_auto_2026-10-25.txt`. Results below.

| # | Saw | Verdict |
|---|---|---|
| 1 | Protocol in 34s; search 50 records, **3 duplicates removed**; Auto mode never paused | pass |
| 2 | Title/abstract: 8 excluded (designs 5, exposure 2, comparison 1), 39 sought; 20 not retrieved, 19 assessed in full | pass |
| 3 | Full text: 18 excluded (exposure 17, unspecified 1), **1 included** (oncology/haematology nurses, Palestinian hospitals) | pass (see finding 1) |
| 4 | Included study read and analysed into a linked trial, Judge verdict *insufficient evidence* (the single witness addressed no sub-claim); ~10 minutes in total | pass |
| 5 | Audit queue: 10 title/abstract + 1 full text (the "unspecified" exclusion the guardrail flagged) | pass |

### Findings

1. **Overlapping protocol criteria.** The drafted *exposure* criterion repeated the comparison requirement ("…versus nurses
   assigned to permanent day shifts"), so broadening *comparison* changed nothing and 17 full-text exclusions were for
   exposure. Fixed in the protocol prompt: each criterion covers one thing. Not yet re-run live.
2. **Screener and Analyst can disagree.** The Screener included the Palestinian study as eligible; the Analyst then found
   it addressed none of the sub-claims. Both are recorded and the verdict says so. A future step could flag such
   disagreements in the audit queue.
3. **Most open-access papers fail strict nursing protocols.** About 40% of sought records had no legal open full text.
   "Upload PDF to complete" exists in the trial but not yet in the review's not-retrieved list.

## Not built yet / known gaps

- Upload a PDF for a not-retrieved record inside the review (the trial has this).
- Client project state (hypothesis, question) is localStorage-only (feature 02).
- Re-running a review with an edited protocol creates a new review; there is no "revise and re-screen" path.
- The old formal-review pipeline code (`orchestrator`'s PRISMA path, `intellectual_rigour/prisma.py`) is unreachable from the
  UI but not yet archived.
