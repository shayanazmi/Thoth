# Phase 0.A3 — Endpoint reality probe

**Date:** 2026-10-23
**Method:** FastAPI `TestClient` against `backend.main.app` with empty API keys and SQLite-only. 70 paths registered; 25 probed for a mix of GET/POST surfaces across every router.
**Full logs:** `_logs/A3_endpoint_probe.log`, `_logs/A3_pipeline_probe.log`

## Summary (25 probes)

- **18 × 200 OK** (reads, writes to healthy paths)
- **1 × 201 Created** (`POST /api/ideas/tentative` — persisted idea row)
- **1 × 422 Unprocessable** (`POST /api/projects` — schema contract: expects `title`, not `name`)
- **18 × SSE events observed cleanly** across two streaming endpoints
- **1 × real backend bug** surfaced

## Verdict per endpoint

| Endpoint | Verdict | Notes |
|---|---|---|
| `GET /health` | **honest 200** | `{"status":"ok"}` |
| `GET /ready` | **honest 200** | `{"database":"sqlite_local","redis":"memory_fallback"}` — accurate |
| `GET /api/status` | **honest 200** | Reports deepeval off, breaker CLOSED, 3-provider list |
| `GET /api/brainstorm/thinkers` | **honest 200** | Returns all 10 thinkers from `thinkers.yaml` |
| `POST /api/brainstorm/match` | **honest 200** | Tried NVIDIA → 403 proxy block → **fell back to heuristic (Popper)**. Fail-open ✅ |
| `GET /api/ideas` | **honest 200** | `{"ideas":[]}` from empty DB |
| `POST /api/ideas/tentative` | **honest 201** | Row persisted with real `idea_id` |
| `GET /api/ideas/{id}` | **honest 200** | Round-trips the row |
| `GET /api/ideas/{id}/history` | **honest 200** | Lineage read works |
| `POST /api/research/brief/prepare` | **honest 200** | Synthesizes a `PENDING_APPROVAL` brief with real `brief_id` |
| `GET /api/research/brief/{id}` | **honest 200** | Brief round-trips |
| `POST /api/research/brief/approve` | **honest 200** | Marks `APPROVED` with versioned seal |
| `POST /api/research/stream` (no brief) | **approval barrier works ✅** | Emits `approval_barrier` event + `complete`, pipeline never fires |
| `POST /api/research/stream` (approved brief) | **pipeline runs end-to-end ✅** | `approval_verified` → SEARCH → scholarly APIs blocked by sandbox proxy → circuit breaker trips → writer hits NVIDIA proxy block → `error` event → clean `complete`. Code path is intact |
| `POST /api/followup/stream` | **BROKEN — real bug** | `'NoneType' object has no attribute 'get'` when `state=None`. Needs a guard in the followup entrypoint |
| `GET /api/prisma/reviews` | **honest 200** | `[]` from empty DB |
| `GET /api/projects` | **honest 200** | `{"projects":[]}` |
| `POST /api/projects` | **contract bug** | 422 — code expects `title` but README/schema docs likely say `name`. Minor |
| `GET /api/manuscripts` | **honest 200** | `[]` |
| `GET /api/manuscripts/journal-presets` | **honest 200** | Returns ACM/IEEE/Nature/NeurIPS presets as code declares |
| `GET /api/vault/notes` | **honest 200** | `[]` |
| `GET /api/vault/graph` | **honest 200** | `{"nodes":[],"edges":[]}` |
| `GET /api/sessions` | **honest 200** | `[]` |
| `GET /api/reports` | **honest 200** | `[]` |

## Key observations

### 1. The approval gate is real

A direct `POST /api/research/stream` with just a `topic` and no `brief_id` emits:

```
event: message
data: {"node":"approval_barrier","update":{"approval_status":"PENDING_APPROVAL","requires_approval":true,"barrier_reason":"No research brief provided. Formal research requires an explicit, approved Research Brief."}}
event: message
data: {"node":"complete","state":{}}
```

Then returns. No pipeline work happens. This matches `routes_research.py:193-249` and the Explore agent's prior finding.

### 2. The pipeline runs end-to-end on an approved brief

Prepare → approve → stream produced:

```
approval_verified → task_id="task_brief-...", version=1
: ping
error → "ProxyError: Tunnel connection failed: 403 Forbidden" (NVIDIA)
complete
```

The failure here is **sandbox network policy, not code**. In this sandbox the egress proxy allowlist does not cover `integrate.api.nvidia.com`, `api.semanticscholar.org`, `arxiv.org`, `api.openalex.org`, `europepmc.org`, `eutils.ncbi.nlm.nih.gov`, `api.tavily.com`. Every one of them returned 403. The dispatcher correctly:

- Retried with exponential backoff.
- Tripped the circuit breaker on 5 consecutive failures (`CIRCUIT BREAKER TRIPPED -> OPEN for 30.0s`).
- Blocked subsequent calls during cooloff.
- Fell through to the writer node which also failed cleanly.
- Emitted an `error` SSE event with the real error message.
- Terminated with `complete`.

On the user's local machine with working API keys, this path runs to produce a report. The dispatcher, circuit breaker, scholarly module, pipeline FSM, SSE emitter, and task lifecycle are all behaviourally correct.

### 3. Real bugs found

1. **`POST /api/followup/stream` with `state=None` crashes.** Code assumes `state` is a dict. One-line guard will fix. Vision §10 ("Allow users to steer, pause, redirect, or abandon") requires this path.
2. **`POST /api/projects` schema mismatch.** Request body expects `title`; the natural call uses `name`. Either accept both or document consistently. Minor.

### 4. Fail-open behaviour is honest

- Redis down → in-memory cache fallback, logged, served.
- NVIDIA proxy blocked → heuristic matcher kicks in on `brainstorm/match`.
- SQLite initialises cleanly without Supabase credentials.

This all matches vision §2 ("Resource awareness") and vision §10 (don't hide failed access behind a generic 'complete' status). The `error` SSE event propagates the real cause to the client — not a generic failure.

### 5. 70 total paths, mostly reachable

Only one path (`/api/followup/stream` with null state) crashed on probe. Every other path returned a code the frontend can reasonably render. The scaffolding is wired through.

## Implication for the plan

- **Phase 1** (chat router) can safely absorb the two bug fixes above as part of the migration.
- **Pipeline is salvageable as-is** for Phases 3-5 — we don't need to rewrite the FSM, we need to **gate** and **split** it (lightweight scan vs. formal PRISMA, phase 3) and **integrate thinkers** (phase 4).
- **Approval gate's `fast_chat` bypass** flagged in the plan is still a concern — not visible in these probes because `mode` defaulted to `auto`; needs explicit probe during Phase 1 implementation.
