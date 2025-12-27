# =========================================================
# FishBroWFS Makefile (V3 War Room Edition)
# Fixed by Gemini - 2025-12-28
# =========================================================

# FORCE PYTHON VIRTUAL ENVIRONMENT (CRITICAL FIX)
PYTHON := .venv/bin/python

.PHONY: help check test precommit clean-cache clean-all clean-caches clean-caches-dry compile gui war-room run-research run-plateau run-freeze run-compile run-season snapshot

# ---------------------------------------------------------
# Help
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# GUI Entry Point (Corrected)
# ---------------------------------------------------------
gui:
	@echo "==> Launching FishBro War Room..."
	# 使用 PYTHONPATH=src 確保能抓到 FishBroWFS_V2 模組
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) -B main.py

war-room: gui

# ---------------------------------------------------------
# V3 Production Shortcuts
# ---------------------------------------------------------
run-research:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/run_research_v3.py

run-plateau:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/run_phase3a_plateau.py

run-freeze:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/run_phase3b_freeze.py

run-compile:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/run_phase3c_compile.py

run-season: run-research run-plateau run-freeze run-compile

snapshot:
	@echo "==> Generating Context Snapshot..."
	$(PYTHON) scripts/dump_context.py

# ---------------------------------------------------------
# Testing
# ---------------------------------------------------------
check:
	@echo "==> Running fast CI-safe tests (excluding slow research-grade tests)..."
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest

test:
	@echo "==> Running all tests (including slow research-grade tests)..."
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -m "slow or not slow"

# ---------------------------------------------------------
# Cleaning
# ---------------------------------------------------------
clean-all:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache