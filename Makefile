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
# Legacy GUI port (different from official dashboard port)
GUI_PORT ?= 8081
# Dashboard-specific variables (constitution-safe defaults)
DASH_HOST ?= $(UI_HOST)
DASH_PORT ?= $(UI_PORT)
DASH_RELOAD ?= 0
DASH_SHOW ?= 0

# Desktop (PySide6) variables
# Set to 'wayland', 'xcb', 'offscreen', etc. Leave empty for auto-detection
# Auto-detection prefers Wayland if WAYLAND_DISPLAY is set, otherwise uses default
DESKTOP_QPA ?=

# Desktop offscreen helper (CI/dev)
DESKTOP_OFFSCREEN ?= QT_QPA_PLATFORM=offscreen

# Supervisor variables (make up/down)
SUP_URL ?= http://127.0.0.1:8000
SUP_HEALTH ?= $(SUP_URL)/health
SUP_PID ?= outputs/_trash/supervisor.pid
SUP_LOG ?= outputs/_trash/supervisor_stdout.log

# Test selection variables (override-friendly)
PYTEST ?= $(PYTHON) -m pytest
PYTEST_ARGS ?= -q
PYTEST_MARK_EXPR_PRODUCT ?= not slow and not legacy_ui
PYTEST_MARK_EXPR_ALL ?= not legacy_ui

.PHONY: help check check-legacy test portfolio-gov-test portfolio-gov-smoke precommit clean-cache clean-all clean-snapshot clean-caches clean-caches-dry compile desktop desktop-wayland desktop-offscreen snapshot api-snapshot forensics ui-forensics ui-contract status ports down doctor run logs supervisor up down up-status

help:
	@echo ""
	@echo "FishBroWFS Desktop Product (Phase 16 - Desktop UI 1:1)"
	@echo ""
	@echo "PRODUCT COMMANDS (Desktop is the ONLY product UI):"
	@echo "  make doctor           Run pre-flight checks (deps, health)"
	@echo "  make desktop          Launch Desktop Control Station (PySide6, no ports)"
	@echo "  make desktop-wayland  Launch Desktop with XCB/XWayland fallback (if Wayland fails)"
	@echo "  make desktop-offscreen Launch Desktop in offscreen mode (CI/dev)"
	@echo "  make down             Stop all fishbro processes"
	@echo "  make status           Check backend/worker health"
	@echo "  make logs             Show logs"
	@echo "  make supervisor       Start supervisor (backend API) in foreground"
	@echo "  make up               Ensure supervisor healthy, then launch desktop UI"
	@echo "  make up-status        Show supervisor PID and health status"
	@echo ""
	@echo "ENVIRONMENT VARIABLES:"
	@echo "  DESKTOP_QPA=platform  Set Qt platform (wayland, xcb, offscreen, etc.)"
	@echo "                        Auto-detects Wayland if WAYLAND_DISPLAY is set"
	@echo ""
	@echo "Testing:"
	@echo "  make check            Run product tests (excludes legacy UI and slow)"
	@echo "  make check-legacy     Run legacy UI tests only (historical reference)"
	@echo "  make portfolio-gov-test   Run portfolio governance unit tests"
	@echo "  make portfolio-gov-smoke  Smoke test governance modules"
	@echo ""
	@echo ""
	@echo "Phase 2 Migration (Supervisor):"
	@echo "  make clean-cache      Clean cache via Supervisor"
	@echo "  make clean-caches     Alias for clean-cache"
	@echo "  make clean-caches-dry Dry-run cache cleaning"
	@echo "  make generate-reports Generate reports via Supervisor"
	@echo "  Note: build-data requires parameters, use Supervisor CLI directly"
	@echo ""

# -----------------------------------------------------------------------------
# Canonical Supervisor Targets
# -----------------------------------------------------------------------------

doctor:
	@echo "==> Running pre-flight checks (doctor)..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py doctor

run: desktop
	@echo "==> Desktop is the ONLY product UI (no web stack required)"

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


# -----------------------------------------------------------------------------
# Supervisor + Desktop Integration (make up)
# -----------------------------------------------------------------------------

supervisor:
	@echo "==> Starting supervisor (backend API) in foreground..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py run --no-worker

up:
	@set -euo pipefail; \
	echo "==> Checking supervisor health..."; \
	if curl -s -f $(SUP_HEALTH) >/dev/null 2>&1; then \
		echo "✓ Supervisor already healthy at $(SUP_HEALTH)"; \
	else \
		echo "==> Supervisor not healthy, starting in background..."; \
		mkdir -p $(dir $(SUP_PID)); \
		$(ENV) $(PYTHON) -B scripts/run_stack.py run --no-worker >$(SUP_LOG) 2>&1 & \
			pid=$$!; \
			echo $$pid >$(SUP_PID); \
		echo "==> Waiting for supervisor to become healthy (max 30s)..."; \
		for i in $$(seq 1 30); do \
			if curl -s -f $(SUP_HEALTH) >/dev/null 2>&1; then \
				echo "✓ Supervisor healthy after $$i seconds"; \
				break; \
			fi; \
			sleep 1; \
			if [ $$i -eq 30 ]; then \
				echo "✗ Supervisor failed to start within 30s"; \
				tail -n 120 $(SUP_LOG); \
				exit 2; \
			fi; \
		done; \
	fi; \
	echo "==> Launching desktop UI..."; \
	$(MAKE) desktop

up-status:
	@if [ -f $(SUP_PID) ]; then \
		pid=$$(cat $(SUP_PID)); \
		if kill -0 $$pid 2>/dev/null; then \
			echo "Supervisor PID $$pid is alive"; \
			if curl -s -f $(SUP_HEALTH) >/dev/null 2>&1; then \
				echo "Health check: OK"; \
			else \
				echo "Health check: FAILED"; \
			fi; \
		else \
			echo "Supervisor PID $$pid is dead"; \
		fi; \
	else \
		echo "No supervisor PID file ($(SUP_PID))"; \
	fi

down:
	@if [ -f $(SUP_PID) ]; then \
		pid=$$(cat $(SUP_PID)); \
		if kill -0 $$pid 2>/dev/null; then \
			echo "==> Stopping supervisor (PID $$pid)..."; \
			kill $$pid; \
			sleep 2; \
			if kill -0 $$pid 2>/dev/null; then \
				kill -9 $$pid; \
			fi; \
		fi; \
		rm -f $(SUP_PID); \
	fi
	@$(MAKE) down-canonical


# -----------------------------------------------------------------------------
# Desktop UI (Product Standard: Phase 18.5 Wayland Fixed)
# -----------------------------------------------------------------------------

.PHONY: desktop desktop-xcb desktop-offscreen

desktop:
	@echo "==> Launching FishBro Desktop [Wayland Standard Mode]..."
	@echo "    Note: Window decoration (Title Bar) is enabled."
	@# 移除 DISABLE_WINDOWDECORATION 以找回標題欄
	@# 協議崩潰問題將透過 scripts/desktop_launcher.py 內的 QTimer 延遲解決
	QT_QPA_PLATFORM=wayland \
	QT_AUTO_SCREEN_SCALE_FACTOR=1 \
	$(ENV) $(PYTHON) -B scripts/desktop_launcher.py

desktop-xcb:
	@echo "==> Launching FishBro Desktop [XCB/XWayland Fallback]..."
	@echo "    Use this if Wayland protocol errors persist."
	@# 強制使用 X11 協議跑在 XWayland 上，這是目前最穩定的顯示方案
	QT_QPA_PLATFORM=xcb \
	$(ENV) $(PYTHON) -B scripts/desktop_launcher.py

desktop-offscreen:
	@echo "==> Launching Desktop in Offscreen mode (CI/Dev)..."
	QT_QPA_PLATFORM=offscreen $(ENV) $(PYTHON) -B scripts/desktop_launcher.py



snapshot:
	@echo "==> Generating Context Snapshot..."
	$(ENV) $(PYTHON) -B scripts/dump_context.py

api-snapshot:
	@echo "==> Dumping OpenAPI contract snapshot..."
	@$(ENV) $(PYTHON) -m src.control.tools.dump_openapi --out tests/policy/api_contract/openapi.json

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
# Clean targets
# -----------------------------------------------------------------------------

clean-all:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build

clean-snapshot:
	rm -rf SNAPSHOT/*

# -----------------------------------------------------------------------------
# Phase 2: Supervisor Migration Targets (Strangler Pattern)
# -----------------------------------------------------------------------------

clean-cache:
	@echo "==> Cleaning cache via Supervisor (CLEAN_CACHE job)..."
	$(ENV) $(PYTHON) -B -m src.control.supervisor.cli submit \
		--job-type CLEAN_CACHE \
		--params-json '{"scope": "all", "dry_run": false}'


clean-caches:
	@echo "==> Cleaning caches via Supervisor (CLEAN_CACHE job with scope=all)..."
	$(ENV) $(PYTHON) -B -m src.control.supervisor.cli submit \
		--job-type CLEAN_CACHE \
		--params-json '{"scope": "all", "dry_run": false}'

clean-caches-dry:
	@echo "==> Dry-run cleaning caches via Supervisor..."
	$(ENV) $(PYTHON) -B -m src.control.supervisor.cli submit \
		--job-type CLEAN_CACHE \
		--params-json '{"scope": "all", "dry_run": true}'

build-data:
	@echo "==> Building data via Supervisor (BUILD_DATA job)..."
	@echo "ERROR: BUILD_DATA requires parameters. Use CLI directly:"
	@echo "  python -B -m src.control.supervisor.cli submit --job-type BUILD_DATA --params-json '{\"dataset_id\": \"...\", \"timeframe_min\": 60}'"
	@exit 1

generate-reports:
	@echo "==> Generating reports via Supervisor (GENERATE_REPORTS job)..."
	$(ENV) $(PYTHON) -B -m src.control.supervisor.cli submit \
		--job-type GENERATE_REPORTS \
		--params-json '{"outputs_root": "outputs", "strict": true}'
