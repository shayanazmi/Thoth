# ⚙️ Operational Workflows for Thoth

## 1. Development Commands
- Start both services: `make dev`
- Start backend only: `make dev-backend`
- Start web client only: `make dev-web`
- Run test suite: `make test`
- Run 7-layer diagnostic: `python scripts/dev/diagnostic_test.py`

## 2. Database & Migration Workflows
- Apply Supabase migrations:
  ```bash
  cat backend/supabase/migrations/*.sql | psql $SUPABASE_DB_URL
  ```
- Migrate local SQLite `store.db` to Supabase:
  ```bash
  python scripts/db/migrate_sqlite_to_supabase.py --db store.db
  ```
- Seed initial fixtures:
  ```bash
  python scripts/db/seed.py
  ```

## 3. Operational & Cache Workflows
- Flush all Redis cache keys:
  ```bash
  python scripts/ops/cache_flush.py --all --force
  ```
- Flush specific namespace:
  ```bash
  python scripts/ops/cache_flush.py --namespace thoth:cache:scholar
  ```
- Service health check:
  ```bash
  python scripts/ops/health_check.py --url http://127.0.0.1:8000
  ```

## 4. Evaluation Workflows
- Run pipeline evaluation harness:
  ```bash
  python scripts/eval/run_evals.py
  ```
- Run multi-turn conversational simulations:
  ```bash
  python scripts/eval/run_multiturn_simulation.py
  ```
