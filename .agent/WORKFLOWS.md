# Thoth — Workflows

Full targets: `make help`. The core ones:

| Task | Command |
|---|---|
| First-time setup | `make setup` |
| Backend (reload) | `make dev` → http://localhost:8000 |
| Frontend (static) | `make dev-web` → http://localhost:3000 |
| **Canonical test gate** | `make test-vision` (14 scenario tests, ~10s) |
| `make test` alias | runs `test-vision` |
| Discovery-only | `make test-legacy-all` |
| Lint / imports | `make lint` |
| 7-layer diagnostic | `make diagnostics` |
| Health probe | `make health` |
| SQLite → Supabase (dry) | `make migrate-dry-run` |
| SQLite → Supabase (apply) | `make migrate` |
| Seed demo data | `make seed` / `make seed-reset` |
| Flush Redis | `make cache-flush` |
| Clean caches | `make clean` |

## Venv gotcha for migration

The repo's committed `venv/` was built on macOS and its `python` symlink
points at a specific `/Library/Frameworks/Python.framework/...` path. On
a Linux host (including Claude Code sandboxes) or a different Mac layout,
it is a **dangling symlink**. Fix:

```bash
rm -rf venv
python3 -m venv venv
./venv/bin/pip install -r backend/requirements.txt pytest pytest-asyncio pytest-subtests httpx
```

Or create a disposable venv anywhere outside the project folder and
pass `VENV=/path/to/your-venv make dev`.

## Phase workflow (how work is done)

1. Read the vision section for the phase in `THOTH.docx`.
2. Write (or update) the scenario test in `backend/tests/scenarios/test_sN_*.py` first.
3. Implement.
4. Make the scenario green.
5. Walk through from the user's seat; record in `docs/archive/verify/phase_N.md`.
6. Stamp `docs/SYSTEM_STATE.md`.
7. Keep `/CLAUDE.md` §2 (current state) and §3 (repo map) accurate.
8. Hand control back to the owner for git staging / push.

Phase 0 verification notes under `docs/archive/verify/` are the honest
baseline; they are not updated after a phase lands (each phase gets its
own `phase_N.md` instead).
