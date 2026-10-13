# 🛠️ Thoth Local Setup & Development Guide

This guide walks you through setting up Thoth locally, configuring Supabase, Redis, and running the development environment.

---

## 1. Prerequisites

Ensure you have the following installed on your machine:
- **Python 3.10+** (Python 3.10 or 3.11 recommended)
- **Node.js 18+** (Optional, for tooling and Supabase CLI)
- **Make** (Pre-installed on macOS / Linux)
- **Redis** (`brew install redis` on macOS or Docker)
- **Supabase CLI** (`brew install supabase/tap/supabase` or a free cloud account at [supabase.com](https://supabase.com))

---

## 2. Quickstart (Under 5 Minutes)

```bash
# 1. Clone repository (or navigate to root)
cd thoth

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your provider keys (NVIDIA, Groq, Tavily, Supabase, Redis)

# 5. Launch local server
make dev
```

---

## 3. Environment Configuration

Copy the example environment file and populate the required API credentials:

```bash
cp .env.example .env
```

### Essential Keys for Local Testing:
1. **Primary LLM:** `NVIDIA_API_KEY` (Get a free key from [build.nvidia.com](https://build.nvidia.com))
2. **Fallback LLM:** `GROQ_API_KEY` (Free high-speed inference from [console.groq.com](https://console.groq.com))
3. **Web Search:** `TAVILY_API_KEY` (From [tavily.com](https://tavily.com))
4. **Supabase:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
5. **Redis:** `REDIS_URL=redis://localhost:6379/0`

---

## 4. Setting up Redis

### Option A: Local Redis (macOS Homebrew)
```bash
brew install redis
brew services start redis
```

### Option B: Docker Container
```bash
docker run -d --name thoth-redis -p 6379:6379 redis:7-alpine
```

Verify Redis is responsive:
```bash
redis-cli ping
# Expected output: PONG
```

---

## 5. Setting up Supabase

### Cloud Instance (Recommended for Quick Dev)
1. Create a project at [supabase.com](https://supabase.com).
2. Go to **Project Settings → API** and copy:
   - Project URL (`SUPABASE_URL`)
   - Anon Public Key (`SUPABASE_ANON_KEY`)
   - Service Role Secret (`SUPABASE_SERVICE_ROLE_KEY`)
3. Open the **SQL Editor** in Supabase and execute the migrations in order:
   - `backend/supabase/migrations/001_initial_schema.sql`
   - `backend/supabase/migrations/002_enable_rls.sql`
   - `backend/supabase/migrations/003_pgvector_setup.sql`

### Local Instance (Using Supabase CLI)
```bash
supabase init
supabase start
supabase db reset
```

---

## 6. Running Tests

Execute the comprehensive test suite to verify pipeline integrity:

```bash
# Run unit & schema tests
pytest tests/test_schemas.py tests/test_pure_functions.py -v

# Run the complete test suite
pytest tests/ -v

# Run 7-layer system diagnostic
python scripts/dev/diagnostic_test.py
```

---

## 7. Starting the Development Servers

Using the **Makefile**:
```bash
# Run backend development server with auto-reload
make dev-backend

# Serve the web client
make dev-web

# Or run both concurrently
make dev
```
Navigate your browser to `http://127.0.0.1:8000` to launch the **Thoth Research Intelligence Studio**.
