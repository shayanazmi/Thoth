# 🔑 Environment Variables Specification

This document details every environment variable used in the Thoth monorepo.
**Security Rule:** Secrets must only be provided via `.env` or cloud secret managers. Never commit secrets to source control.

---

## 1. Master Environment Variables Table

| Variable | Scope | Type | Default | Required? | Sensitive? | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Backend / Web | String | `development` | No | No | Runtime mode (`development`, `staging`, `production`) |
| `PORT` | Backend | Integer | `8000` | No | No | HTTP listening port for FastAPI |
| `HOST` | Backend | String | `0.0.0.0` | No | No | Network binding host address |
| `API_BASE_URL` | Web | String | `http://127.0.0.1:8000` | No | No | Target backend URL for web frontend requests |
| `SUPABASE_URL` | Web & Backend | String | None | **Yes** | No | HTTPS endpoint of the Supabase project |
| `SUPABASE_ANON_KEY` | Web & Backend | String | None | **Yes** | No | Public anonymous client JWT for Supabase Auth |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend Only | String | None | **Yes** | **YES** | Admin key with full DB privileges (never send to client) |
| `SUPABASE_JWT_SECRET` | Backend Only | String | None | **Yes** | **YES** | Secret used by FastAPI to verify Supabase bearer tokens |
| `REDIS_URL` | Backend Only | String | `redis://localhost:6379/0` | No | **YES** | Redis connection URI for caching and rate limiting |
| `REDIS_CACHE_TTL` | Backend Only | Integer | `86400` | No | No | Default TTL for cached academic query results (seconds) |
| `NVIDIA_API_KEY` | Backend Only | String | None | **Yes** | **YES** | Primary inference provider key (NVIDIA NIM) |
| `NVIDIA_PRIMARY_MODEL` | Backend Only | String | `nvidia/nemotron-3.5-lightning-30b-a3b` | No | No | Primary model ID used for research synthesis |
| `GROQ_API_KEY` | Backend Only | String | None | Recommended | **YES** | High-speed fallback inference key |
| `GROQ_FALLBACK_MODEL` | Backend Only | String | `openai/gpt-oss-120b` | No | No | Fallback model used when primary reaches rate limits |
| `GROQ_VERIFIER_MODEL` | Backend Only | String | `openai/gpt-oss-20b` | No | No | Dedicated SLM model for Truth Guard claim verification |
| `OPENAI_API_KEY` | Backend Only | String | None | Optional | **YES** | Tertiary fallback inference provider key |
| `TAVILY_API_KEY` | Backend Only | String | None | **Yes** | **YES** | Web search and academic source discovery key |
| `SEMANTIC_SCHOLAR_API_KEY` | Backend Only | String | None | Optional | **YES** | Higher rate limit tier for Semantic Scholar API |
| `HF_TOKEN` | Backend Only | String | None | Optional | **YES** | Hugging Face token for downloading embedding weights |
| `DEEPEVAL_TELEMETRY_OPT_OUT` | Backend / Eval | String | `YES` | No | No | Disables DeepEval cloud telemetry reporting |
| `LOG_LEVEL` | Backend Only | String | `INFO` | No | No | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 2. Configuration Profiles

### Development (`.env.local` or `.env`)
```bash
ENVIRONMENT=development
PORT=8000
HOST=127.0.0.1
REDIS_URL=redis://127.0.0.1:6379/0
API_BASE_URL=http://127.0.0.1:8000
LOG_LEVEL=DEBUG
```

### Production (Railway Deployment)
On Railway, define service variables in the dashboard or via `railway.toml`:
- **Web Service:** Requires `API_BASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`.
- **Backend Service:** Requires all backend provider keys, `REDIS_URL` (injected automatically via Railway Redis Add-on), `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_JWT_SECRET`.
