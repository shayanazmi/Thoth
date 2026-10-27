# Projects on the server: user-seat walkthrough (27 Oct 2026)

Feature: `docs/features/02-threads-projects-notebook.md`, first slice (checklist item 1). In-app browser on :8002
against a scratch copy of the database, so deleting could not touch real projects.

## What was built

- `backend/conversation/projects.py`:
  - **Thread or project** is read from the notebook: a chat becomes a project when its first hypothesis version
    exists (the researcher wrote one, or accepted Thoth's proposal). Every store already keys on the same id, so
    promotion moves nothing.
  - **State** for any browser: title, kind, question, every hypothesis version with who wrote it, rivals, and
    the main conversation (thinker one-to-one rooms excluded).
  - **The researcher's own edits** of the question, hypothesis and rivals become new notebook versions authored
    by them.
  - **Footprint and delete** across every table the project owns: turns (incl. thinker rooms `pid::room::…`),
    summaries, proposals, notebook, thinker memory, trials and their papers, systematic reviews and their records,
    the project row. One transaction. Thread prefixes are matched exactly (a `LIKE` would treat `_` as a wildcard).
- `backend/api/routes_projects.py`: `GET /api/projects/{id}/state`, `PUT /api/projects/{id}/notebook`,
  `GET /api/projects/{id}/footprint`. `DELETE /api/projects/{id}` (in `routes_workspace.py`) now deletes everything,
  and only with `?confirm=true`; without it, 409 with the counts. `GET /api/projects` carries `kind`.
- `backend/memory/conversation_store.section_history`: all versions of a section.
- Frontend: `store.js` sends the researcher's hypothesis edits to the server (accepted proposals are already
  there), `hydrate()` rebuilds a project from the server when it is opened (server history wins; a project from
  before this change sends its local hypothesis and question up once), `forgetProject()` clears the local copy.
  `main.js`: the sidebar splits **Projects** from **Threads**; each row has a delete control that shows the
  footprint in an in-page dialog and needs "delete" typed.
- No new table: kind is derived, and the existing tables already key on the project id. The spec's `threads`,
  `projects(mode, …)` and `activity` tables wait for the Autopilot switch and Stop (checklist item 3).
- `backend/tests/scenarios/test_s11_thread_promotion_and_retention.py`: 3 tests, written before the code.
  Gate: 60 passed, 1 skipped.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Opened the app | Sidebar: **Projects** (2, those with a hypothesis, incl. the nurses project) and **Threads** (49 chats, many from earlier test runs) | pass (after fix 2) |
| 2 | Removed the nurses project's localStorage copy (a second browser) and opened it | All 35 messages back in order, hypothesis v1 on the card, read from the server | pass |
| 3 | In a one-message thread, `/hypothesis Nurses on quieter night wards sleep longer…` | Server holds the version, authored by "you"; the chat moved from Threads to Projects | pass |
| 4 | Delete control on it | In-page dialog: "This removes 2 messages, 1 notebook entry from this project, for good." and "Type 'delete' to confirm" | pass (after fix 3) |
| 5 | Typed "yes" | Toast "Not deleted"; footprint unchanged | pass |
| 6 | Typed "delete", confirmed | Toast "Deleted …"; gone from the sidebar, the project list and localStorage; footprint "nothing stored yet" | pass |
| 7 | Footprint of the nurses project (not deleted) | "31 papers, 5 trials, 2 systematic reviews, 100 screening records, 35 messages, 27 notebook entries, 5 thinker memories" | pass |

## Problems found and fixed

1. **Projects were written to a stale database.** `backend/workspace/project.py` bound `DEFAULT_DB_PATH` into
   its default arguments at import time, so project rows could go to a different database than everything else
   (in tests, an earlier test's database; delete answered 404). The path is now resolved at call time.
2. The sidebar grouping called a helper that only existed inside the sidebar renderer (`stageOf`): the sidebar
   didn't render at all. Found in the browser; fixed.
3. The delete dialog's placeholder "delete" looked already typed, and its text repeated what the counts said.
4. The server's thinker messages used a different shape from the chat's (`thinker: {id, name}`); aligned.

During the walkthrough my own typing landed in the chat box of the open project (the collapsed sidebar hid the
new-project field) and was sent as a message. It was the scratch database; the conductor answered sensibly
("That looks like two questions merged").

## Known gaps

- The chat cards (trial plan, reviews, proposals) are still only in the browser; a second browser gets the text of
  the conversation, not the cards. The trial, review, design and proposal panels load from the server anyway.
- Rivals are the distinct values of the `rival_hypothesis` versions; removing one, and swapping a rival in, are
  checklist item 2 (feature 04).
- Projects are still created on the first message (as threads, which is now honest about what they are).
- Vault notes are still global; legacy `workspace/` manuscripts keyed by project id are not part of the footprint.
- The 49 leftover threads from earlier runs can now be deleted one by one; there is no bulk clean-up.
