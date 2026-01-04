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

# Test selection variables (override-friendly)
PYTEST ?= $(PYTHON) -m pytest
PYTEST_ARGS ?= -q
PYTEST_MARK_EXPR_PRODUCT ?= not slow and not legacy_ui
PYTEST_MARK_EXPR_ALL ?= not legacy_ui

.PHONY: help check check-legacy test portfolio-gov-test portfolio-gov-smoke precommit clean-cache clean-all clean-snapshot clean-caches clean-caches-dry compile legacy-gui legacy-dashboard desktop desktop-wayland desktop-offscreen war-room run-research run-plateau run-freeze run-compile run-season snapshot forensics ui-forensics ui-contract legacy-backend legacy-worker status legacy-war legacy-stop-war ports down gui-safe legacy-up doctor run logs

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
	@echo "Pipeline:"
	@echo "  make run-research     [Phase 2]  Backtest"
	@echo "  make run-plateau      [Phase 3A] Plateau"
	@echo "  make run-freeze       [Phase 3B] Freeze"
	@echo "  make run-compile      [Phase 3C] Compile"
	@echo ""
	@echo "Phase 2 Migration (Supervisor):"
	@echo "  make clean-cache      Clean cache via Supervisor"
	@echo "  make clean-cache-legacy  Legacy cache cleaning (if available)"
	@echo "  make clean-caches     Alias for clean-cache"
	@echo "  make clean-caches-dry Dry-run cache cleaning"
	@echo "  make generate-reports Generate reports via Supervisor"
	@echo "  make generate-reports-legacy Legacy report generation"
	@echo "  Note: build-data requires parameters, use Supervisor CLI directly"
	@echo ""
	@echo "LEGACY / DEPRECATED (NiceGUI/web UI decommissioned):"
	@echo "  make legacy-gui       Launch legacy NiceGUI (deprecated)"
	@echo "  make legacy-dashboard Launch legacy dashboard (deprecated)"
	@echo "  make legacy-backend   Start Control API server only"
	@echo "  make legacy-worker    Start Worker daemon only"
	@echo "  make legacy-war       Start backend + worker (no GUI)"
	@echo "  make legacy-stop-war  Stop backend + worker"
	@echo "  make legacy-up        Start full stack with tmux"
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

legacy-gui:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1

legacy-dashboard:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1

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

war-room: legacy-gui
	@echo "==> [LEGACY] Starting war room (NiceGUI web UI)"
	@echo "    WARNING: Web UI is decommissioned. Use 'make desktop' instead."

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

legacy-backend:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1

legacy-worker:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1

legacy-war:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1

legacy-stop-war:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1


gui-safe:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1

legacy-up:
	@echo "ERROR: NiceGUI has been fully removed. Use 'make desktop' (Qt UI)."
	@exit 1

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

clean-cache-legacy:
	@echo "==> [LEGACY] Cleaning cache using legacy implementation..."
	@echo "ERROR: Legacy clean-cache implementation not found. Use 'make clean-cache' instead."
	@exit 1

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

build-data-legacy:
	@echo "==> [LEGACY] Building data using legacy implementation..."
	@echo "ERROR: Legacy build-data implementation not found. Use Qt Desktop UI 'Prepare Data' button or Supervisor CLI."
	@exit 1

generate-reports:
	@echo "==> Generating reports via Supervisor (GENERATE_REPORTS job)..."
	$(ENV) $(PYTHON) -B -m src.control.supervisor.cli submit \
		--job-type GENERATE_REPORTS \
		--params-json '{"outputs_root": "outputs", "strict": true}'

generate-reports-legacy:
	@echo "==> [LEGACY] Generating reports using legacy implementation..."
	$(ENV) $(PYTHON) -B scripts/generate_research.py --outputs-root outputs
