# =========================================================
# FishBroWFS Makefile (LOCAL RESEARCH OS)
#
# Local mode:
#   - no HTTP, no ports
#   - single SSOT enqueue via control.supervisor.submit()
#   - sqlite3 is storage + monitor only (TUI reads RO)
#
# Entry points:
#   make worker   start local job orchestrator (poll QUEUED -> run handlers)
#   make tui      start TUI control station (submit in-proc, monitor sqlite RO)
#   make test     run test suite (pytest)
#   make check    sanity gate (compile + import smoke + tests)
#   make clear-*  remove caches
# =========================================================

SHELL := /bin/bash
.SHELLFLAGS := -lc

PYTHON ?= .venv/bin/python

# Central cache layout (repo root)
CACHE_ROOT ?= cache

# Central outputs layout (repo root)
OUTPUTS_ROOT ?= outputs

# Default runtime env used by worker/tui/check.
# Keep these here so subprocess handlers inherit consistent cache paths.
ENV ?= PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
	FISHBRO_OUTPUTS_ROOT=$(OUTPUTS_ROOT) \
	FISHBRO_CACHE_ROOT=$(CACHE_ROOT) \
	NUMBA_CACHE_DIR=$(CACHE_ROOT)/numba

CHECK_ENV ?= $(ENV) PYTHONWARNINGS=ignore::DeprecationWarning

.PHONY: help worker tui tui-inline check test clear-py clear-cache clear

help:
	@echo ""
	@echo "FishBroWFS LOCAL RESEARCH OS"
	@echo "  make worker   Start supervisor worker loop (no HTTP)"
	@echo "  make tui      Start TUI (submit in-proc, monitor sqlite RO)"
	@echo "  make test     Run pytest"
	@echo "  make check    Sanity checks (compile + import smoke + tests)"
	@echo "  make clear-py    Remove Python caches"
	@echo "  make clear-cache Remove repo caches (cache/)"
	@echo ""

worker:
	@if command -v gnome-terminal &> /dev/null; then \
		gnome-terminal --title="FishBro Worker" -- bash -c "cd $(PWD) && $(ENV) $(PYTHON) -B -m control.supervisor.worker --max-workers 1 --tick-interval 0.2; exec bash"; \
	else \
		$(ENV) $(PYTHON) -B -m control.supervisor.worker --max-workers 1 --tick-interval 0.2; \
	fi

tui:
	@if command -v gnome-terminal &> /dev/null; then \
		gnome-terminal --title="FishBro TUI" -- bash -c "cd $(PWD) && $(ENV) $(PYTHON) -B src/gui/tui/app.py; exec bash"; \
	else \
		$(ENV) $(PYTHON) -B src/gui/tui/app.py; \
	fi

tui-inline:
	@$(ENV) $(PYTHON) -B src/gui/tui/app.py

test:
	@set -euo pipefail; \
	$(CHECK_ENV) $(PYTHON) -m pytest -q

check:
	@set -euo pipefail; \
	echo "==> Sanity: compileall"; \
	$(CHECK_ENV) $(PYTHON) -m compileall -q src; \
	echo "==> Sanity: import smoke"; \
	$(CHECK_ENV) $(PYTHON) -c "from control.supervisor import submit; from control.supervisor.db import SupervisorDB; from control.supervisor.models import JobSpec; from gui.tui.services.bridge import Bridge; print('ok: imports')"; \
	echo "==> Sanity: tests (pytest)"; \
	$(CHECK_ENV) $(PYTHON) -m pytest -q

clear-py:
	@set -euo pipefail; \
	rm -rf .pytest_cache .mypy_cache .ruff_cache **/__pycache__ || true; \
	find . -name "*.pyc" -o -name "*.pyo" | xargs -r rm -f || true

clear-cache:
	@set -euo pipefail; \
	rm -rf $(CACHE_ROOT) || true

clear: clear-py clear-cache
