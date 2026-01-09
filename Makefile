# =========================================================
# FishBroWFS Makefile (PRODUCT + GATES MINIMAL)
#
# PRODUCT ENTRYPOINTS:
#   make up         start backend (run_stack run) + launch Desktop UI
#   make down       stop everything (guarantee port 8000 freed)
#   make check      run product test gate
#   make acceptance run final acceptance gate
#
# OPS INTERNAL (not user entrypoints):
#   make doctor / status / ports / logs
# =========================================================

SHELL := /bin/bash
.SHELLFLAGS := -lc

PYTHON ?= .venv/bin/python
ENV ?= PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src

# Backend
SUP_URL ?= http://127.0.0.1:8000
SUP_HEALTH ?= $(SUP_URL)/health

# Runtime files
SUP_DIR := outputs/_trash
SUP_PID := $(SUP_DIR)/stack.pid
SUP_LOG := $(SUP_DIR)/stack_stdout.log

# Testing
PYTEST ?= $(PYTHON) -m pytest
PYTEST_ARGS ?= -q
PYTEST_MARK_EXPR_PRODUCT ?= not slow and not legacy_ui

.PHONY: help up down check acceptance doctor status ports logs

help:
	@echo ""
	@echo "FishBroWFS PRODUCT COMMANDS"
	@echo "  make up          Start backend + launch Desktop UI"
	@echo "  make down        Stop all processes (frees port 8000)"
	@echo "  make check       Run product tests"
	@echo "  make acceptance  Run final acceptance harness"
	@echo ""
	@echo "OPS INTERNAL"
	@echo "  make doctor      Pre-flight checks"
	@echo "  make status      Backend health status"
	@echo "  make ports       Port ownership"
	@echo "  make logs        Tail logs"
	@echo ""

# -----------------------------
# OPS INTERNAL (canonical stack)
# -----------------------------
doctor:
	@echo "==> Doctor..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py doctor

status:
	@echo "==> Status..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py status

ports:
	@echo "==> Ports..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py ports

logs:
	@echo "==> Logs..."
	$(ENV) $(PYTHON) -B scripts/run_stack.py logs

# -----------------------------
# PRODUCT: up/down
# -----------------------------
up:
	@set -euo pipefail; \
	echo "==> Checking backend health..."; \
	if curl -s -f --connect-timeout 1 --max-time 2 $(SUP_HEALTH) >/dev/null 2>&1; then \
		echo "✓ Backend already healthy"; \
	else \
		echo "==> Backend not healthy, starting stack..."; \
		mkdir -p $(SUP_DIR); \
		$(ENV) $(PYTHON) -B scripts/run_stack.py run >$(SUP_LOG) 2>&1 & \
		pid=$$!; \
		echo $$pid >$(SUP_PID); \
		echo "==> Waiting for backend to become healthy (max 30s)..."; \
		for i in $$(seq 1 30); do \
			if curl -s -f --connect-timeout 1 --max-time 2 $(SUP_HEALTH) >/dev/null 2>&1; then \
				echo "✓ Backend healthy after $$i seconds"; \
				break; \
			fi; \
			sleep 1; \
			if [ $$i -eq 30 ]; then \
				echo "✗ Backend failed to start within 30s"; \
				echo "---- tail $(SUP_LOG) ----"; \
				tail -n 120 $(SUP_LOG) || true; \
				echo "---- tail /tmp/fishbro_backend.log ----"; \
				tail -n 120 /tmp/fishbro_backend.log 2>/dev/null || true; \
				exit 2; \
			fi; \
		done; \
	fi; \
	echo "==> Launching Desktop UI..."; \
	$(ENV) $(PYTHON) -B scripts/desktop_launcher.py

down:
	@set -euo pipefail; \
	echo "==> Stopping system..."; \
	if [ -f $(SUP_PID) ]; then \
		pid=$$(cat $(SUP_PID)); \
		if kill -0 $$pid 2>/dev/null; then \
			echo "==> Killing stack PID $$pid"; \
			kill $$pid || true; \
			sleep 2; \
			kill -9 $$pid 2>/dev/null || true; \
		fi; \
		rm -f $(SUP_PID); \
	fi; \
	$(ENV) $(PYTHON) -B scripts/run_stack.py down || true; \
	echo "==> Done."

# -----------------------------
# GATES
# -----------------------------
check:
	@echo "==> Running product tests (mark expr: $(PYTEST_MARK_EXPR_PRODUCT))..."
	$(ENV) $(PYTEST) $(PYTEST_ARGS) -m "$(PYTEST_MARK_EXPR_PRODUCT)"

acceptance:
	@echo "==> Running final acceptance..."
	$(ENV) bash scripts/acceptance/run_final_acceptance.sh
