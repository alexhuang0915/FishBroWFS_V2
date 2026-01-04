# Supervisor V1 Plan (Locked)

## Overview
Process-based Supervisor v1 implements a plugin registry system for all job types, with Qt Desktop UI as the only UI. The system enforces PYTEST LOCKDOWN (make check → 0 failures).

## Architecture

### Core Components
1. **JobSpec + Handler Registry Plugin Model** - Pydantic models with plugin registration
2. **SQLite DB jobs_v2.db** - Stored under `outputs/` (not repo root) for hygiene
3. **Worker Process Bootstrap** - Isolated worker processes with heartbeat monitoring
4. **Supervisor Loop** - Fetches queued jobs, spawns workers, reaps exits, orphan detection
5. **Atomic DB Transactions** - Every state transition uses explicit `BEGIN IMMEDIATE`

### Key Design Decisions
- **Single Source of Truth**: Supervisor is SSOT for final job states
- **Worker Constraints**: Workers cannot mutate job state directly except via constrained DB APIs
- **Plugin Registry**: All job types must register handlers under `src/control/supervisor/handlers/`
- **No Root Files**: DB stored under `outputs/`, no new files in repo root

## Implementation Status (Phase 1 Complete)

### Files Created
```
src/control/supervisor/
├── __init__.py              # Main module with handler registration
├── models.py                # Pydantic models + constants
├── job_handler.py           # Handler registry + base classes
├── db.py                    # SQLite v2 with atomic transactions
├── bootstrap.py             # Worker process entry point
├── supervisor.py            # Main supervisor loop
├── cli.py                   # CLI for submit/list/abort
└── handlers/
    ├── __init__.py
    └── ping.py              # PING handler for testing
```

### Test Files
```
tests/control/
├── test_supervisor_db_contract_v1.py
├── test_supervisor_ping_contract_v1.py
├── test_supervisor_heartbeat_timeout_v1.py
├── test_supervisor_abort_contract_v1.py
└── test_supervisor_unknown_job_type_v1.py
```

## How to Use

### 1. Submit a PING Job
```bash
# Using CLI
python -m src.control.supervisor.cli submit \
  --job-type PING \
  --params-json '{"sleep_sec": 1}'

# Programmatically
from src.control.supervisor.db import SupervisorDB
from src.control.supervisor.models import JobSpec

db = SupervisorDB(Path("outputs/jobs_v2.db"))
spec = JobSpec(job_type="PING", params={"sleep_sec": 1})
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

### 3. Monitor Jobs
```bash
# List jobs
python -m src.control.supervisor.cli list --state RUNNING

# Abort a job
python -m src.control.supervisor.cli abort --job-id <job_id>
```

## Abort/Timeout Mechanism

### Abort Flow
1. User calls `request_abort(job_id)` → sets `abort_requested=1` flag
2. Worker periodically checks `ctx.is_abort_requested()` during execution
3. If abort requested, worker raises `KeyboardInterrupt` or returns early
4. Supervisor marks job as `ABORTED` (or `FAILED` with "user_abort" reason)

### Heartbeat Timeout
- **Heartbeat Interval**: 2.0 seconds (configurable)
- **Timeout**: 10.0 seconds (configurable)
- **Orphan Detection**: Jobs with stale heartbeat > timeout marked `ORPHANED`
- **Grace Period**: 2.0 seconds after orphan before marking `FAILED`

### Kill Policy
1. First `SIGTERM` (graceful shutdown)
2. Wait 1 second
3. Escalate to `SIGKILL` if still running

## Database Schema (jobs_v2.db)

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

## Testing Philosophy
- **PYTEST LOCKDOWN**: All tests must pass with 0 failures
- **Deterministic Tests**: No `time.sleep()` except ultra-short (0.01s) if unavoidable
- **Mock Time**: Use monkeypatch of DB "now()" helper
- **Atomic Verification**: Each DB operation tested for transaction safety

## Next Steps (Phase 2)
1. **Migrate Real Jobs**: Implement handlers for existing job types (clean_cache, build_data, etc.)
2. **Strangler Pattern**: Keep legacy targets as `*-legacy` during migration
3. **Artifact Compatibility**: Preserve existing artifact formats
4. **Makefile Integration**: Update targets to route to supervisor CLI

## Evidence
- Phase 0 baseline: `outputs/_dp_evidence/phase0_*.txt`
- Phase 1 test results: `outputs/_dp_evidence/phase1_pytest_supervisor.txt`
- Final verification: `outputs/_dp_evidence/phase1_make_check.txt`

## Compliance
- ✅ No new files in repo root
- ✅ DB under `outputs/` only
- ✅ Qt UI remains unchanged (Phase 4 integration pending)
- ✅ Engine/research core untouched (black box)
- ✅ All Phase 1 tests pass (after fixes)