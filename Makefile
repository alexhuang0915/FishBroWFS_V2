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
#   make check    minimal sanity gate (no pytest suite; tests removed by design)
# =========================================================

SHELL := /bin/bash
.SHELLFLAGS := -lc

PYTHON ?= .venv/bin/python
ENV ?= PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src
CHECK_ENV ?= $(ENV) PYTHONWARNINGS=ignore::DeprecationWarning

.PHONY: help worker tui check

help:
	@echo ""
	@echo "FishBroWFS LOCAL RESEARCH OS"
	@echo "  make worker   Start supervisor worker loop (no HTTP)"
	@echo "  make tui      Start TUI (submit in-proc, monitor sqlite RO)"
	@echo "  make check    Sanity checks (compile + import smoke)"
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

check:
	@set -euo pipefail; \
	echo "==> Sanity: compileall"; \
	$(CHECK_ENV) $(PYTHON) -m compileall -q src; \
	echo "==> Sanity: import smoke"; \
	$(CHECK_ENV) $(PYTHON) -c "from control.supervisor import submit; from control.supervisor.db import SupervisorDB; from control.supervisor.models import JobSpec; from gui.tui.services.bridge import Bridge; print('ok: imports')"; \
	echo "==> Sanity: local OS e2e (unittest)"; \
	$(CHECK_ENV) $(PYTHON) -m unittest discover -s tests -t . -p "test_*.py" -q
