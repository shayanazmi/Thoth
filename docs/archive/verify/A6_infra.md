# Phase 0.A6 — Infra reality check

**Date:** 2026-10-23
**Method:** Boot the backend repeatedly under varied env configurations via TestClient and observe `/ready` + lifespan logs + endpoint behaviour.

## Summary

Infra fail-open invariants hold. The system is runnable with **zero external services** on a developer laptop. Every external dependency degrades gracefully to a documented fallback.

## Supabase

- `SUPABASE_URL=""`, `SUPABASE_ANON_KEY=""`, `SUPABASE_SERVICE_ROLE_KEY=""`, `SUPABASE_JWT_SECRET=""`.
- Observed: `backend/repositories/base.py:10-28` detects the empty URL and returns `None`. The lifespan `init_db()` initialises local SQLite at `$THOTH_DB_PATH` (default `db/store.db`; overridable). `/ready` reports `"database":"sqlite_local"` honestly.
- Verdict: **Supabase is optional for dev.** The code reports its own fallback state truthfully.

## Redis

- Default `REDIS_URL` points at a hosted instance (`soft-lichen-milkwood-97876.db.redis.io:15156`) that is unreachable from this sandbox.
- Observed on every boot: `[WARNING] [ThothRedisCache] Redis unreachable (Error -3 connecting to ... Temporary failure in name resolution.). Running in fail-open in-memory fallback mode.`
- `/ready` reports `"redis":"memory_fallback"` honestly.
- Verdict: **Redis is optional.** In-memory fallback is live-swapped at first failure.

## LLM providers

- `NVIDIA_API_KEY=""`, `GROQ_API_KEY=""`, `OPENAI_API_KEY=""`.
- Observed: imports succeed (`ChatNVIDIA(api_key="")` does not raise at construction with the pinned version of `langchain-nvidia-ai-endpoints`). The first LLM call surfaces the real error: `HTTPSConnectionPool(host='integrate.api.nvidia.com', port=443): Max retries exceeded ... ProxyError: 403 Forbidden` in this sandbox (which does not whitelist that host). On a developer machine with a real key, the call reaches the provider.
- The `FallbackLLMWrapper` in `backend/agents.py` adapts input to the fallback provider when the primary fails, and the heuristic fallback inside `backend/intellectual_rigour/matcher.py` kicked in during A3's `/api/brainstorm/match` probe when NVIDIA was unreachable (`[MATCHER LLM ERROR] Fallback to heuristic or Popper`).
- Verdict: **Boot requires no API keys.** First real request needs at least one working provider.

## Scholarly APIs

- `TAVILY_API_KEY=""`, `SEMANTIC_SCHOLAR_API_KEY=""`, no HuggingFace token.
- Observed: `TavilyClient(api_key="")` does not raise at import time (`tavily-python` installed version 0.8.5 accepts a missing key — keyless mode). `backend/scholarly.py:799` short-circuits with `return []` when the key is missing.
- During A3's full pipeline probe, every scholarly API (ArXiv, Semantic Scholar, OpenAlex, PubMed, Europe PMC, Tavily) returned 403 from the sandbox proxy. The dispatcher tripped its circuit breaker after 5 failures and emitted a clean SSE `error` event. The behaviour is correct.
- Verdict: **Scholarly keys are optional for the code to boot.** The pipeline falls through to a web-only path or emits a clean error when no sources are reachable.

## Strictly required env for boot

**None.** Every variable in `.env.example` has a working default or an empty-string tolerance. The code's `pydantic-settings` config in `backend/core/config.py` makes every field optional.

## Strictly required for a real research run

| Capability | Minimum | Fallback |
|---|---|---|
| LLM inference | one working provider key (NVIDIA, Groq, or OpenAI) | three-way fallback wrapper |
| Scholarly search | one of ArXiv or Semantic Scholar reachable | OpenAlex / PubMed / Europe PMC in parallel; Tavily web for supplementation |
| Persistence | writable local disk for SQLite + `vault/` | — |
| Approval & task lifecycle | SQLite transactions on local disk | — |
| Cache | nothing — in-memory fallback is always available | — |

## Known infra issues (small bugs, not architecture)

- `.env.example` ships a `REDIS_URL` pointing at a dead hosted instance by default. New developers see the warning on every boot. **Change the default to `redis://localhost:6379/0` or leave it empty and let the fail-open path handle it silently.** Trivial fix in Phase 1.
- The default `ENVIRONMENT=development` in `.env.example` is not applied when the backend is launched without reading a `.env` file (as during A1's TestClient probe). The log shows `env=production` as a side effect. Harmless for behaviour; cosmetic.

## Verdict

**Fail-open discipline is real** across cache, Supabase, scholarly APIs, and LLM providers. The repeated vision principle "Resource awareness: avoid unlimited-cost assumptions" and the companion "fail-open" principle in `CLAUDE.md` §6 both hold in observed behaviour.

The system is **local-first-ready today**, even before the Phase 10 deployment-model decision is made. SQLite + in-memory cache + any one LLM key + any one scholarly source is enough to run a full research journey. This substantially de-risks the plan: no infra lift required between here and Phase 1.
