# Autopilot / Co-pilot, live work and Stop: user-seat walkthrough (27 Oct 2026)

Feature: `docs/features/02-threads-projects-notebook.md` § Autopilot / Co-pilot, § Live work (checklist item 3).
Live NVIDIA NIM (slow: the free tier was rate-limiting), in-app browser on :8002 against a scratch copy of the
database, the night-shift nurses project. The real database was not changed.

## What was built

- **Mode per project** (`backend/conversation/projects.py`): `copilot` (default) or `autopilot`, with per-step
  overrides for `subclaims`, `screening` and `proposal`, stored as a versioned notebook entry (`mode`).
  `GET/PUT /api/projects/{id}/mode`; the project state carries it. Neither mode skips the up-front approval of a
  heavy run.
  - Sub-claims: Co-pilot shows them as editable boxes on the trial plan; Autopilot shows them read-only ("you can
    change them after the run with Edit sub-claims"). The run still needs **Approve and run**.
  - Proposal: Co-pilot writes one section per approval (`awaiting_next`), and the peer Reviewer runs once the last
    one is written; Autopilot writes every missing section, then the review.
  - Screening: the override is stored and shown, but the systematic-review panel (`review.js`, owned by another
    session) still defaults to Human-in-the-loop; it is not wired to the project mode yet.
- **Model calls used** (`backend/research/llm.py`): each run counts the model calls it makes and how many the
  fallback answered (a context variable shared with the run's tasks).
- **Live work** (`trial.py`): the run streams `usage` events (papers found and analysed, model calls, fallback
  calls). The trial panel shows a header with elapsed time against the estimate, papers analysed out of found,
  model calls and **Stop**; the chat's progress card has Stop too.
- **Stop**: `POST /api/trial/{id}/stop` (409 unless running). The run cancels its workers, keeps finished rows,
  marks the rest `not_run`, sets the trial `stopped` and weighs no verdict. "Weigh what's done" runs the Judge on
  the finished rows; the verdict says how many were not run and is marked `partial`. A stopped trial is never used
  as "the latest finished trial" by the design or proposal steps. Closing the page mid-run counts as Stop, and at
  startup any running or stopped trial's unfinished papers become `not_run`.
- Frontend: `frontend/js/mode.js` (the mode button in the top bar and its in-page dialog), the live-work header,
  Stop, the stopped banner and "Weigh what's done" in `trial.js`, Co-pilot stepping in `proposal.js`.
- `backend/tests/scenarios/test_s14_modes_live_work_and_stop.py`: 5 tests, written before the code. S18's writing
  helper now sets Autopilot explicitly (its gates are about the whole pipeline). Gate: 72 passed, 1 skipped.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Opened the nurses project | Top bar: "CO-PILOT" | pass (after fix 1) |
| 2 | Clicked it; chose Autopilot; under "Per step" kept Proposal sections on Co-pilot; Save | Dialog explains both modes and that heavy runs always ask first. Button: "AUTOPILOT · MIXED"; toast "Mode: Autopilot, with per-step changes."; server: effective subclaims/screening autopilot, proposal copilot | pass |
| 3 | Started a trial | Plan card: sub-claims read-only, "Autopilot set these sub-claims… the run itself still waits for your approval", weaknesses listed, **Approve and run** | pass (after fix 4) |
| 4 | Approve and run; opened the trial tab | Header "41s of ~5-10 minutes · 0/15 papers analysed · 1 model call · Stop", later "2m 20s · 3/15 · 13 model calls" | pass (after fixes 2, 5) |
| 5 | Stop at 3/15 | Chat: "Stopped. 3 of 15 papers were analysed and are kept; 12 were not run. No verdict was weighed." Panel: "Stopped before finishing… Weigh what's done"; 12 rows "not run". Server: status `stopped`, 3 done / 12 not_run | pass |
| 6 | Weigh what's done | Verdict "insufficient evidence" with "12 papers were not run (the trial was stopped); this verdict weighs only the 3 that were."; marked partial; trial stays `stopped` | pass |
| 7 | Restarted the server during a run | The interrupted trial came back `stopped`, 5 done and 10 `not_run` | pass (after fix 3) |
| 8 | Draft tab → Edit the outline | "Approve and write the first section" and "Co-pilot: one section at a time…" (the proposal override) | pass |

## Problems found and fixed

1. **The proposal module didn't load at all** (a bad splice of my own edit left a dangling block). `node --check`
   had passed because it parsed the file as a script; files are now checked as ES modules, as the browser loads them.
2. **A race replaced the live run.** The trial panel's server load, started just before the run, finished during
   the run and overwrote its state with a "planned" snapshot: no header, no Stop. A load that finishes during a
   live run is now discarded.
3. **Unfinished papers stayed "reading"/"analysing"** after the page closed or the server restarted mid-run. Both
   now mark them `not_run`; startup clean-up covers stopped trials too (an older build had already marked one
   `stopped`).
4. Autopilot's plan card still said "Edit them if they misstate what you mean"; removed in Autopilot.
5. "1 model calls"; and the step selects in the mode dialog had no accessible names (screen readers heard
   "Same as the project" three times). Both fixed.

Also seen: the guided demo's replay layer answers requests while the demo project is open (a trial plan there got
a 404 from the recording). That is the demo working as designed; leaving the demo project and reloading restores
the live server.

## Known gaps

- The screening override isn't applied: the review panel still opens on Human-in-the-loop.
- Stop exists for the trial only; the proposal's writing and review loops, the systematic review and re-analysis
  have no Stop yet (closing the page stops a trial, not those).
- Elapsed time is the browser's; after a reload mid-run the header is gone (the trial reloads as stopped or done).
- Model calls are counted when they return; a call that fails after retries is not counted.
- No `activity` table: the live work is streamed, not stored, so it can't be replayed later.
- In Co-pilot, "Approve and write the first section" shows even when every section exists (approving then only
  runs the review).
