PROJECT_ROOT := $(CURDIR)
CACHE_CLEANER := GM_Huang/clean_repo_caches.py
RELEASE_TOOL := GM_Huang/release_tool.py
VIEWER_APP := $(shell PYTHONPATH=src python3 -c "import FishBroWFS_V2.gui.viewer.app as m; import inspect; print(inspect.getsourcefile(m))")

.PHONY: help check test research perf perf-mid perf-heavy clean-caches clean-caches-dry clean-data compile release-txt release-zip gui demo contract

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
	@echo "  make clean-data        Clean parquet data cache (Binding #4)"
	@echo "  make compile           Safe syntax check (no repo pollution)"
	@echo "  make release-txt       Generate release TXT (structure + code)"
	@echo "  make release-zip       Generate release ZIP (excludes .git)"
	@echo "  make gui               Start GUI stack (Control API + Mission UI)"
	@echo "  make demo              Create demo job for Viewer validation"
	@echo "  make contract          Run critical contract tests (regression prevention)"
	@echo ""

# ---------------------------------------------------------
# Cache cleanup (Constitution-enforced)
# ---------------------------------------------------------
clean-caches:
	@PYTHONDONTWRITEBYTECODE=1 python3 -B $(CACHE_CLEANER) || true

clean-caches-dry:
	@FISHBRO_DRY_RUN=1 PYTHONDONTWRITEBYTECODE=1 python3 -B $(CACHE_CLEANER) || true

clean-data:
	@echo "==> Cleaning parquet data cache (Binding #4: Parquet is Cache, Not Truth)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/clean_data_cache.py

# ---------------------------------------------------------
# Testing (safe mode)
# ---------------------------------------------------------
test:
	@echo "==> Running pytest (no bytecode, no numba cache)"
	@PYTHONDONTWRITEBYTECODE=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=src python3 -B -m pytest -q

check:
	@echo "==> [0/2] Pre-cleaning bytecode caches (Constitution-enforced)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B $(CACHE_CLEANER) || true
	@echo ""
	@echo "==> [1/2] Running pytest (no bytecode, no numba cache)"
	@PYTHONDONTWRITEBYTECODE=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=src python3 -B -m pytest -q
	@echo ""
	@echo "==> [2/2] Post-cleaning bytecode caches (ensure no pollution)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B $(CACHE_CLEANER) || true

research:
	@echo "==> Running research-grade tests (slow)"
	@PYTHONDONTWRITEBYTECODE=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=src python3 -B -m pytest -q -m slow -vv

# ---------------------------------------------------------
# Performance harness (stdout-only, non-CI)
# ---------------------------------------------------------
perf:
	@echo "==> Running perf harness baseline (20000×1000, stdout-only; non-CI)"
	@FISHBRO_PERF_BARS=20000 FISHBRO_PERF_PARAMS=1000 PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/perf_grid.py

perf-mid:
	@echo "==> Running perf harness mid-tier (20000×10000, hot_runs=3, timeout=1200s)"
	@FISHBRO_PERF_BARS=20000 FISHBRO_PERF_PARAMS=10000 FISHBRO_PERF_HOTRUNS=3 FISHBRO_PERF_TIMEOUT_S=1200 PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/perf_grid.py

perf-heavy:
	@echo "WARNING: perf-heavy is expensive; use intentionally."
	@echo "==> Running perf harness heavy-tier (200000×10000, hot_runs=1, timeout=3600s)"
	@FISHBRO_PERF_BARS=200000 FISHBRO_PERF_PARAMS=10000 FISHBRO_PERF_HOTRUNS=1 FISHBRO_PERF_TIMEOUT_S=3600 PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/perf_grid.py

# ---------------------------------------------------------
# Safe syntax check
# ---------------------------------------------------------
compile:
	@echo "==> Compile check (no bytecode)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B -m compileall -q src tests

# ---------------------------------------------------------
# Release tools
# ---------------------------------------------------------
release-txt:
	@echo "==> Generating release TXT (structure + code)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B $(RELEASE_TOOL) txt

release-zip:
	@echo "==> Generating release ZIP (excludes .git)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B $(RELEASE_TOOL) zip

# ---------------------------------------------------------
# GUI stack (Mission Control + Viewer)
# ---------------------------------------------------------
gui:
	@echo "==> Starting FishBroWFS_V2 GUI stack"
	@echo " - Control API      : http://localhost:8000"
	@echo " - Mission Control  : http://localhost:8080"
	@echo " - Viewer (B5)      : http://localhost:8502"
	@echo "Press Ctrl+C to stop all services"
	@echo ""
	@command -v uvicorn >/dev/null 2>&1 || { echo "ERROR: uvicorn not installed (pip install uvicorn fastapi)"; exit 1; }
	@python3 -c "import nicegui" 2>/dev/null || { echo "ERROR: nicegui not installed (pip install nicegui)"; exit 1; }
	@python3 -c "import streamlit" 2>/dev/null || { echo "ERROR: streamlit not installed (pip install streamlit)"; exit 1; }
	@bash -c 'trap "kill %1 %2 2>/dev/null || true; exit" EXIT INT TERM; \
		PYTHONPATH=src uvicorn FishBroWFS_V2.control.api:app --port 8000 & \
		PYTHONPATH=src python3 -m FishBroWFS_V2.control.app_nicegui & \
		PYTHONPATH=src streamlit run $(VIEWER_APP) --server.port 8502; \
		kill %1 %2 2>/dev/null || true'

demo:
	@echo "==> Creating demo job for Viewer validation"
	@PYTHONPATH=src python3 -m FishBroWFS_V2.control.seed_demo_run
