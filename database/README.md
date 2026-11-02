# Database

Thoth stores everything in one **SQLite** file. There is nothing to install or run.

| File | What it is |
|---|---|
| [`schema.sql`](schema.sql) | The schema: the single source of truth. `backend/memory/db.py` applies it (idempotently) at startup. |
| `thoth.db` | Your data, created on first start. Git-ignored. Set `THOTH_DB_PATH` to keep it elsewhere. |

## Tables

| Table | Holds |
|---|---|
| `research_projects` | Threads and projects (a thread becomes a project when a hypothesis is accepted) |
| `research_ideas` | Ideas you explicitly kept from the conversation |
| `conversation_turns` | Every message: the main conversation and each one-to-one thinker room |
| `thread_summaries` | The rolling summary of older turns |
| `conductor_proposals` | What Thoth proposed and what you decided |
| `notebook_sections` | The research file: every version of each section, with why it changed |
| `thinker_memory` | Where each thinker stands on the project |
| `trials`, `trial_papers` | Trials (plan, matrix, ruling) and the papers read in them |
| `sys_reviews`, `sys_review_records`, `sys_review_searches` | Systematic reviews, their records and screening decisions, and the search record |

## Backup, reset and inspect

```bash
cp database/thoth.db database/thoth-backup.db    # back up (stop the server first)
rm database/thoth.db*                            # start fresh (deletes all projects)
sqlite3 database/thoth.db ".tables"              # inspect
```

Deleting a project from the UI removes all of its rows, after a confirmation that lists the counts.

---

<sub>Thoth · Developed by Shayan Azmi</sub>
