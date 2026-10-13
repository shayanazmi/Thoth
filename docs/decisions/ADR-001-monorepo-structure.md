# ADR-001: Monorepo Reorganization & Railway Deployment

## Status
Accepted

## Context
Thoth originally developed with root-level scripts (`app.py`, `run_web.py`, `web_server.py`), scattered documentation, mixed Streamlit/HTML UI configs, and unsegregated test scripts. As the system expanded to include 10 epistemological reasoning frameworks and production evaluation benchmarks, this layout caused import fragility, deployment ambiguity, and operational overhead.

## Decision
Reorganize the repository into a clean monorepo topology:
- `docs/`: Centralized markdown documentation and architecture specifications.
- `web/`: Dedicated frontend service deployed independently on Railway.
- `backend/`: Layered API (`api/`), business services (`services/`), data repositories (`repositories/`), and core runtime (`core/`).
- `scripts/`: Categorized CLI utilities (`dev/`, `db/`, `ops/`, `eval/`).
- `evals/`: Unified benchmark harness consolidating sandbox tests and DeepEval configs.
- `archive/`: Safe quarantine for historical chat logs, reference repos, and deprecated launchers.

## Consequences
- **Positive:** Clear service boundary between frontend and backend on Railway. Standardized imports. Predictable CI/CD pipelines. Zero clutter in root.
- **Negative:** Requires updating import paths across the backend and migrating from root launchers to `Makefile` / `backend.main`.
