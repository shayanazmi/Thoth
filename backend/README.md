# Backend

Python 3.10+, FastAPI, LangChain Core for model calls, SQLite for storage.
See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for how the pieces fit together.

```bash
make setup && make dev     # from the repository root
make test                  # scenario tests, offline
```

| Path | What it holds |
|---|---|
| `main.py` | The FastAPI app; serves `frontend/` at `/` |
| `api/` | One router per feature |
| `conversation/` | The conductor, explicit idea promotion, project state |
| `thinkers/` | The roster, persona prompts, council / debate / review / rooms, and the dossiers |
| `research/` | Literature, the trial, the systematic review, study design and the proposal |
| `memory/` | SQLite access and the conversation store |
| `intellectual_rigour/` | Deterministic integrity checks (numbers, bibliography) |
| `agents.py` | Per-role models with fallbacks (`get_role_llm`) |
| `tests/scenarios/` | The test suite |

Rules the code keeps:
- New model calls go through `get_role_llm` / `FallbackLLMWrapper`; never hard-code a provider.
- External services fail open: a literature source that is down is recorded, and the work continues.
- Provider errors pass through `sanitize_log_message` before they are logged or shown.
- The approve flags are the only way into expensive work.

---

<sub>Thoth · Developed by Shayan Azmi</sub>
