# SYSTEM FULL SNAPSHOT - Supervisor V1 Implementation Complete

## Phase 1: Supervisor Skeleton + New jobs_v2.db - COMPLETE ✅

### New Supervisor Files Created
```
src/control/supervisor/
├── __init__.py              # Main module with handler registration
├── models.py                # Pydantic models + constants (JobSpec, JobRow, etc.)
├── job_handler.py           # Handler registry + base classes (BaseJobHandler, JobContext)
├── db.py                    # SQLite v2 with atomic transactions (SupervisorDB)
├── bootstrap.py             # Worker process entry point with heartbeat monitoring
├── supervisor.py            # Main supervisor loop with spawn/reap/orphan detection
├── cli.py                   # CLI for submit/list/abort commands
└── handlers/
    ├── __init__.py
    └── ping.py              # PING handler for testing (sleeps, checks abort, heartbeats)
```

### Test Files Created
```
tests/control/
├── test_supervisor_db_contract_v1.py        # DB API tests (36 tests total)
├── test_supervisor_ping_contract_v1.py      # PING handler tests
├── test_supervisor_heartbeat_timeout_v1.py  # Heartbeat/orphan detection tests
├── test_supervisor_abort_contract_v1.py     # Abort mechanism tests
└── test_supervisor_unknown_job_type_v1.py   # Unknown job type handling tests
```

### Key Features Implemented

#### 1. Plugin Registry System
- **Handler Registration**: Central registry in `job_handler.py`
- **BaseJobHandler**: Abstract base class with `validate_params()` and `execute()`
- **JobContext**: Runtime context with `heartbeat()` and `is_abort_requested()`
- **PING Handler**: Reference implementation with abort detection

#### 2. Atomic Database (jobs_v2.db)
- **Location**: `outputs/jobs_v2.db` (NOT repo root)
- **Schema**: Jobs table (job_id, state, abort_requested, etc.) + Workers table
- **Transactions**: Explicit `BEGIN IMMEDIATE` for all state transitions
- **Key APIs**: `submit_job()`, `fetch_next_queued_job()`, `mark_succeeded()`, etc.

#### 3. Worker Process Bootstrap
- **Isolation**: Each job runs in separate subprocess
- **Heartbeat**: Background thread updates heartbeat every 2 seconds
- **Abort Detection**: Polls `ctx.is_abort_requested()` during execution
- **Error Handling**: Marks jobs FAILED on validation/execution errors

#### 4. Supervisor Loop
- **Spawn Workers**: Up to `max_workers` concurrent jobs
- **Reap Exited**: Monitors child processes via `poll()`
- **Orphan Detection**: Stale heartbeat > 10s → ORPHANED → kill worker
- **Kill Policy**: SIGTERM → 1s wait → SIGKILL escalation

#### 5. CLI Interface
```
# Submit PING job
python -m src.control.supervisor.cli submit \
  --job-type PING \
  --params-json '{"sleep_sec": 1}'

# List jobs
python -m src.control.supervisor.cli list --state RUNNING

# Abort job
python -m src.control.supervisor.cli abort --job-id <id>
```

## How to Submit Jobs

### 1. PING Job (Testing)
```python
from src.control.supervisor.db import SupervisorDB
from src.control.supervisor.models import JobSpec
from pathlib import Path

db = SupervisorDB(Path("outputs/jobs_v2.db"))
spec = JobSpec(job_type="PING", params={"sleep_sec": 1.0})
job_id = db.submit_job(spec)
```

### 2. Run Supervisor
```bash
# Start supervisor (default: 4 workers, 1s tick interval)
python -m src.control.supervisor.supervisor \
  --db outputs/jobs_v2.db \
  --max-workers 4 \
  --tick-interval 1.0
```

## Abort/Timeout Mechanism

### Abort Flow
1. **Request**: `db.request_abort(job_id)` sets `abort_requested=1` flag
2. **Detection**: Worker polls `ctx.is_abort_requested()` during execution
3. **Response**: PING handler returns `{"aborted": True, ...}` result
4. **State**: Bootstrap calls `db.mark_aborted(job_id, "user_abort")`

### Heartbeat Timeout
- **Interval**: 2.0 seconds (HEARTBEAT_INTERVAL_SEC)
- **Timeout**: 10.0 seconds (HEARTBEAT_TIMEOUT_SEC)
- **Orphan**: Stale heartbeat > timeout → ORPHANED state
- **Grace**: 2.0 seconds (REAP_GRACE_SEC) before marking FAILED

### Kill Policy
1. **SIGTERM** (graceful shutdown)
2. Wait 1 second
3. **SIGKILL** (force kill if still running)

## Database Schema

### Jobs Table
```sql
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    state TEXT NOT NULL,  -- QUEUED,RUNNING,SUCCEEDED,FAILED,ABORTED,ORPHANED
    state_reason TEXT DEFAULT '',
    result_json TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    worker_id TEXT NULL,
    worker_pid INTEGER NULL,
    last_heartbeat TEXT NULL,
    abort_requested INTEGER DEFAULT 0,
    progress REAL NULL,
    phase TEXT NULL
)
```

### Workers Table
```sql
CREATE TABLE workers (
    worker_id TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,
    current_job_id TEXT NULL,
    status TEXT NOT NULL DEFAULT 'IDLE',  -- IDLE,BUSY,EXITED
    spawned_at TEXT NOT NULL,
    exited_at TEXT NULL
)
```

## Testing Results

### Phase 0 Baseline
- **make check**: 1251 passed, 0 failures (baseline established)
- **Evidence**: `outputs/_dp_evidence/phase0_*.txt`

### Phase 1 Supervisor Tests
- **All 36 tests PASS**: `tests/control/test_supervisor_*_v1.py`
- **Key fixes applied**:
  1. `fetch_next_queued_job()` filters out abort-requested jobs
  2. Bootstrap prints errors to stderr for unknown job types
  3. Abort detection properly marks jobs ABORTED (not SUCCEEDED)
  4. PYTHONPATH set for subprocess calls

### Final Verification
- **make check**: 1287 passed, 20 skipped, 10 xfailed, 0 failures ✅
- **Evidence**: `outputs/_dp_evidence/final_make_check_supervisor.txt`

## Compliance with Requirements

### ✅ Absolute Rules Met
1. **No root files**: DB stored under `outputs/` only
2. **Allowed directories**: All files under `src/control/supervisor/`, `tests/control/`, `docs/_dp_notes/`
3. **Engine/research core untouched**: No modifications to `src/engine/**`
4. **Qt UI preserved**: No changes to Qt Desktop UI (Phase 4 integration pending)
5. **No web UI**: NiceGUI already removed, not reintroduced

### ✅ Technical Requirements
1. **Atomic DB transactions**: Every state change uses `BEGIN IMMEDIATE`
2. **Worker constraints**: Workers cannot mutate job state directly (only via DB APIs)
3. **Supervisor SSOT**: Supervisor is single source of truth for final states
4. **Plugin registry**: All job types via handler registration
5. **PYTEST LOCKDOWN**: All tests pass with 0 failures

## Phase 2: Real Job Migration (CLEAN_CACHE, BUILD_DATA, GENERATE_REPORTS) - COMPLETE ✅

### New Handler Files Created
```
src/control/supervisor/handlers/
├── clean_cache.py        # CLEAN_CACHE handler with scope: all/season/dataset
├── build_data.py         # BUILD_DATA handler for data preparation
└── generate_reports.py   # GENERATE_REPORTS handler for canonical results
```

### Test Files Created
```
tests/control/
├── test_supervisor_handler_clean_cache_v1.py      # 4 tests
├── test_supervisor_handler_build_data_v1.py       # 5 tests
└── test_supervisor_handler_generate_reports_v1.py # 7 tests
```

### Makefile Targets Added (Strangler Pattern)
```
# Supervisor targets (Phase 2 migration)
make clean-cache           # Routes to supervisor submit CLEAN_CACHE
make clean-cache-legacy    # Preserved old behavior
make clean-caches          # Alias for clean-cache
make clean-caches-dry      # Dry-run cache cleaning

make build-data            # Routes to supervisor submit BUILD_DATA (requires params)
make build-data-legacy     # Preserved old behavior

make generate-reports      # Routes to supervisor submit GENERATE_REPORTS
make generate-reports-legacy # Preserved old behavior
```

### Handler Contracts

#### CLEAN_CACHE Handler
- **Job type**: `CLEAN_CACHE`
- **Parameters**:
  - `scope`: "all" | "season" | "dataset" (required)
  - `season`: str (required when scope="season")
  - `dataset_id`: str (required when scope="dataset")
  - `dry_run`: bool (default False)
- **Behavior**: Calls legacy cleanup logic via `CleanupService` or fallback file deletion
- **Output**: Returns deleted count, stdout/stderr artifacts
- **Safety**: Always use `dry_run=True` in tests

#### BUILD_DATA Handler
- **Job type**: `BUILD_DATA`
- **Parameters**:
  - `dataset_id`: str (required)
  - `timeframe_min`: int (default 60)
  - `force_rebuild`: bool (default False)
  - `mode`: "BARS_ONLY" | "FEATURES_ONLY" | "FULL" (default "FULL")
- **Behavior**: Calls `prepare_with_data2_enforcement()` or CLI fallback
- **Output**: Returns produced paths, stdout/stderr artifacts

#### GENERATE_REPORTS Handler
- **Job type**: `GENERATE_REPORTS`
- **Parameters**:
  - `outputs_root`: str (default "outputs")
  - `season`: str (optional)
  - `strict`: bool (default True)
- **Behavior**: Calls `scripts/generate_research.py` via subprocess
- **Output**: Returns report paths (canonical_results.json, research_index.json)

### Legacy Mapping (from MIGRATION_MAP.md)
- **CLEAN_CACHE**: Legacy target `clean-cache` in Makefile, actual implementation in `src/gui/desktop/services/cleanup_service.py`
- **BUILD_DATA**: Legacy target `build-data` in Makefile, actual implementation via `prepare_with_data2_enforcement()` in `src/control/prepare_orchestration.py`
- **GENERATE_REPORTS**: Legacy target `generate-reports` in Makefile, actual implementation via `scripts/generate_research.py`

### Testing Results
- **Handler tests**: 16 tests passed (4 + 5 + 7)
- **make check**: 1303 passed, 20 skipped, 10 xfailed, 0 failures ✅
- **Evidence files**:
  - `outputs/_dp_evidence/phase2_step0_make_check_before.txt` - Baseline before changes
  - `outputs/_dp_evidence/phase2_step0_entrypoints_before_rg.txt` - Entrypoint inventory
  - `outputs/_dp_evidence/phase2_step1_*_rg.txt` - Legacy implementation discovery
  - `outputs/_dp_evidence/phase2_step5_pytest_handlers.txt` - Handler test results
  - `outputs/_dp_evidence/phase2_step5_make_check_after.txt` - Final make check
  - `outputs/_dp_evidence/phase2_step5_makefile_legacy_targets_rg.txt` - Legacy target verification

### Known Limitations / Deferrals
- **RUN_RESEARCH / RUN_PLATEAU**: NOT migrated in Phase 2 (deferred to later phase)
- **BUILD_DATA parameter mapping**: Some parameters may need adjustment for full compatibility
- **CLEAN_CACHE "all" scope**: Simplified implementation; may need enhancement for production

## Next Steps (Phase 3+)

### Phase 3 - Remove Old Worker System
1. **Identify obsolete code**: `src/control/worker*.py`, `scripts/kill_stray_workers.py`
2. **Delete after verification**: Ensure supervisor handles all job types
3. **Update docs**: Remove references to old worker system

### Phase 4 - Qt UI Wiring
1. **Thin API layer**: `src/control/supervisor/__init__.py` with `submit()`, `list()`, `abort()`
2. **Qt integration**: Update UI to call supervisor API instead of spawning processes directly
3. **Preserve UI visuals**: Keep existing Qt interface unchanged

## Evidence Files Created
- `outputs/_dp_evidence/phase0_make_check.txt` - Baseline test results
- `outputs/_dp_evidence/phase0_entrypoints_rg.txt` - Job entrypoints inventory
- `outputs/_dp_evidence/phase0_jobsdb_rg.txt` - Existing DB usage inventory
- `outputs/_dp_evidence/phase1_pytest_supervisor.txt` - Initial Phase 1 test results
- `outputs/_dp_evidence/phase1_pytest_supervisor_fixed.txt` - Fixed Phase 1 test results
- `outputs/_dp_evidence/phase1_make_check.txt` - Phase 1 make check results
- `outputs/_dp_evidence/final_make_check_supervisor.txt` - Final verification
- `docs/_dp_notes/SUPERVISOR_V1_PLAN_LOCKED.md` - Implementation documentation

## Conclusion
**Phase 1 COMPLETE**: Process-based Supervisor v1 successfully implemented with:
- ✅ Complete plugin registry system
- ✅ Atomic SQLite database (jobs_v2.db)
- ✅ Worker process bootstrap with heartbeat monitoring
- ✅ Supervisor loop with spawn/reap/orphan detection
- ✅ Abort/timeout mechanism
- ✅ CLI interface
- ✅ 36 passing tests
- ✅ make check with 0 failures

The system is ready for Phase 2 migration of real job entrypoints.