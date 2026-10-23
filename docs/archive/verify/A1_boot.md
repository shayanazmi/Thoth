# Phase 0.A1 — Boot the backend cleanly

**Date:** 2026-10-23
**Environment:** Linux sandbox (Python 3.10.12 /usr/bin/python3), disposable venv at `$HOME/thoth-verify-venv` on sandbox disk. The project's own `venv/` is a dangling symlink to a macOS Python 3.10 install and does not resolve on this device — the user's `venv/` was not touched.

## What was done

1. Created `$HOME/thoth-verify-venv` using `python3 -m venv`. Upgraded pip/wheel/setuptools.
2. Installed `backend/requirements.txt` in two rounds:
   - **Round 1 (core web + ingestion):** fastapi, uvicorn, sse-starlette, pydantic, pydantic-settings, pyjwt, python-dotenv, orjson, rich, pyyaml, tenacity, httpx, requests, aiohttp, beautifulsoup4, lxml, html5lib, pypdf, tiktoken, numpy, pandas.
   - **Round 2 (LLM + storage):** langchain, langchain-core, langchain-community, langchain-openai, langchain-nvidia-ai-endpoints, langchain-groq, openai, groq, tavily-python, supabase, redis, asyncpg.
   - **Deliberately deferred:** torch, sentence-transformers (large; needed only for embeddings — defer until A2 shows a reaching test or A3 shows an endpoint that imports them).
3. Set every API key env var to `""` to confirm fail-open behaviour. SQLite path pinned to `$HOME/thoth-verify.db` so the user's `db/store.db` is not written.
4. Imported `backend.main` directly — succeeded, `app.title = "Thoth Research Gateway"`.
5. Could not run uvicorn as a detached long-lived process in this sandbox (shell killed with exit 143 on `nohup`/`setsid` background). **Switched to `fastapi.testclient.TestClient`** against the same `app` object — same code paths through the lifespan context manager, no network layer.

## Observations

- **Lifespan starts cleanly.** Log line: `[INFO] [ThothApp] Initializing Thoth Research Intelligence Service (env=production)...`.
- **Redis fails open as the code claims.** Log: `[WARNING] [ThothRedisCache] Redis unreachable ... Running in fail-open in-memory fallback mode.` Confirms vision §2 "resource awareness / fail-open" invariant for the cache layer.
- **`/health` returns `{"status":"ok","app":"Thoth Research Intelligence"}`** (200).
- **`/ready` returns `{"status":"ready","database":"sqlite_local","redis":"memory_fallback","timestamp":"..."}`** (200). The `database` field honestly reports `sqlite_local`, not a false `postgres` claim.
- **Total registered routes: 70.** Many more than the nine routers suggested — manuscript, exports, project, snowball, cluster, journal-submission paths all show up. Full list on file.
- **Lifespan shutdown emits** `[INFO] [ThothApp] Shutting down Thoth Research Intelligence Service...` — clean teardown.
- **No deepeval** installed yet; the `backend/telemetry.py` module's optional-import branch kicked in without error.

## Verdict

**Honest claim:** The backend starts, degrades gracefully on missing infra, and reports its state truthfully through `/ready`. The permissive-boot assertion in `CLAUDE.md` §0 holds.

## Known caveats for later phases

- Boot was tested against the TestClient, not a live uvicorn. A later phase that needs a real-server environment will need a different sandbox / local run.
- Embedding-adjacent paths (`backend/memory/index.py` likely uses sentence-transformers) have **not been exercised yet**. A2 and A3 will surface which routes trip over the missing torch/sentence-transformers.
- `env=production` was reported — because `ENVIRONMENT=development` from `.env.example` was not applied (no `.env` loaded in the probe script). Harmless for the boot check; worth tracking.
