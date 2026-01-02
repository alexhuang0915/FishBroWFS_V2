# =========================================================
# FishBroWFS Makefile (V3 War Room Edition)
# =========================================================

# Runtime variables (override-friendly)
PYTHON ?= .venv/bin/python
ENV ?= PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
UI_HOST ?= 0.0.0.0
UI_PORT ?= 8080

# Test selection variables (override-friendly)
PYTEST ?= $(PYTHON) -m pytest
PYTEST_ARGS ?= -q
PYTEST_MARK_EXPR_PRODUCT ?= not slow and not legacy_ui
PYTEST_MARK_EXPR_ALL ?= not legacy_ui

.PHONY: help check check-legacy test portfolio-gov-test portfolio-gov-smoke precommit clean-cache clean-all clean-snapshot clean-caches clean-caches-dry compile gui dashboard war-room run-research run-plateau run-freeze run-compile run-season snapshot forensics ui-forensics ui-contract backend worker status war stop-war ports down gui-safe up doctor run logs

help:
	@echo ""
	@echo "FishBroWFS Governance Console (Phase 10 - RELEASE HYGIENE)"
	@echo ""
	@echo "Product Commands (Supported):"
	@echo "  make doctor           Run pre-flight checks (deps, ports, health)"
	@echo "  make run              Safe start full stack (backend+worker+dashboard)"
	@echo "  make dashboard        Launch Governance Console UI (official entry point)"
	@echo "  make down             Stop all fishbro processes"
	@echo "  make status           Check backend/worker/dashboard health"
	@echo "  make logs             Show logs"
	@echo "  make ports            Show port ownership"
	@echo ""
	@echo "Testing:"
	@echo "  make check            Run product tests (excludes legacy UI and slow)"
	@echo "  make check-legacy     Run legacy UI tests only (historical reference)"
	@echo "  make portfolio-gov-test   Run portfolio governance unit tests"
	@echo "  make portfolio-gov-smoke  Smoke test governance modules"
	@echo ""
	@echo "Pipeline:"
	@echo "  make run-research     [Phase 2]  Backtest"
	@echo "  make run-plateau      [Phase 3A] Plateau"
	@echo "  make run-freeze       [Phase 3B] Freeze"
	@echo "  make run-compile      [Phase 3C] Compile"
	@echo ""
	@echo "Legacy Ops (Deprecated - for backward compatibility only):"
	@echo "  make gui              Launch legacy GUI (deprecated)"
	@echo "  make backend          Start Control API server only"
	@echo "  make worker           Start Worker daemon only"
	@echo "  make war              Start backend + worker (no GUI)"
	@echo "  make stop-war         Stop backend + worker"
	@echo "  make up               Start full stack with tmux"
	@echo ""

# -----------------------------------------------------------------------------
# Canonical Supervisor Targets
# -----------------------------------------------------------------------------

doctor:
	@echo "==> Running pre-flight checks (doctor)..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py doctor

run:
	@echo "==> Safe start of full stack (backend+worker+gui)..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py run

down-canonical:
	@echo "==> Stopping all fishbro processes..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py down

down: down-canonical

status-canonical:
	@echo "==> Checking stack health..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py status

status: status-canonical

logs:
	@echo "==> Showing logs..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py logs

ports-canonical:
	@echo "==> Showing port ownership..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py ports

ports: ports-canonical

gui:
	@echo "==> Launching legacy GUI (deprecated)..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py run --no-backend --no-worker

dashboard:
	@echo "==> Launching Governance Console UI (official entry point)..."
	$(ENV) $(PYTHON) -B scripts/start_dashboard.py

war-room: gui

run-research:
	$(ENV) $(PYTHON) -B scripts/run_research_v3.py

run-plateau:
	$(ENV) $(PYTHON) -B scripts/run_phase3a_plateau.py

run-freeze:
	$(ENV) $(PYTHON) -B scripts/run_phase3b_freeze.py

run-compile:
	$(ENV) $(PYTHON) -B scripts/run_phase3c_compile.py

run-season: run-research run-plateau run-freeze run-compile

snapshot:
	@echo "==> Generating Context Snapshot..."
	$(ENV) $(PYTHON) -B scripts/dump_context.py

forensics ui-forensics:
	@echo "==> Generating UI Forensics Dump..."
	$(ENV) $(PYTHON) -B scripts/ui_forensics_dump.py

autopass:
	@echo "==> Running UI Autopass..."
	$(ENV) $(PYTHON) -B scripts/ui_autopass.py

render-probe:
	@echo "==> Running UI Render Probe..."
	$(ENV) $(PYTHON) -B scripts/ui_render_probe.py

ui-contract:
	@echo "==> Running UI Style Contract Tests..."
	@echo "Checking/installing Playwright browsers..."
	./scripts/_dev/install_playwright.sh
	FISHBRO_UI_CONTRACT=1 $(ENV) $(PYTHON) -B -m pytest -q -m ui_contract

check:
	@echo "==> Running product CI tests (mark expr: $(PYTEST_MARK_EXPR_PRODUCT))..."
	$(ENV) $(PYTEST) $(PYTEST_ARGS) -m "$(PYTEST_MARK_EXPR_PRODUCT)"

check-legacy:
	@echo "==> Running legacy UI tests only..."
	$(ENV) $(PYTEST) $(PYTEST_ARGS) -m "legacy_ui"

test:
	@echo "==> Running all tests (mark expr: $(PYTEST_MARK_EXPR_ALL))..."
	$(ENV) $(PYTEST) $(PYTEST_ARGS) -m "$(PYTEST_MARK_EXPR_ALL)"

portfolio-gov-test:
	@echo "==> Running portfolio governance unit tests..."
	$(ENV) $(PYTHON) -B -m pytest -q tests/portfolio

portfolio-gov-smoke:
	@echo "==> Smoke testing portfolio governance modules..."
	$(ENV) $(PYTHON) -B scripts/_dev/portfolio_governance_log_smoke.py | tee outputs/_dp_evidence/portfolio_gov_smoke.txt

# -----------------------------------------------------------------------------
# Ops targets
# -----------------------------------------------------------------------------

backend:
	@echo "==> Starting Control API server on $(BACKEND_HOST):$(BACKEND_PORT)..."
	@echo "    (Use BACKEND_HOST=... BACKEND_PORT=... to override)"
	$(ENV) $(PYTHON) -m uvicorn control.api:app --host $(BACKEND_HOST) --port $(BACKEND_PORT) --reload

worker:
	@echo "==> Starting Worker daemon..."
	@echo "    (Database: outputs/jobs.db)"
	$(ENV) $(PYTHON) -m control.worker_main outputs/jobs.db

war:
	@echo "==> Starting full stack (backend + worker)..."
	@echo "    Backend: http://$(BACKEND_HOST):$(BACKEND_PORT)"
	@echo "    Worker:  outputs/jobs.db"
	@echo "    Press Ctrl+C to stop both."
	@echo ""
	@echo "Starting backend in background..."
	@$(ENV) $(PYTHON) -m uvicorn control.api:app --host $(BACKEND_HOST) --port $(BACKEND_PORT) --reload > /tmp/fishbro_backend.log 2>&1 &
	@BACKEND_PID=$$!; \
	echo "Backend PID: $$BACKEND_PID"; \
	echo "Waiting for backend to start..."; \
	sleep 2; \
	echo "Starting worker in background..."; \
	$(ENV) $(PYTHON) -m control.worker_main outputs/jobs.db > /tmp/fishbro_worker.log 2>&1 & \
	WORKER_PID=$$!; \
	echo "Worker PID: $$WORKER_PID"; \
	echo ""; \
	echo "Backend and worker started. Logs:"; \
	echo "  Backend: /tmp/fishbro_backend.log"; \
	echo "  Worker:  /tmp/fishbro_worker.log"; \
	echo ""; \
	echo "Press Ctrl+C to stop both processes."; \
	trap 'echo ""; echo "Stopping processes..."; kill $$BACKEND_PID $$WORKER_PID 2>/dev/null || true; echo "Stopped."; exit 0' INT TERM; \
	wait

stop-war:
	@echo "==> Stopping backend and worker..."
	@pkill -f "uvicorn control.api:app" 2>/dev/null || true
	@pkill -f "control.worker_main" 2>/dev/null || true
	@echo "Stopped."


gui-safe:
	@ss -ltnp 2>/dev/null | rg ":\b$(UI_PORT)\b" >/dev/null 2>&1 && { \
	  echo "ERROR: Port $(UI_PORT) is already in use."; \
	  echo "Fix: run 'make ports' then 'make down' (or 'fuser -k $(UI_PORT)/tcp')."; \
	  exit 2; \
	} || true

up:
	@echo "==> Starting full stack (backend+worker+ui)..."
	@if command -v tmux >/dev/null 2>&1; then \
	  echo "Using tmux to start backend+worker+ui in separate panes..."; \
	  tmux new-session -d -s fishbro "make war" \; \
	    split-window -h "make gui" \; \
	    attach-session -t fishbro; \
	else \
	  echo "tmux not found. Please run in two terminals:"; \
	  echo "  Terminal 1: make war"; \
	  echo "  Terminal 2: make gui"; \
	  echo ""; \
	  echo "Or install tmux and run again."; \
	  exit 0; \
	fi

# -----------------------------------------------------------------------------
# Clean targets
# -----------------------------------------------------------------------------

clean-all:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build

clean-snapshot:
	rm -rf SNAPSHOT/*
