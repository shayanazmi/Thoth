.PHONY: help setup dev dev-web test lint migrate migrate-dry-run seed seed-reset cache-flush health clean deploy test-vision

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
	@echo "  test             Alias for test-vision (canonical gate)"
	@echo "  test-vision      Run the vision-anchored scenario suite"
	@echo "  lint             Verify code syntax and validate module imports"
	@echo ""
	@echo "Database & Ops:"
	@echo "  migrate          Migrate local SQLite store.db into Supabase Postgres"
	@echo "  migrate-dry-run  Preview SQLite to Supabase migration without writing"
	@echo "  seed             Seed demo research sessions and reports"
	@echo "  seed-reset       Reset and re-seed demo data"
	@echo "  cache-flush      Flush or inspect Redis / local memory cache"
	@echo "  health           Probe backend health and database reachability"
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

test-vision:
	@echo "Running vision-anchored scenario suite (canonical gate)..."
	@$(PYTEST) backend/tests/scenarios/ -v

# `make test` is the same gate: behavioural scenarios anchored on THOTH.docx.
test: test-vision

lint:
	@echo "Validating Python syntax and imports..."
	@$(PYTHON) -m py_compile backend/main.py
	@$(PYTHON) -m py_compile backend/workspace/project.py backend/workspace/manuscript.py backend/workspace/exporter.py backend/workspace/pdf_compiler.py backend/workspace/journal_formatter.py backend/workspace/traceability.py backend/api/routes_workspace.py backend/collaboration/membership.py backend/collaboration/sync.py
	@$(PYTHON) -c "import backend.main; import backend.core.config; import backend.workspace; import backend.workspace.pdf_compiler; import backend.workspace.journal_formatter; import backend.collaboration; print('All core modules imported successfully.')"





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
