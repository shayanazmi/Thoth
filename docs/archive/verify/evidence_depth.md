# Evidence depth (Phase 2): a user-seat walkthrough, 29 Oct 2026

Covers bugs #1+#2 (the formal review's scale and stopping rules), #5 (citation following) and #6 (study-quality
appraisal). The plan is `~/.claude/plans/extreme-detail-three-phase-end-to-end-im-cryptic-lemur.md`.

**How it was run.** The real app on a copy of `db/store.db` (`THOTH_DB_PATH`; the `thoth-evidence` entry in
`.claude/launch.json`, port 8002), in the in-app browser, on the "why do night-shift nurses burn out more?" project.
Live keys: NVIDIA, OpenAlex (added 29 Oct) and Semantic Scholar.

**Gate.** `pytest backend/tests/scenarios`: **112 passed, 1 skipped**.
- New: S23 (10 tests, the review at scale) and S24 (7 tests, appraisal and citations in the trial).
- Updated: S15 (stub signatures and the original single-pass budget), S14 (11 model calls: the Appraiser adds one per paper), S11 (search rows are deleted with the project), S22.

---

## 1. Systematic review, end to end

1. **Protocol card.** `/review` drafted a protocol. The new **Budget and stopping rules** section showed the defaults (300 database records, 200 citation records, 2 rounds, stop after 50 irrelevant in a row, 30 full texts) with their estimate: "up to 247 model calls, about 43–86 minutes".
2. **Budget edited.** I changed it to 150 / 60 / 1 round / 25 / 5. The estimate re-computed as I typed: "up to 75 model calls, about 12–24 minutes". Mode: Auto. Approve and run.
3. **Identification.** Every request went into the search record (database, query, page, returned, new, total, cost):
   - **Europe PMC** returned **503** (their outage). Recorded as `source_error`, and its unused quota went to OpenAlex.
   - **Semantic Scholar** bulk search returned 2 matches. **This was a finding** (section 4).
   - **OpenAlex:** page 1 returned 100 and page 2 returned 48, of 301 matches, at $0.001 a request. Recorded as "OpenAlex: the first 148 of 301 matches by relevance were retrieved (record budget)".
   - The PRISMA flow showed **150 identified from databases** and **0 by citation searching**, with 2 duplicates removed.
4. **Title/abstract screening.** Batches ran in parallel waves; the banner read "Title/abstract screening · Auto · 12/148 screened · Stop".
   - One batch came back empty, and the run **blocked honestly**: 4 records were left "unscreened" and nothing was decided on the model's behalf.
   - Fixed (section 4), then **Try again** resumed and finished: 117 excluded and 31 "maybe". The early-stop rule (K=25) did not fire, because relevant records were spread through the ranking.
5. **Citation round 1.** 10 seeds from the records that passed. The round stopped at its budget: "Citation searching stopped at its budget of 60 records". The PRISMA flow showed **60 identified by citation searching**, counted apart from the 150 database records, and 19 records were removed by the off-topic filter (counted, not hidden).
6. **Retrieval and full text.**
   - With a full-text budget of 5, the remaining eligible records were counted as **"not retrieved (full-text budget)": 40**.
   - The 3 assessed in full were excluded (comparison), and 2 had no legal open full text.
7. **Result: complete, 0 included.** The note originally said only that no study met every criterion, which hides the 40 unread records. Fixed: it now adds "30 eligible record(s) were not read at all because of the full-text budget; raising it would assess them".
8. **Raising the budget.**
   - The panel offered **"Read 10 more (about 40 model calls)"**. The first version would have raised it by all 40 at once, about 160 calls; fixed to 10 at a time.
   - Clicking it superseded the old `ft_budget` entry (kept, marked "no longer applies") and resumed at retrieval.
   - Full-text screening blocked again on one paper (section 4); after the fix, **Try again** finished.
   - **Final:** 210 identified (150 databases + 60 citations), 45 sought, 15 retrieved in full or attempted, 7 assessed and excluded (comparison 4, outcomes 3), 8 with no open full text, **30 still beyond the budget**. 0 included.
   - The limitations list names: the Europe PMC failure, Semantic Scholar's 2 matches, OpenAlex's 148 of 301, the citation budget, the full-text budget, the English-only restriction, OpenAlex's core corpus, and "Reaching these stopping conditions … does not prove that no other relevant literature exists".
9. **The panel's long sections** load when opened. "Why the search stopped" shows each rule with a badge. "Search record" is a table of every request. "All records" pages 50 at a time with filters (included, excluded, not screened, from citations, duplicates).

**Not exercised live** (covered by S23):
- **Stop**, then Continue from the stored cursor;
- the early-stop rule firing;
- an override inside its run superseding it;
- a review with included studies creating a new trial after a budget raise.

The review on the nurses protocol included nothing because its comparison criterion requires a day-shift comparison group.

## 2. The trial (lightweight check), end to end

Run from the hypothesis card's "Check this →". The plan card showed the new cost line: "each paper appraised with a checklist for its design; papers citing or cited by the strongest witnesses checked for prior work · about 48 model calls". The run took **505 s** for 15 papers, 9 of them read in full.

**Appraisal.** The checklist was chosen per design, and the Appraiser never saw the hypothesis. 7 papers came out high risk, 1 low, 1 some concerns, and 6 "not assessable" (abstract only). For example:

| Paper (short) | Design → checklist | Appraisal | Weight |
|---|---|---|---|
| Circadian misalignment increases mood vulnerability | RCT → RoB 2 | high (no blinding, per-protocol) | 0.54 |
| Burnout among Lebanese nurses | cross-sectional → JBI | low | 0.45 |
| Impact of circadian rhythms on business efficiency | systematic review → JBI SR | some concerns | 0.81 |
| Effects of shift work on sleep quality | narrative review → SANRA | high | 0.18 |
| Night shift work and sleep in older nurses | qualitative → JBI qualitative | not assessable (abstract) | 0.18 |

**The verdict.**
- Insufficient evidence on all three sub-claims.
- Certainty was rated down with appraisal-grounded reasons, for example "Risk of bias in W3: no blinding, per-protocol analysis, expectation bias on subjective VAS" and "Confounding not controlled (chronotype, sleep duration, light exposure, workload)".
- `appraisal_summary` is computed in code.

**Citation following.**
- 3 seeds (the strongest witnesses) produced 20 neighbours, read at abstract level only and labelled "cited by W14".
- The Judge named the closest prior work **by id: C11, C12, C20**, giving partial overlap.
- The "How originality and coverage were checked" section says: "A lightweight scan: the first page of results from OpenAlex and Europe PMC, not a systematic search."

## 3. What the walkthrough fixed (all covered by tests)

| Found live | Cause | Fix |
|---|---|---|
| Semantic Scholar bulk search returned 2 matches | Bulk search ANDs every term, and it sorts by id, date or citations, **not relevance**. The review's budget ("first N") and its early-stop rule need relevance order | Relevance search `/paper/search`, paged by offset (100 a call, up to 1000). Live: 424 matches, top results on topic |
| A screening batch returned no decisions → blocked | The Screener quoted the paper with double quotes inside its JSON evidence, so the JSON broke; a retry at temperature 0 broke the same way | The prompt asks for single quotes; retries carry a format note; empty batch answers are retried one record at a time; the full-text stage gets one retry. S23 test added |
| The zero-included note hid unread records | The note ignored `not_retrieved_budget` | The note says how many eligible records were never read, and why |
| "Raise the budget" would have read all 40 at once | It added the whole remainder | 10 at a time, with the cost shown |
| The Europe PMC failure listed twice | Both the stop entry and the search log were listed | Deduplicated |
| An abstract-only paper's weight was 0.45 × 0.55 × **0.8** | "Not assessable" was discounted on top of the access factor, for the same cause | Factor 1.0 when not assessable *because* only the abstract was read; 0.8 only when read in full and still unreported. The trial above ran before this fix, so its abstract-only weights (0.2) carry the old double discount |

**The Semantic Scholar key.** Every keyed request returned 429 (the key's quota is spent). The new fallback retries once without the key; the live log shows "429 → 200".

## 4. Known gaps left open

- Europe PMC was down (503) for the whole session, so its paging is verified only in tests and in the 28 Oct smoke test.
- The review's Stop/Continue was not clicked live. It is tested in S23, and Continue after a block was exercised live three times.
- Semantic Scholar relevance search has a hard limit of 1000 results; beyond that it records `source_exhausted` at 1000. That is honest but could read as "all matches".
