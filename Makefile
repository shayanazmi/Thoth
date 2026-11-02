# Thoth · Developed by Shayan Azmi
.PHONY: help setup dev test test-live lint health docker docker-down clean

VENV   ?= .venv
PYTHON ?= $(VENV)/bin/python
PIP    ?= $(VENV)/bin/pip

help:
	@echo "Thoth: a research companion"
	@echo ""
	@echo "  make setup        create $(VENV), install the backend and test requirements, create .env"
	@echo "  make dev          run Thoth at http://localhost:8000 (API and UI, auto-reload)"
	@echo "  make test         run the scenario test suite (offline, no keys needed)"
	@echo "  make test-live    also run the live-model test (uses your keys)"
	@echo "  make lint         ruff over the backend"
	@echo "  make health       probe a running server"
	@echo "  make docker       build and run with Docker Compose"
	@echo "  make clean        remove caches"

setup:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r backend/requirements-dev.txt
	@test -f .env || cp .env.example .env
	@echo "Ready. Add your NVIDIA_API_KEY to .env, then run: make dev"

dev:
	@$(PYTHON) -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

test:
	@$(PYTHON) -m pytest

test-live:
	@THOTH_LIVE_TESTS=1 $(PYTHON) -m pytest

lint:
	@$(PYTHON) -m ruff check backend

health:
	@$(PYTHON) server/health_check.py --url http://localhost:8000

docker:
	@docker compose -f server/docker-compose.yml up --build

docker-down:
	@docker compose -f server/docker-compose.yml down

clean:
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache
