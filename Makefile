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

.PHONY: help check doctor status ports logs down down-canonical status-canonical ports-canonical supervisor up

help:
	@echo ""
	@echo "FishBroWFS Desktop Product (Phase 16 - Desktop UI 1:1)"
	@echo ""
	@echo "PRODUCT COMMANDS (Desktop is the ONLY product UI):"
	@echo "  make up               Ensure supervisor healthy, then launch desktop UI"
	@echo "  make down             Stop all fishbro processes"
	@echo ""
	@echo "STACK INTERNAL:"
	@echo "  make doctor           Run pre-flight checks (deps, health)"
	@echo "  make status           Check backend/worker health"
	@echo "  make ports            Show port ownership"
	@echo "  make logs             Show logs"
	@echo ""
	@echo "ENVIRONMENT VARIABLES:"
	@echo "  DESKTOP_QPA=platform  Set Qt platform (wayland, xcb, offscreen, etc.)"
	@echo "                        Auto-detects Wayland if WAYLAND_DISPLAY is set"
	@echo ""
	@echo "TESTING:"
	@echo "  make check            Run product tests (excludes legacy UI and slow)"
	@echo ""

# -----------------------------------------------------------------------------
# Canonical Supervisor Targets
# -----------------------------------------------------------------------------

doctor:
	@echo "==> Running pre-flight checks (doctor)..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py doctor


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
	QT_QPA_PLATFORM=wayland \
	QT_AUTO_SCREEN_SCALE_FACTOR=1 \
	$(ENV) $(PYTHON) -B scripts/desktop_launcher.py


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






check:
	@echo "==> Running product CI tests (mark expr: $(PYTEST_MARK_EXPR_PRODUCT))..."
	$(ENV) $(PYTEST) $(PYTEST_ARGS) -m "$(PYTEST_MARK_EXPR_PRODUCT)"

