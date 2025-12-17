PROJECT_ROOT := $(CURDIR)
CACHE_CLEANER := GM_Huang/clean_repo_caches.py
RELEASE_TOOL := GM_Huang/release_tool.py

.PHONY: help check test research perf perf-mid perf-heavy clean-caches clean-caches-dry compile release-txt release-zip

help:
	@echo ""
	@echo "FishBroWFS_V2 Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make check            Clean caches + safe pytest (RECOMMENDED)"
	@echo "  make test             Safe pytest only"
	@echo "  make research         Run slow research-grade tests"
	@echo "  make perf             Run perf harness baseline (20000×1000, stdout-only, non-CI)"
	@echo "  make perf-mid         Run perf harness mid-tier (20000×10000)"
	@echo "  make perf-heavy       Run perf harness heavy-tier (200000×10000, expensive)"
	@echo "  make clean-caches      Clean python bytecode caches"
	@echo "  make clean-caches-dry  Dry-run cache cleanup"
	@echo "  make compile           Safe syntax check (no repo pollution)"
	@echo "  make release-txt       Generate release TXT (structure + code)"
	@echo "  make release-zip       Generate release ZIP (excludes .git)"
	@echo ""

# ---------------------------------------------------------
# Cache cleanup (Constitution-enforced)
# ---------------------------------------------------------
clean-caches:
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 python -B $(CACHE_CLEANER) || true

clean-caches-dry:
	@cd $(PROJECT_ROOT) && FISHBRO_DRY_RUN=1 PYTHONDONTWRITEBYTECODE=1 python -B $(CACHE_CLEANER) || true

# ---------------------------------------------------------
# Testing (safe mode)
# ---------------------------------------------------------
test:
	@cd $(PROJECT_ROOT) && echo "==> Running pytest (no bytecode, no numba cache)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=src python -B -m pytest -q

check:
	@cd $(PROJECT_ROOT) && echo "==> [0/2] Pre-cleaning bytecode caches (Constitution-enforced)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 python -B $(CACHE_CLEANER) || true
	@echo ""
	@cd $(PROJECT_ROOT) && echo "==> [1/2] Running pytest (no bytecode, no numba cache)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=src python -B -m pytest -q
	@echo ""
	@cd $(PROJECT_ROOT) && echo "==> [2/2] Post-cleaning bytecode caches (ensure no pollution)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 python -B $(CACHE_CLEANER) || true

research:
	@cd $(PROJECT_ROOT) && echo "==> Running research-grade tests (slow)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=src python -B -m pytest -q -m slow -vv

# ---------------------------------------------------------
# Performance harness (stdout-only, non-CI)
# ---------------------------------------------------------
perf:
	@cd $(PROJECT_ROOT) && echo "==> Running perf harness baseline (20000×1000, stdout-only; non-CI)"
	@cd $(PROJECT_ROOT) && FISHBRO_PERF_BARS=20000 FISHBRO_PERF_PARAMS=1000 PYTHONPATH=$(PROJECT_ROOT)/src PYTHONDONTWRITEBYTECODE=1 python -B scripts/perf_grid.py

perf-mid:
	@cd $(PROJECT_ROOT) && echo "==> Running perf harness mid-tier (20000×10000, hot_runs=3, timeout=1200s)"
	@cd $(PROJECT_ROOT) && FISHBRO_PERF_BARS=20000 FISHBRO_PERF_PARAMS=10000 FISHBRO_PERF_HOTRUNS=3 FISHBRO_PERF_TIMEOUT_S=1200 PYTHONPATH=$(PROJECT_ROOT)/src PYTHONDONTWRITEBYTECODE=1 python -B scripts/perf_grid.py

perf-heavy:
	@cd $(PROJECT_ROOT) && echo "WARNING: perf-heavy is expensive; use intentionally."
	@cd $(PROJECT_ROOT) && echo "==> Running perf harness heavy-tier (200000×10000, hot_runs=1, timeout=3600s)"
	@cd $(PROJECT_ROOT) && FISHBRO_PERF_BARS=200000 FISHBRO_PERF_PARAMS=10000 FISHBRO_PERF_HOTRUNS=1 FISHBRO_PERF_TIMEOUT_S=3600 PYTHONPATH=$(PROJECT_ROOT)/src PYTHONDONTWRITEBYTECODE=1 python -B scripts/perf_grid.py

# ---------------------------------------------------------
# Safe syntax check
# ---------------------------------------------------------
compile:
	@cd $(PROJECT_ROOT) && echo "==> Compile check (no bytecode)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 python -B -m compileall -q src tests

# ---------------------------------------------------------
# Release tools
# ---------------------------------------------------------
release-txt:
	@cd $(PROJECT_ROOT) && echo "==> Generating release TXT (structure + code)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 python -B $(RELEASE_TOOL) txt

release-zip:
	@cd $(PROJECT_ROOT) && echo "==> Generating release ZIP (excludes .git)"
	@cd $(PROJECT_ROOT) && PYTHONDONTWRITEBYTECODE=1 python -B $(RELEASE_TOOL) zip
