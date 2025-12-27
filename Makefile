# =========================================================
# FishBroWFS Makefile (V3 War Room Edition)
# =========================================================

PYTHON := .venv/bin/python
ENV := PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src

.PHONY: help check test precommit clean-cache clean-all clean-snapshot clean-caches clean-caches-dry compile gui war-room run-research run-plateau run-freeze run-compile run-season snapshot

help:
	@echo ""
	@echo "FishBroWFS Strategy Factory V3"
	@echo ""
	@echo "UI:"
	@echo "  make gui             Launch War Room UI"
	@echo ""
	@echo "Pipeline:"
	@echo "  make run-research    [Phase 2]  Backtest"
	@echo "  make run-plateau     [Phase 3A] Plateau"
	@echo "  make run-freeze      [Phase 3B] Freeze"
	@echo "  make run-compile     [Phase 3C] Compile"
	@echo ""

gui:
	@echo "==> Launching FishBro War Room..."
	# Use PYTHONPATH=src to resolve local packages from the repo.
	$(ENV) $(PYTHON) -B main.py

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

check:
	@echo "==> Running fast CI-safe tests (excluding slow research-grade tests)..."
	$(ENV) $(PYTHON) -B -m pytest

test:
	@echo "==> Running all tests (including slow research-grade tests)..."
	$(ENV) $(PYTHON) -B -m pytest -m "slow or not slow"

clean-all:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build

clean-snapshot:
	rm -rf SNAPSHOT/*
