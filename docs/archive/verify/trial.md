# The trial (+ literature): user-seat walkthrough (24 Oct 2026)

Features: `docs/features/05-literature.md`, `06-trial.md` (first version). Live NVIDIA NIM, in-app browser
on :8000, the night-shift nurses project; plus scripted end-to-end runs (`_logs/trial_live_2026-10-24.txt`).

## What was built

- `backend/research/`:
  - `librarian.py`: strategy, then OpenAlex + Europe PMC + one query per sub-claim, then legal open full text
    (PMC XML, then arXiv, then OA PDF), DOI lookup.
  - `reader.py`: hypothesis-blind records; provenance enforced in code; methods and results focused into
    16k characters.
  - `analyst.py`: sub-claims, matrix rows, computed witness weight.
  - `judge.py`: GRADE-style weighing; code-enforced guardrails.
  - `trial.py`: plan, then the approval gate, then a streamed run.
  - `store.py`: persistence, plus startup reconciliation of interrupted trials.
- Storage: tables `trials`, `trial_papers` (+ `db/migrations/008_trials.sql`).
- API: `/api/trial/*`. The plan runs nothing; `run` needs `{"approve": true}` and runs once; "I say"
  edits, add by DOI, PDF upload (base64), re-weigh.
- Frontend `trial.js`:
  - plan card with editable sub-claims, the ambiguities and an estimate;
  - live progress card, with the matrix filling in the Check panel;
  - verdict strip, cases for and against per sub-claim, gaps scoped to "these N papers", hypothesis weaknesses;
  - expandable records with provenance tags, "Upload PDF to complete", "Write your own I say".
- The conductor can now offer a trial; "Check this" plans one.
- Model use: shared cap of 4 concurrent calls; two retries with backoff before falling back; every record
  states which model read it, and the UI warns when the fallback did.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Check this → | Plan card: 4 editable sub-claims, "2 things your hypothesis leaves open", estimate, Approve and run | pass |
| 2 | Approve and run | Stage moves to Check; progress card (found / full text / analysed); matrix rows appear with access badges and fill in | pass |
| 3 | Wait | 15 papers, 9 with legal full text; all analysed in ~7.5 min; verdict after ~8.5 min | pass (slow) |
| 4 | Read the verdict | "Insufficient evidence" overall; sub-claim 3 "supported within limits"; no witness measured circadian misalignment in nurses; gaps phrased "None of the 15 witnesses…"; hypothesis weaknesses (no falsifier, undefined shifts, unoperationalised construct) | pass |
| 5 | Inspect the matrix | Full-text rows were empty (fixed, see 4 below); abstract-only rows correct | fail → fixed |

## Problems found and fixed

1. **OpenAlex HTTP 400**: `?` in a query is a wildcard. Queries are now reduced to plain keywords.
2. **Europe PMC returned nothing**: the Boolean query ANDed four concept blocks. Now at most three blocks, the
   comparison group and mechanism are never their own block, and a keyword retry runs when results are thin.
3. **Weak relevance**: searches leaned towards circadian biology. One extra query per sub-claim gives every link
   in the hypothesis its own witnesses.
4. **Empty full-text records** (the worst one): on long inputs Ultra spent the whole 3000-token budget on hidden
   reasoning and the JSON was cut off (199 visible characters). The extraction roles (Reader, Analyst,
   Librarian, support steps) now run with `enable_thinking: false`. The same truncation explained the
   "degraded" strategies, which had disabled the adjacent-field search.
5. **Rate limits**: 429s made most readings silently fall back to `gpt-oss-20b`. Two retries with backoff cut
   fallbacks to about 1 in 27 calls, and each record now says which model read it.
6. **Slow reads of 35k-character papers**: the Reader now gets abstract, methods, results, discussion and
   limitations within 16k characters; references and front matter are dropped.
7. **Narrative reviews weighted like systematic reviews** (0.52 for a literature review): a new
   `narrative_review` design with a low tier; `systematic_review` requires a reported search and selection method.
8. **Duplicated guardrail notes**: deduplicated.
9. **Stale "running" trials** after a reload or restart: interrupted trials are marked stopped at startup, and the
   panel refreshes a trial that claims to be running without a live stream.
10. Sub-claim numbers rendered under the text boxes: layout fixed.

## Final scripted run (after all fixes)

`_logs/trial_live_2026-10-24.txt`, 10 papers, ~7 minutes:
- Strategy not degraded; the adjacent-field search ran (physician shift work, EMS: 8 papers), so originality
  could be judged: **partial overlap**, citing physician sleep and burnout literature.
- 5 full text / 5 abstract only. **4 of 5 full-text records complete** (design, sample, measures, located
  results). The fifth was read by the `gpt-oss-20b` fallback during a 429 and came back empty; its record
  says which model read it, and the UI flags fallback readings.
- 3 of ~26 role calls fell back; the Judge ran on Ultra.
- Verdict: insufficient evidence overall. Sub-claim 2 (misalignment ↔ exhaustion) supported within limits
  (W1, W4, W10); sub-claims 1, 3 and 4 insufficient, with no witness against any of them, which the Judge
  reports rather than hides.

## Not built yet / known gaps

- Speed: free-tier NIM gives roughly one analysed paper per minute (15 papers ≈ 8-10 minutes).
- ~~Fallback readings should be re-read automatically.~~ Fixed 25 Oct 2026 (below).
- ~~Europe PMC's relevance lets in off-topic papers.~~ Tightened 25 Oct 2026 (below); borderline papers remain.
- Systematic-review tier (protocol, Screener, PRISMA flow) is not rebuilt; "Review" still uses the older pipeline.
- No Autopilot / Co-pilot switch yet (feature 02); sub-claims are always shown for approval.
- ~~"Weigh again" does not re-analyse rows after a sub-claim edit.~~ Fixed 25 Oct 2026: "Edit sub-claims" (below).
- ~~Thinker reviews of the verdict are not wired.~~ Fixed 25 Oct 2026 (below).

## Loose ends closed (25 Oct 2026)

Scenario tests: four new tests in `test_s16_trial_neutral_court.py` (stubbed models, a fake Europe PMC client).
Gate: 68 passed, 1 skipped. Live checks ran on a scratch copy of the database, so the real nurses trial (which
the design and proposal build on) was not changed.

1. **Fallback readings are re-read.** After the main pass of a run, every paper whose record says a model other
   than Ultra read it (`record.read_by`) is read again with the primary model only (`reader:primary` →
   `get_role_llm(..., allow_fallback=False)`), and its matrix row is redone. If the primary still can't answer,
   the fallback record stays and stays flagged ("a re-read with the primary failed too"); the verdict is never
   held up. Events: `rereading`, `paper_reread {recovered}`. Code: `trial.reread_fallbacks`, `reader.read_by_fallback`.
   *Not run live*: it needs a fresh run in which the fallback answers. Covered by two S16 tests (recovered / kept).
   It only applies within a run: papers in older trials keep their flag, because the fetched text is not stored.
2. **Edit sub-claims → every row redone → weighed again.** `POST /api/trial/{id}/subclaims` (SSE, requires
   `approve: true`, only on a complete trial, claimed atomically as `reanalysing`; a restart puts it back to
   `complete`). Records stay; the Reader does not run. A row that can't be redone is cleared rather than left
   answering the old sub-claims. Panel: "Edit sub-claims" opens an in-page dialog (one claim per line, at most 6)
   whose confirm button states the cost ("Redo 15 rows and weigh again"). "Weigh again" stays Judge-only.
   *Live*: sub-claim 1 rewritten as "Night-shift nurses sleep at the wrong biological time more often than
   day-shift nurses." 15 rows redone and re-judged in ~2 minutes; the new verdict names the new sub-claim
   (insufficient evidence: no witness addresses it), sub-claim 3 still supported within limits.
3. **Thinker reviews of the verdict.** "Ask thinkers about this verdict" sends the overall verdict, per-sub-claim
   cases for and against, conflicts and gaps to `/api/thinkers/review` (artifact "trial verdict") and shows the
   existing reviews card. *Live*: Popper ("not a failed test — the absence of a test"), Hume (separates the
   observed conjunction from the causal story), Nightingale ("not one measured the thing the hypothesis hangs on"),
   all objecting, 5 critical concerns between them.
4. **Europe PMC relevance.** `sort=RELEVANCE` is not supported (the service returns an error; the default
   order is already relevance; `sort` takes fields such as `CITED desc`), so the search now matches titles and
   abstracts only (`TITLE_ABS:(…)`: 2848 → 36 hits for the plain keyword query), and records whose title and
   abstract share fewer than two of the query's content words are dropped. The count and titles are recorded on
   the strategy (`europepmc_dropped_off_topic`), streamed as `search_filtered`, and shown above the matrix.
   *Live*: with `TITLE_ABS` the night-shift query returned only nurse/shift-work papers and the word filter
   dropped none. One borderline paper (intimate-partner violence among night-shift nurses) still gets in: it
   shares the population words.

Problem found during the live check: the edit dialog said every paper would be "read again"; only the rows are
redone. Wording fixed.
