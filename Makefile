PROJECT_ROOT := $(CURDIR)
CACHE_CLEANER := GM_Huang/clean_repo_caches.py
RELEASE_TOOL := GM_Huang/release_tool.py

# --- SAFE MODE (WSL / pytest / numba stabilization) ---
SAFE_ENV := NUMBA_DISABLE_CACHE=1 \
            OMP_NUM_THREADS=1 \
            MKL_NUM_THREADS=1 \
            NUMEXPR_NUM_THREADS=1

# Default: no xdist flags. User may override:
#   make test SAFE_PYTEST_ADDOPTS="-n 1"
SAFE_PYTEST_ADDOPTS ?=

# pytest command using venv pytest (not python3 -m pytest)
PYTEST := PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest

.PHONY: help check test research perf perf-mid perf-heavy clean-caches clean-caches-dry clean-data compile release-txt release-zip dashboard gui demo contract research-season portfolio-season phase3 phase4

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
	@echo "  make dashboard         Start FishBroWFS_V2 Dashboard (Official Entry Point)"
	@echo "  make demo              Create demo job for Viewer validation"
	@echo "  make contract          Run critical contract tests (regression prevention)"
	@echo "  make research-season   Generate research artifacts for season 2026Q1"
	@echo "  make portfolio-season  Generate portfolio from 2026Q1 research results"
	@echo "  make phase3            Run research-season → portfolio-season → smoke check"
	@echo "  make phase4            Validate Phase 4: Operational closed loop (UI Actions + Governance)"
	@echo "  make phase5            Validate Phase 5: Deterministic Governance & Reproducibility Lock"
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
	@echo "==> Running pytest (SAFE MODE)"
	@$(SAFE_ENV) $(PYTEST) -q $(PYTEST_ADDOPTS) $(SAFE_PYTEST_ADDOPTS)

check:
	@echo "==> [0/2] Pre-cleaning bytecode caches (Constitution-enforced)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B $(CACHE_CLEANER) || true
	@echo ""
	@echo "==> [1/2] Running pytest (no bytecode, no numba cache)"
	@$(SAFE_ENV) $(PYTEST) -q $(PYTEST_ADDOPTS) $(SAFE_PYTEST_ADDOPTS)
	@echo ""
	@echo "==> [2/2] Post-cleaning bytecode caches (ensure no pollution)"
	@PYTHONDONTWRITEBYTECODE=1 python3 -B $(CACHE_CLEANER) || true

.PHONY: check-safe
check-safe: check

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
# Dashboard stack (Official Dashboard Entry Point)
# ---------------------------------------------------------
dashboard:
	@echo "==> Starting FishBroWFS_V2 Dashboard (Official Entry Point)"
	@echo " - URL            : http://localhost:8080"
	@echo " - Health endpoint: http://localhost:8080/health"
	@echo "Press Ctrl+C to stop"
	@if [ ! -f ".venv/bin/python" ]; then \
		echo "❌ .venv not found. Run make venv first."; \
		exit 1; \
	fi
	@.venv/bin/python -c "import nicegui" 2>/dev/null || { echo "ERROR: nicegui not installed in venv (pip install nicegui)"; exit 1; }
	@PYTHONPATH=src .venv/bin/python -m FishBroWFS_V2.gui.nicegui.app

gui: dashboard
	@# Alias for dashboard (not advertised in help)

demo:
	@echo "==> Creating demo job for Viewer validation"
	@PYTHONPATH=src python3 -m FishBroWFS_V2.control.seed_demo_run

# ---------------------------------------------------------
# Phase 3: Reproducible closed loop (Research → Portfolio → UI)
# ---------------------------------------------------------
research-season:
	@echo "==> Generating research artifacts for season 2026Q1"
	@PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/generate_research.py --season 2026Q1

portfolio-season:
	@echo "==> Generating portfolio from 2026Q1 research results"
	@PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/build_portfolio_from_research.py --season 2026Q1

phase3: research-season portfolio-season
	@echo "==> Phase 3 completed: research → portfolio artifacts generated"
	@echo " - Research artifacts: outputs/seasons/2026Q1/research/"
	@echo " - Portfolio artifacts: outputs/seasons/2026Q1/portfolio/"
	@echo " - Run 'make dashboard' to verify UI pages"

# ---------------------------------------------------------
# Phase 4: Operational closed loop (UI Actions + Governance)
# ---------------------------------------------------------
phase4:
	@echo "==> Phase 4: Operational closed loop validation"
	@echo " [1/5] Checking Makefile governance..."
	@if grep -q "^gui: dashboard" Makefile; then \
		echo "  ✓ gui is alias to dashboard"; \
	else \
		echo "  ✗ gui not properly aliased"; exit 1; \
	fi
	@if make help 2>/dev/null | grep -q "^  make gui"; then \
		echo "  ✗ gui appears in help"; exit 1; \
	else \
		echo "  ✓ gui not advertised in help"; \
	fi
	@echo " [2/5] Checking Season Context SSOT..."
	@if [ -f "src/FishBroWFS_V2/core/season_context.py" ]; then \
		echo "  ✓ season_context.py exists"; \
	else \
		echo "  ✗ season_context.py missing"; exit 1; \
	fi
	@echo " [3/5] Checking UI Actions Service..."
	@if [ -f "src/FishBroWFS_V2/gui/services/actions.py" ]; then \
		echo "  ✓ actions.py exists"; \
	else \
		echo "  ✗ actions.py missing"; exit 1; \
	fi
	@if [ -f "src/FishBroWFS_V2/gui/services/audit_log.py" ]; then \
		echo "  ✓ audit_log.py exists"; \
	else \
		echo "  ✗ audit_log.py missing"; exit 1; \
	fi
	@echo " [4/5] Checking UI wiring (Candidates → Portfolio)..."
	@if [ -f "src/FishBroWFS_V2/gui/nicegui/pages/candidates.py" ]; then \
		if grep -q "Generate Research" src/FishBroWFS_V2/gui/nicegui/pages/candidates.py; then \
			echo "  ✓ candidates.py has Generate Research button"; \
		else \
			echo "  ✗ candidates.py missing Generate Research button"; exit 1; \
		fi; \
	else \
		echo "  ✗ candidates.py missing"; exit 1; \
	fi
	@if [ -f "src/FishBroWFS_V2/gui/nicegui/pages/portfolio.py" ]; then \
		if grep -q "Build Portfolio" src/FishBroWFS_V2/gui/nicegui/pages/portfolio.py; then \
			echo "  ✓ portfolio.py has Build Portfolio button"; \
		else \
			echo "  ✗ portfolio.py missing Build Portfolio button"; exit 1; \
		fi; \
	else \
		echo "  ✗ portfolio.py missing"; exit 1; \
	fi
	@echo " [5/5] Checking History/Run Detail enhancements..."
	@if [ -f "src/FishBroWFS_V2/gui/nicegui/pages/run_detail.py" ]; then \
		echo "  ✓ run_detail.py exists"; \
	else \
		echo "  ✗ run_detail.py missing"; exit 1; \
	fi
	@if [ -f "src/FishBroWFS_V2/gui/nicegui/pages/history.py" ]; then \
		if grep -q "Audit Trail" src/FishBroWFS_V2/gui/nicegui/pages/history.py; then \
			echo "  ✓ history.py has Audit Trail section"; \
		else \
			echo "  ✗ history.py missing Audit Trail section"; exit 1; \
		fi; \
	else \
		echo "  ✗ history.py missing"; exit 1; \
	fi
	@echo ""
	@echo "==> Phase 4 validation PASSED"
	@echo " - Makefile governance: gui→dashboard alias, clean help"
	@echo " - Season Context SSOT: single source of truth for season"
	@echo " - UI Actions Service: actions.py + audit_log.py"
	@echo " - UI wiring: Candidates → Portfolio buttons"
	@echo " - History/Run Detail: Audit trail + enhanced governance"
	@echo ""
	@echo "Next steps:"
	@echo " 1. Run 'make dashboard' to start UI"
	@echo " 2. Navigate to /candidates → Generate Research"
	@echo " 3. Navigate to /portfolio → Build Portfolio"
	@echo " 4. Navigate to /history → View audit trail"
	@echo " 5. Check outputs/seasons/2026Q1/governance/ui_audit.jsonl"

# ---------------------------------------------------------
# Phase 5: Deterministic Governance & Reproducibility Lock
# ---------------------------------------------------------
phase5:
	@echo "==> Phase 5: Deterministic Governance & Reproducibility Lock validation"
	@echo " [1/6] Checking Season Freeze (治理鎖)..."
	@if [ -f "src/FishBroWFS_V2/core/season_state.py" ]; then \
		echo "  ✓ season_state.py exists"; \
	else \
		echo "  ✗ season_state.py missing"; exit 1; \
	fi
	@if grep -q "class SeasonState" src/FishBroWFS_V2/core/season_state.py; then \
		echo "  ✓ SeasonState class defined"; \
	else \
		echo "  ✗ SeasonState class missing"; exit 1; \
	fi
	@if grep -q "def freeze_season" src/FishBroWFS_V2/core/season_state.py; then \
		echo "  ✓ freeze_season function exists"; \
	else \
		echo "  ✗ freeze_season function missing"; exit 1; \
	fi
	@echo " [2/6] Checking UI/CLI freeze state respect..."
	@if [ -f "src/FishBroWFS_V2/gui/services/actions.py" ]; then \
		if grep -q "check_season_not_frozen" src/FishBroWFS_V2/gui/services/actions.py; then \
			echo "  ✓ actions.py checks season freeze state"; \
		else \
			echo "  ✗ actions.py missing freeze check"; exit 1; \
		fi; \
	else \
		echo "  ✗ actions.py missing"; exit 1; \
	fi
	@if [ -f "scripts/generate_research.py" ]; then \
		if grep -q "check_season_not_frozen\|load_season_state" scripts/generate_research.py; then \
			echo "  ✓ generate_research.py respects freeze state"; \
		else \
			echo "  ✗ generate_research.py missing freeze check"; exit 1; \
		fi; \
	else \
		echo "  ✗ generate_research.py missing"; exit 1; \
	fi
	@if [ -f "scripts/build_portfolio_from_research.py" ]; then \
		if grep -q "check_season_not_frozen\|load_season_state" scripts/build_portfolio_from_research.py; then \
			echo "  ✓ build_portfolio_from_research.py respects freeze state"; \
		else \
			echo "  ✗ build_portfolio_from_research.py missing freeze check"; exit 1; \
		fi; \
	else \
		echo "  ✗ build_portfolio_from_research.py missing"; exit 1; \
	fi
	@echo " [3/6] Checking Deterministic Snapshot (可重現封印)..."
	@if [ -f "src/FishBroWFS_V2/core/snapshot.py" ]; then \
		echo "  ✓ snapshot.py exists"; \
	else \
		echo "  ✗ snapshot.py missing"; exit 1; \
	fi
	@if grep -q "def create_freeze_snapshot" src/FishBroWFS_V2/core/snapshot.py; then \
		echo "  ✓ create_freeze_snapshot function exists"; \
	else \
		echo "  ✗ create_freeze_snapshot function missing"; exit 1; \
	fi
	@if grep -q "def verify_snapshot_integrity" src/FishBroWFS_V2/core/snapshot.py; then \
		echo "  ✓ verify_snapshot_integrity function exists"; \
	else \
		echo "  ✗ verify_snapshot_integrity function missing"; exit 1; \
	fi
	@echo " [4/6] Checking Artifact Diff Guard (防偷改)..."
	@if [ -f "scripts/verify_season_integrity.py" ]; then \
		echo "  ✓ verify_season_integrity.py exists"; \
	else \
		echo "  ✗ verify_season_integrity.py missing"; exit 1; \
	fi
	@if [ -f "src/FishBroWFS_V2/gui/services/archive.py" ]; then \
		if grep -q "load_season_state" src/FishBroWFS_V2/gui/services/archive.py; then \
			echo "  ✓ archive.py checks freeze state"; \
		else \
			echo "  ✗ archive.py missing freeze check"; exit 1; \
		fi; \
	else \
		echo "  ✗ archive.py missing"; exit 1; \
	fi
	@echo " [5/6] Checking UI History upgrade (治理真相頁)..."
	@if [ -f "src/FishBroWFS_V2/gui/nicegui/pages/history.py" ]; then \
		if grep -q "Season Frozen" src/FishBroWFS_V2/gui/nicegui/pages/history.py; then \
			echo "  ✓ history.py shows freeze status"; \
		else \
			echo "  ✗ history.py missing freeze status display"; exit 1; \
		fi; \
		if grep -q "Check Integrity" src/FishBroWFS_V2/gui/nicegui/pages/history.py; then \
			echo "  ✓ history.py has integrity check button"; \
		else \
			echo "  ✗ history.py missing integrity check button"; exit 1; \
		fi; \
	else \
		echo "  ✗ history.py missing"; exit 1; \
	fi
	@echo " [6/6] Testing freeze/snapshot functionality..."
	@echo "  Running test_freeze_snapshot.py..."
	@PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_freeze_snapshot.py > /tmp/phase5_test.log 2>&1 || { echo "  ✗ Freeze snapshot test failed"; cat /tmp/phase5_test.log; exit 1; }
	@echo "  ✓ Freeze snapshot test passed"
	@echo ""
	@echo "==> Phase 5 validation PASSED"
	@echo " - Season Freeze (治理鎖): season_state.py with freeze/unfreeze"
	@echo " - UI/CLI freeze respect: actions.py + CLI scripts block on frozen"
	@echo " - Deterministic Snapshot: snapshot.py creates freeze_snapshot.json"
	@echo " - Artifact Diff Guard: verify_season_integrity.py detects changes"
	@echo " - UI History upgrade: History page shows freeze status + integrity check"
	@echo " - Functional test: freeze/unfreeze + snapshot creation works"
	@echo ""
	@echo "Next steps:"
	@echo " 1. Run 'make dashboard' to start UI"
	@echo " 2. Navigate to /history → Check freeze status"
	@echo " 3. Test freeze: python3 -c \"from FishBroWFS_V2.core.season_state import freeze_season; freeze_season('2026Q1', by='cli', reason='test')\""
	@echo " 4. Verify UI actions are blocked on frozen season"
	@echo " 5. Check integrity: python3 scripts/verify_season_integrity.py --season 2026Q1"
	@echo " 6. Unfreeze: python3 -c \"from FishBroWFS_V2.core.season_state import unfreeze_season; unfreeze_season('2026Q1', by='cli')\""
