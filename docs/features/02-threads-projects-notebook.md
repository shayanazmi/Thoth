# 02 · Threads, projects and the living research file

> Vision: §3, §9 (project-scoped storage), §10 (resource awareness).

## What the owner wants

- Every chat starts as a **thread**. It becomes a **Project** when a hypothesis is accepted.
- What a project owns is a **living research file** with separate sections, never one mashed report.
- Thoth proposes changes to the file; the user accepts them with one tap. Versions are kept.
- One **Autopilot / Co-pilot** switch per project, with per-step override. Autopilot still asks once,
  up front and with an estimate, before expensive runs.
- Deleting a project deletes everything, after a confirmation.
- Big runs show what's happening in the background (see "Live work" below).

## Design

### Thread → Project

```
Thread (light notebook)                      Project (full research file)
  question                                     question
  quick-look papers          accept            hypothesis (+ parked rivals)
  thinker notes        ── hypothesis ──▶       library (full paper records)
  open proposals                               trial: sub-claims, matrix, verdict
                                               design
                                               proposal draft
                                               activity log
```

Promotion moves the thread's turns, notes and papers into the project. Nothing is lost.
Threads appear under "Recent" in the sidebar; projects under "Projects".

### The research file sections

| Section | Filled by | Versioned | Editable by user |
|---|---|---|---|
| Question | Conductor proposal | yes | yes |
| Hypothesis (main + rivals) | Conductor / thinkers proposal | yes | yes |
| Sub-claims | Analyst (auto) or user (co-pilot) | yes | yes |
| Library | Librarian + Reader; user uploads, DOI/arXiv/URL | n/a | add/remove |
| Matrix | Analyst | per run | edit "I say" cells |
| Verdict + originality | Judge | per run | comment |
| Design | Designer | yes | yes |
| Proposal | Writer → Verifier → Reviewer | per section | yes |
| Thinker notes | Thinkers | append-only | no |
| Activity | System | append-only | no |

Each section has its own status (`empty | draft | provisional | reviewed`). The project status is
the weakest of its required sections. That satisfies vision §11: nothing is called complete while
critical review is unresolved.

### Autopilot / Co-pilot

`project.mode ∈ {autopilot, copilot}`; `step_overrides: {screening: copilot, subclaims: autopilot, …}`.

| Step | Co-pilot | Autopilot |
|---|---|---|
| Sub-claims | Thoth proposes, user approves | Thoth sets them, shows them, user can edit later |
| PRISMA screening | Screener proposes, user audits each decision | Screener decides; disagreements are logged for later audit |
| "I say" cells | Drafted, marked "Thoth's draft" until accepted | Drafted, still marked as Thoth's |
| Proposal sections | One at a time with approval | Full outline → sections, then review |

Autopilot never skips the up-front approval for a heavy run, and never fabricates past a blocked step:
a blocked step writes `BLOCKED: <reason>` and the run continues in degraded mode (the Feynman rule).

### Live work

Every heavy run streams `activity` events that the UI renders as things happening, not as a spinner:
- the library: papers drop in as they're found, each showing an access badge
  (`full text | abstract only | inaccessible`);
- the matrix: rows appear, cells fill as the Reader and Analyst finish them, and any row can be opened mid-run;
- a header strip: elapsed time against the estimate, papers read out of papers found, model calls used;
- **Stop** at any time keeps what's done and marks the rest `not run`.

### Retention

Deleting a project removes its turns, notes, papers, PDFs, matrix, drafts and embeddings, after one
confirmation that lists counts ("38 papers, 4 PDFs, 212 messages"). There is no global library.

## Data (new tables; SQLite + Postgres migration together)

`threads`, `projects(mode, step_overrides_json, status)`, `notebook_sections(project_id, kind, version,
content_json, status, author)`, `papers(project_id, …)` (see 05), `matrix_rows` (see 06),
`activity(project_id, run_id, kind, payload_json, ts)`.

## Walkthrough (acceptance)

1. Chat in a new thread; accept a question proposal. The thread shows a light notebook.
2. Accept a hypothesis → it becomes a project with all its earlier turns and quick-look papers.
3. Switch to Autopilot and start a scan: one approval with an estimate, then papers and rows fill in live.
4. Press Stop mid-run: completed rows stay, the rest show `not run`, and the status is provisional.
5. Delete the project: the confirmation shows counts; afterwards nothing remains in the DB for that id.

Scenario test: `test_s11_thread_promotion_and_retention.py`.

## Build note (27 Oct 2026, first slice)

Built: thread vs project (derived from the first hypothesis version), project state on the server (question,
hypothesis versions, rivals, conversation) with `hydrate()` in the browser, the researcher's own edits as notebook
versions, and delete with a count confirmation across every table the project owns. Code:
`backend/conversation/projects.py`, `backend/api/routes_projects.py`, the delete handler in `routes_workspace.py`.
Walkthrough: `docs/archive/verify/projects_on_server.md`. Scenario: `test_s11_thread_promotion_and_retention.py`.

Departures: no `threads`/`projects` tables yet, because every store already keys on the project id and "project"
is derived from the notebook; the `projects(mode, step_overrides)` and `activity` tables come with Autopilot /
Co-pilot and Stop. Promotion keeps the same id, so nothing is moved. Not yet: per-section status, Autopilot,
the live-work header and Stop, chat cards on the server, and vault notes in the delete.

## Build note (27 Oct 2026, second slice: modes, live work, Stop)

Built: mode per project (`copilot` default / `autopilot`) with overrides for `subclaims`, `screening`, `proposal`
(stored as a versioned notebook entry, `/api/projects/{id}/mode`); a per-run model-call counter
(`research/llm.py`); the trial's live-work header (elapsed vs estimate, papers analysed of found, model calls,
fallback calls) and Stop (`POST /api/trial/{id}/stop`: finished rows kept, the rest `not_run`, no verdict unless
asked; a later verdict says what wasn't run). Proposal writing steps one section per approval in Co-pilot.
Walkthrough: `docs/archive/verify/modes_live_work_stop.md`. Scenario: `test_s14_modes_live_work_and_stop.py`.

Departures: no `projects` or `activity` tables (the mode is a notebook entry; live work is streamed, not stored).
Not yet: Stop for proposal writing, systematic review and re-analysis; the screening override in the review panel.

