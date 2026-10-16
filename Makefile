.PHONY: help setup dev dev-web test test-ui eval lint migrate migrate-dry-run seed seed-reset cache-flush health diagnostics clean deploy

VENV ?= venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
PYTEST ?= $(VENV)/bin/pytest
UVICORN ?= $(VENV)/bin/uvicorn

help:
	@echo "========================================================================"
	@echo "                        THOTH MONOREPO TOOLKIT                          "
	@echo "========================================================================"
	@echo "Usage: make [target]"
	@echo ""
	@echo "Core Targets:"
	@echo "  setup            Set up local virtual environment & install dependencies"
	@echo "  dev              Start the FastAPI backend with hot reload (port 8000)"
	@echo "  dev-web          Start the standalone frontend dev server (port 3000)"
	@echo "  test             Run all test suites via pytest"
	@echo "  test-ui          Run the Web API adapter test suite"
	@echo "  eval             Run the production multi-agent DeepEval benchmark"
	@echo "  lint             Verify code syntax and validate module imports"
	@echo ""
	@echo "Database & Ops:"
	@echo "  migrate          Migrate local SQLite store.db into Supabase Postgres"
	@echo "  migrate-dry-run  Preview SQLite to Supabase migration without writing"
	@echo "  seed             Seed demo research sessions and reports"
	@echo "  seed-reset       Reset and re-seed demo data"
	@echo "  cache-flush      Flush or inspect Redis / local memory cache"
	@echo "  health           Probe backend health and database reachability"
	@echo "  diagnostics      Run full 7-layer agentic diagnostic suite"
	@echo ""
	@echo "Deployment:"
	@echo "  deploy           Instructions and checks for deploying to Railway"
	@echo "  clean            Remove temporary cache directories and build artifacts"
	@echo "========================================================================"

setup:
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating Python virtual environment in $(VENV)..."; \
		python3 -m venv $(VENV); \
	fi
	@echo "Installing backend requirements..."
	@$(PIP) install --upgrade pip
	@$(PIP) install -r backend/requirements.txt
	@if [ -f "backend/requirements-dev.txt" ]; then \
		$(PIP) install -r backend/requirements-dev.txt; \
	fi
	@if [ ! -f ".env" ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
	fi
	@echo "Setup complete. Run 'make dev' to start the application."

dev:
	@echo "Starting Thoth Backend server on http://localhost:8000..."
	@$(UVICORN) backend.main:app --host 0.0.0.0 --port 8000 --reload

dev-web:
	@echo "Starting Thoth Frontend server on http://localhost:3000..."
	@cd frontend && python3 -m http.server 3000

test:
	@echo "Running core unit, db, schema, and API adapter test suites..."
	@$(PYTEST) backend/tests/test_pure_functions.py backend/tests/test_db.py backend/tests/test_ui_adapter.py backend/tests/test_schemas.py backend/tests/test_dispatcher.py backend/tests/test_all_ten_frameworks.py backend/tests/test_claim_evidence_integrity.py backend/tests/test_document_ingestion.py backend/tests/test_research_mandate_and_approval.py backend/tests/test_audit_forensic_invariants.py backend/tests/test_task_lifecycle_persistence.py backend/tests/test_evidence_provenance_and_verification.py backend/tests/test_evidence_audit_and_correctness_gate.py backend/tests/test_idea_hypothesis_lifecycle.py backend/tests/test_thinker_dialectic_and_counter_evidence.py backend/tests/test_prisma_review_and_evidence_synthesis.py -v

test-all:
	@echo "Running all pytest test suites..."
	@$(PYTEST) backend/tests/ -v

test-ui:
	@echo "Running Web API adapter test suite..."
	@$(PYTEST) backend/tests/test_ui_adapter.py -v

eval:
	@echo "Running Thoth DeepEval Benchmark..."
	@$(PYTHON) backend/evals/run_production_evals.py

lint:
	@echo "Validating Python syntax and imports..."
	@$(PYTHON) -m py_compile backend/main.py
	@$(PYTHON) -c "import backend.main; import backend.core.config; print('All core modules imported successfully.')"

migrate:
	@echo "Migrating SQLite db/store.db to Supabase Postgres..."
	@$(PYTHON) scripts/db/migrate_sqlite_to_supabase.py

migrate-dry-run:
	@echo "Previewing SQLite to Supabase migration (dry-run)..."
	@$(PYTHON) scripts/db/migrate_sqlite_to_supabase.py --dry-run

seed:
	@echo "Seeding database with demo research sessions..."
	@$(PYTHON) scripts/db/seed.py --target auto

seed-reset:
	@echo "Resetting and re-seeding demo records..."
	@$(PYTHON) scripts/db/seed.py --target auto --reset

cache-flush:
	@echo "Flushing Redis cache..."
	@$(PYTHON) scripts/ops/cache_flush.py

health:
	@echo "Probing Thoth health..."
	@$(PYTHON) scripts/ops/health_check.py --url http://localhost:8000

diagnostics:
	@echo "Running 7-layer diagnostic audit..."
	@$(PYTHON) scripts/dev/diagnostic_test.py

deploy:
	@echo "========================================================================"
	@echo "                   RAILWAY DEPLOYMENT CHECKLIST                         "
	@echo "========================================================================"
	@echo "Service 1: Backend API (FastAPI)"
	@echo "  - Directory: repo root"
	@echo "  - Config: backend/railway.toml"
	@echo "  - Start: uvicorn backend.main:app --host 0.0.0.0 --port \$$PORT"
	@echo "  - Required Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, REDIS_URL,"
	@echo "                  OPENAI_API_KEY, NVIDIA_API_KEY, TAVILY_API_KEY"
	@echo ""
	@echo "Service 2: Frontend Client (Nginx Alpine)"
	@echo "  - Root Directory: frontend/"
	@echo "  - Config: frontend/railway.toml & frontend/Dockerfile"
	@echo "  - Env: None required (runtime env injected or uses origin API)"
	@echo "========================================================================"

clean:
	@echo "Cleaning temporary files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean completed."
