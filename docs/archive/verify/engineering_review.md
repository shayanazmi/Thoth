# Engineering review of PR #1 (Step 0a), 29 Oct 2026

**Scope.** `main...feat/evidence-depth`: 67 files, about 4,650 lines. The review used the Claude Code `code-review` skill at high
effort, from eight angles:
- correctness: line by line, removed behaviour, cross-file callers;
- cleanup: reuse, simplification, efficiency;
- altitude;
- the CLAUDE.md conventions.

Complexity and over-engineering are covered separately by the structure audit (`structure_audit.md`). The billed cloud
review (`/code-review ultra 1`) is the owner's to run; its findings will be added here if it is run.

**Gate after the fixes: 129 passed, 1 skipped** (124 before; 5 regression tests added).

| # | Finding | Severity | Fix | Test |
|---|---|---|---|---|
| 1 | **Repeated records without an OpenAlex key:** paging is by page number, and the last page asked for fewer records (the remaining quota), so OpenAlex returned records already fetched. A budget of 148 recorded 48 duplicates and never fetched records 100–147, while the stop rule claimed "the first 148". | correctness | Every request asks for a full page, and records beyond the quota are cut locally (`review._identify`). | S23 `test_every_page_is_a_full_page…` |
| 2 | **A finding "resolved" without any design change:** a design finding the Reviewer simply didn't repeat (model variance) was recorded as resolved by the *same* design version. | correctness | It counts as resolved only if the design version changed since it was raised. Otherwise it is carried forward as still held, saying so (`proposal.resolved_since`, `carried_held`). | S26 `test_a_finding_not_repeated_without_a_design_change…` |
| 3 | **A weak Europe PMC query lost its results:** when the Boolean query returned 1–2 records they were thrown away for the relaxed query, never stored or logged. | correctness | They are kept and logged; the relaxed query then runs as its own logged search. | S23 `test_a_weak_europe_pmc_query…` |
| 4 | **Decisions could land in another review:** the decisions route didn't check that the record belongs to the review in the URL. | correctness / integrity | `review.decide(..., review_id=)` checks it (`review_store.review_of`) and returns 404 otherwise. | S23 `test_a_decision_cannot_be_written_into_another_review` |
| 5 | **Citation lookups re-read every record** for each seed and each direction. | efficiency | Running counters in `_chase`. | covered by S23 citations |
| 6 | **The whole schema script ran on every store call**, hundreds of times per review. | efficiency | `init_db` runs once per database file per process (`db._READY`), and again if the file is gone. | the whole gate |
| 7 | **Untitled citation neighbours escaped deduplication:** they were stored with a `None` reference, which reads as "no match". | correctness | They are stored with their C-id. | S24 `test_untitled_neighbours_are_deduplicated_too` |
| 8 | **The launch config committed a machine-specific path:** a per-session temp folder for the walkthrough database. | conventions | It now uses `scratch/walk.db` (`scratch/` is gitignored). | n/a |

Nothing was found against the CLAUDE.md integrity rules: no fabricated counts, `access` never upgraded, approval gates intact.
