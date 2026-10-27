# Hypothesis: markers, rivals, versions: user-seat walkthrough (27 Oct 2026)

Feature: `docs/features/04-hypothesis.md` (checklist item 2). Live NVIDIA NIM, in-app browser on :8002 against a
scratch copy of the database, the night-shift nurses project. The real database was not changed.

## What was built

- `backend/research/hypothesis.py`: strength markers, one model call per hypothesis version (role `analyst`),
  cached in the notebook (`hypothesis_markers`) and recomputed when the rules change. Code guardrails:
  - a marker counts only if the words it quotes are in the hypothesis;
  - vague placeholders ("things", "it", "people") are never constructs; constructs are de-duplicated by name;
  - a scope must be more than one word and add a word beyond the constructs and the comparison;
  - a trial needs at least two named constructs; a missing comparison, scope or falsifier is a weakness, not a
    blocker; with no model the markers are "not checked" and block nothing.
- `backend/conversation/projects.py`: current version, version of a given text, rivals (every rival written,
  minus retired ones and the current main), retire, swap (the rival becomes a new version; the old main is
  parked). Routes: `GET /api/projects/{id}/markers`, `POST /api/projects/{id}/rivals/retire`, `…/rivals/swap`.
- Trials are tied to a version: new columns `trials.hypothesis_version` and `trials.remapped_from` (SQLite in
  `init_db` with `ALTER TABLE` for older databases, Postgres in `db/migrations/011_trial_hypothesis_version.sql`).
  `GET /api/trial/{id}` and `/latest` add `hypothesis_now` and `stale`; trials from before this change get their
  version inferred from their hypothesis text. Planning refuses a hypothesis without two named constructs (400 with
  the reason) and returns its weaknesses.
- Re-map: `POST /api/trial/{id}/remap` plans a trial of the current hypothesis on the same library (papers and
  hypothesis-blind records copied, the researcher's "I say" not carried over, strategy and adjacent search
  reused). It runs only through `/run` with `approve: true`, which then redoes rows and the verdict only: no search
  and no Reader.
- Frontend: `hypothesis.js` (markers line on the card through a new `hypCardExtras` hook in `chat.js`; Strength and
  Rivals sections in the Hypothesis panel with Park, Swap in, Retire; the swap message offers a re-map), the trial
  panel shows a stale banner with "Re-map these papers to vN", the trial plan card shows weaknesses and re-map
  wording, and `api.js` errors now carry the server's reason.
- `backend/tests/scenarios/test_s13_hypothesis_versions_and_rivals.py`: 7 tests, written before the code.
  Gate: 67 passed, 1 skipped.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Opened the nurses project | Card: "✓ shift type, emotional exhaustion, circadian misalignment · ✓ Direction · no scope · falsifier missing" | pass (after fixes 1-2) |
| 2 | Hypothesis panel → Park a rival ("…because they carry a heavier workload with fewer staff") | Listed under Rivals with Swap in / Retire | pass |
| 3 | Swap in | Card shows v2 = the rival; the old hypothesis is now the parked rival; v2 markers "✓ shift type, emotional exhaustion, workload, staffing level · ✓ Direction · no scope · falsifier missing" | pass (after fix 4) |
| 4 | Opened the trial | "This verdict is for v1 of your hypothesis. It is now v2: …" with "Re-map these papers to v2" | pass (after fixes 3, 5) |
| 5 | Re-map → plan card | "Re-uses the 1 paper of the previous trial; nothing is searched or read again"; new sub-claims for workload and staffing; "Weaknesses the Judge will cite: falsifier missing" | pass (after fix 6) |
| 6 | Approve and run | One row redone from the existing record (read by Ultra in the original run), then the verdict: insufficient evidence ("does not test the hypothesis: it lacks measures of workload and staffing"). New trial: v2, not stale; old trial: verdict kept, labelled stale | pass |
| 7 | In a thread: `/hypothesis Things just get worse at night.`, then Check this → | Card: "needs named constructs · no comparison · no scope · falsifier missing"; "Couldn't plan the trial: Name what varies first: a trial needs at least two named constructs…"; no trial created | pass (after fix 7) |

The project's latest finished trial (made by another session) had only one analysed paper, so the re-map reused one
paper. The 15-paper trial would re-map the same way.

## Problems found and fixed

1. **Repeated construct**: the model named both "night-shift" and "day-shift" as "shift type". De-duplicated.
2. **"nurses" counted as population and scope**, later "Night-shift nurses": they name a population but scope
   nothing. A scope now has to be more than one word and add a word beyond the constructs and the comparison.
3. **Old trials could never be stale**: they had no recorded version. The version is inferred from the text.
4. **Swap offered "Put it on trial" instead of re-map** when the trial panel hadn't been opened yet in the page; it
   now asks the server for the latest trial. The swap also cleared the cached trial, so the Check stage then planned
   a new (unrun) trial; it now marks the cached trial stale instead.
5. **Stale copies from localStorage**: markers and the trial panel trusted the copy saved in the browser, so a
   server-side change didn't show. Markers live in memory now; the trial is fetched once per page load.
6. **Re-map wording**: "1 papers", "Each paper will be read against each one" and the stage "Fetching full texts and
   reading" were wrong for a re-map, where nothing is read again.
7. **"Things just get worse at night" passed the entry bar**: the model offered "things" and "night" as constructs.
   Placeholders are rejected, and a trial needs two named constructs.

During the walkthrough, a click on the Check stage after the swap planned a v2 trial that was never run (fix 4);
it stays as a planned trial in the scratch database only.

## Known gaps

- The two-construct entry bar would also hold back a single-construct claim (e.g. a prevalence hypothesis).
- The Judge is not yet given the computed markers; it still names missing markers from its own reading.
- Rivals are kept by text: two rivals with the same wording are one rival, and editing a rival means parking a new one.
- The Writer and Designer use the latest finished trial; they do not check that it is for the current version.
- Re-mapping copies records but not the researcher's "I say" (it was about the old hypothesis); it has to be written again.
