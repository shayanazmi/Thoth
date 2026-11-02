# API reference

Thoth serves a JSON API at the same origin as the UI. With the server running, interactive documentation is
at **`/docs`** (Swagger UI) and **`/redoc`**, and the schema at `/openapi.json`.

- Long runs stream **Server-Sent Events**: `data: {"event": <name>, "payload": {...}}`.
- Every costly run requires an explicit `{"approve": true}` in its body: trial runs and sub-claim edits,
  systematic review runs, proposal writing and export. Without it, nothing runs.
- Project-scoped calls take `project_id` (in the body, or as a query parameter on `GET`).

## Chat

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/chat/stream` | SSE. An ordinary turn goes to the conductor (`direct_answer`, `quick_look_result`, `notebook_proposal`, `thinker_suggestion`, `step_offer`, `complete`); `{"idea_promotion": {title, hypothesis, rationale}}` keeps an idea (`idea_promoted`) |
| `POST` | `/api/chat/proposals/{proposal_id}` | Accept, edit or dismiss a proposal, offer or suggestion: `{"action": "accept"/"edit"/"dismiss", "value"?}` |

## Projects

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/projects` | Create a thread: `{"title"}` |
| `GET` | `/api/projects` | Every thread and project, each with its `kind` |
| `DELETE` | `/api/projects/{id}?confirm=true` | Delete the project and everything it holds; without `confirm`, `409` with the counts |
| `GET` | `/api/projects/{id}/state` | Thread or project, question, hypothesis versions, rivals, the conversation |
| `PUT` | `/api/projects/{id}/notebook` | Your own question / hypothesis / rival (a new version), with an optional rationale |
| `GET` | `/api/projects/{id}/history?kind=` | Every version of question, hypothesis, rival or design, with why it changed |
| `GET` | `/api/projects/{id}/footprint` | What the project holds, with counts |
| `GET` | `/api/projects/{id}/markers` | Strength markers of the current hypothesis |
| `POST` | `/api/projects/{id}/rivals/retire` | `{"text"}`: retire a parked rival |
| `POST` | `/api/projects/{id}/rivals/swap` | `{"text"}`: the rival becomes the main hypothesis; the old one is parked |
| `GET` `PUT` | `/api/projects/{id}/mode` | Autopilot / Co-pilot, with per-step overrides (`subclaims`, `screening`, `proposal`) |

## Thinkers

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/thinkers` | The roster |
| `GET` | `/api/thinkers/{id}/profile` | The dossier, as shown when you tap a bust |
| `POST` | `/api/thinkers/{id}/reply` | A thinker joins the main chat, or replies in a one-to-one room |
| `POST` | `/api/thinkers/council` | Every thinker's first reaction, each independently |
| `POST` | `/api/thinkers/debate` | SSE: sequential rounds, then Thoth's distillation |
| `POST` | `/api/thinkers/review` | Independent reviews of the hypothesis or another artefact |

## Trial

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/trial/plan` | Sub-claims and the effort estimate; nothing heavy runs |
| `POST` | `/api/trial/{id}/run` | SSE; `{"approve": true}`: papers → matrix rows → the ruling (runs once) |
| `GET` | `/api/trial/{id}` | Full state: papers, records, matrix rows, ruling |
| `GET` | `/api/trial/latest?project_id=` | The project's most recent trial |
| `POST` | `/api/trial/{id}/stop` | Keep finished rows, mark the rest "not run" |
| `POST` | `/api/trial/{id}/subclaims` | SSE; `{"approve": true}`: edited sub-claims, every row redone, re-judged |
| `POST` | `/api/trial/{id}/papers` | Add a paper by DOI (read and analysed immediately) |
| `POST` | `/api/trial/papers/{paper_id}/pdf` | Upload a PDF (base64) to complete an abstract-only paper |
| `PATCH` | `/api/trial/papers/{paper_id}` | Your own "I say" note on a row |
| `POST` | `/api/trial/{id}/rejudge` | Weigh the witnesses again after edits or additions |
| `POST` | `/api/trial/{id}/remap` | A rival was swapped in: plan a trial of it on the same library (the run needs approval) |

## Systematic review

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/review/protocol` | Draft a protocol (nothing runs) |
| `POST` | `/api/review/estimate` | The estimate for a budget (nothing runs) |
| `POST` | `/api/review/{id}/run` | SSE; `{"approve": true, "mode": "auto"/"copilot", "protocol"?}` |
| `POST` | `/api/review/{id}/stop` | Stop a running review; everything recorded is kept |
| `POST` | `/api/review/{id}/continue` | SSE; resume after screening, after Stop, after a raised budget, or after an error |
| `POST` | `/api/review/{id}/budget` | More room (`full_text`, `citation_records`, `citation_rounds`), then Continue |
| `POST` | `/api/review/{id}/decisions/{record_id}` | Confirm or override a screening decision `{stage, decision, reason}` |
| `POST` | `/api/review/{id}/accept-all` | Confirm the Screener's remaining decisions for a stage |
| `GET` | `/api/review/{id}` | Protocol, budget, PRISMA counts, stopping rules, limitations, queues |
| `GET` | `/api/review/{id}/searches` | The search record: every request, query, page, date, totals and errors |
| `GET` | `/api/review/{id}/records?offset&limit&filter` | Records, paged (`all`, `included`, `excluded_ta`, `excluded_ft`, `not_screened`, `duplicates`, `citation`) |
| `GET` | `/api/review/latest?project_id=` | The project's latest review |

## Study design

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/design?project_id=` | Resources, latest candidates, chosen design (versioned) |
| `POST` | `/api/design/resources` | Save your resources for this project |
| `POST` | `/api/design/propose` | Two or three candidate designs from the hypothesis, the trial and your resources |
| `POST` | `/api/design/choose` | Choose (and optionally edit) one; it becomes the Design section |
| `POST` | `/api/design/revise` | Answer a design-level fatal finding from the peer Reviewer with a revised design |

## Proposal

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/proposal?project_id=` | Outline, sections, status, references |
| `POST` | `/api/proposal/outline` | A tailored outline and estimate (nothing heavy runs) |
| `PUT` | `/api/proposal/outline` | Your reordered or edited outline |
| `POST` | `/api/proposal/write` | SSE; `{"approve": true}`: sections → Verifier → Reviewer |
| `PUT` | `/api/proposal/sections/{key}` | Your own edit of a section (kept; needs re-verifying) |
| `POST` | `/api/proposal/sections/{key}/regenerate` | Rewrite one section (`409` if it has your edits, unless `overwrite`) |
| `POST` | `/api/proposal/sections/{key}/verify` | Run the Verifier on a section as it stands |
| `POST` | `/api/proposal/review` | Run the peer Reviewer again (bounded revision loops) |
| `POST` | `/api/proposal/review/stream` | The same, as SSE |
| `POST` | `/api/proposal/thinkers` | Independent thinker reviews of the whole proposal |
| `POST` | `/api/proposal/concerns/{concern_id}/answer` | Your reply to a thinker's concern |
| `POST` | `/api/proposal/export` | Markdown download; `{"approve": true}`; a provisional draft is watermarked |

## Health

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Storage in use (SQLite path) |
| `GET` | `/api/status` | Models and circuit-breaker states |

---

<sub>Thoth · Developed by Shayan Azmi</sub>
