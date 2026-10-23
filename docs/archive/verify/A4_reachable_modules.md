# Phase 0.A4 — Reachable modules map

**Date:** 2026-10-23
**Method:** Static import-graph BFS from `backend.main` + every `backend.api.routes_*` module, then patched with grep for lazy/dynamic imports (`importlib.import_module`, inline `from backend...` inside functions, `__init__.py` re-exports).
**Logs:** `_logs/A4_reach.log`

## Methodology caveats

Pure static grep missed three forms of real reachability:

1. **`__init__.py` re-exports.** `backend/intellectual_rigour/__init__.py` re-exports from `integrity_gate`, `attack_surface`, `synthesis`, `models`, `registry`. Modules reached through the package's public surface are live.
2. **Lazy imports inside functions.** `pipeline.py:959` does `from backend.intellectual_rigour.integrity_gate import audit_report_integrity` *inside* a node function. Patched by grep.
3. **Dynamic imports via `importlib.import_module`.** `registry.py:44` loads framework classes by string from `thinkers.yaml`. All ten `frameworks/*/framework.py` modules are reached this way.

With those added, the picture below is accurate.

## LIVE — reached from a user-facing path

| Module | How it is reached |
|---|---|
| `backend.main` | ASGI entrypoint |
| `backend.api.routes_*` (8 files) | registered in `main.py` |
| `backend.core.{config, logging, errors, cache, auth}` | main + routers |
| `backend.conversation.*` (6 modules) | brief / mandate / clarification / escalation / idea / resolver — all used by routes_research + routes_ideas |
| `backend.dispatcher` | pipeline + scholarly |
| `backend.scholarly` | pipeline + routes_prisma |
| `backend.ingestion` | tools + pipeline |
| `backend.tools` | pipeline + agents |
| `backend.pipeline` | orchestrator |
| `backend.orchestrator` | routes_research |
| `backend.telemetry` | main + status endpoint |
| `backend.memory.db` | every router that persists state |
| `backend.memory.{graph, index, session, vault}` | pipeline + routes_vault |
| `backend.reports.{patch, sections, validation}` | pipeline |
| `backend.workspace.{project, manuscript, exporter, traceability}` | routes_workspace |
| `backend.workspace.pdf_compiler` | **via** `workspace/exporter.py:110` + `journal_formatter.py:42` (lazy) |
| `backend.workspace.journal_formatter` | **via** `routes_workspace.py:351, 536, 560, 572, 586, 600` (lazy) |
| `backend.collaboration.{membership, sync}` | routes_workspace |
| `backend.intellectual_rigour.models` | re-exported via package `__init__.py` |
| `backend.intellectual_rigour.registry` | re-exported; dynamically loads frameworks |
| `backend.intellectual_rigour.matcher` | routes_brainstorm |
| `backend.intellectual_rigour.prisma` | pipeline + routes_prisma |
| `backend.intellectual_rigour.snowball` | routes_prisma |
| `backend.intellectual_rigour.counter_evidence` | routes_ideas |
| `backend.intellectual_rigour.integrity_gate` | **via** `pipeline.py:959` (lazy); exports also chained through `backend/__init__.py` |
| `backend.intellectual_rigour.attack_surface` | re-exported via package `__init__.py` |
| `backend.intellectual_rigour.synthesis` | re-exported via package `__init__.py` |
| `backend.intellectual_rigour.sparring` | **via** `routes_brainstorm.py:44` (lazy) |
| `backend.intellectual_rigour.clustering` | **via** `routes_prisma.py:346, 374, 409, 441` (lazy) |
| `backend.intellectual_rigour.frameworks.base` | parent class of every framework |
| `backend.intellectual_rigour.frameworks.{aristotle,bacon,descartes,hume,darwin,popper,kuhn,simon,turing,box}.framework` | **loaded via `importlib.import_module` from `thinkers.yaml`** |
| `backend.repositories.base` | referenced in `main.py` lifespan via `backend.core.cache` indirectly |

## DEAD — not reached from any router or lifespan (candidates to archive)

| Module | Evidence of deadness |
|---|---|
| `backend.models.schemas` | Zero importers under `backend/` (confirmed via `grep -nR "from backend.models"`). Routers define their own Pydantic classes inline. The declared contracts in `schemas.py` are unused. |
| `backend.repositories.report_repo` | Zero importers. |
| `backend.repositories.session_repo` | Zero importers. |
| `backend.repositories.vault_repo` | Zero importers. |
| `backend.core.rate_limit` | Zero importers. |
| `backend.eval.{datasets, judge_model, logical_integrity, metrics, runner}` | Not reached from main app; only used by `backend/evals/*` benchmark scripts (which are themselves not part of the request-serving graph). |

## Verdict and implication for the plan

- **The `backend/repositories/` layer is architecture that was replaced in place.** Every router skipped the repo abstraction and talks to `backend/memory/db.py` directly. The repos are not currently load-bearing. **Phase 7's project-scoped storage work should decide whether to resurrect them (clean abstraction) or formally archive them and keep db-direct access.**
- **`backend/models/schemas.py` duplicates what the routers inline.** Not harmful, but misleading — a reader opens the file expecting canonical contracts and finds dead ones. Candidate to archive OR to become the canonical source Phase 1's chat router imports from.
- **`backend/core/rate_limit.py` is not wired in.** No rate limiting is actually enforced in-process today, despite the architecture docs claiming "token bucket" everywhere. This is a security story to resolve in Phase 10 if hosted deployment is picked.
- **Everything else listed as "not reached" by naive static grep is actually live** via dynamic/lazy/re-export paths. The scaffolding is tighter than the file layout suggests.

## For the gap closure

Nothing in the LIVE list needs structural rework in Phase 1-9. The transformation per the plan is additive (new chat router, new idea detector, new lightweight-scan module, new originality module, new feasibility module, new budget module) plus narrow modifications to existing live modules. The DEAD list is quarantine, not rework.
