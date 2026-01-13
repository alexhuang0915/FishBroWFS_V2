# Phase P0.2: Abort Enforcement + P0.3 ErrorDetails Observability

**Date**: 2026-01-12  
**Commit**: b4e9cabc64d8b7a2b04bbc379f458fe1c05c71c1  
**Environment**: Python 3.12.3, Linux 6.6

## Overview

This phase implements two constitutional fixes end‑to‑end:

1. **P0.2 – Abort Enforcement**: Abort requests must reliably stop jobs (QUEUED or RUNNING) by supervisor authority (SIGTERM → SIGKILL) and produce deterministic final state.
2. **P0.3 – ErrorDetails Observability**: Every FAILED/ABORTED job must expose structured error details via DB + API so UI can display “why” without digging artifacts.

The implementation is termination‑safe, SSOT‑safe, and test‑enforced.

## Changes Made

### 1. Database Schema Migration (`src/control/supervisor/db.py`)

- Added `error_details` column (TEXT, nullable) to the `jobs` table via idempotent migration.
- Migration checks existing columns with `PRAGMA table_info(jobs)` and adds the column only if missing.
- No data loss; existing rows keep `NULL`.

### 2. DB Write API with Structured Error Details (`src/control/supervisor/db.py`)

- Updated `mark_failed(job_id, reason, *, error_details=None)` to accept a structured dict.
- Updated `mark_aborted(job_id, reason, *, error_details=None)` with same pattern.
- Updated `mark_orphaned` similarly.
- Default error details are generated when `error_details` is `None`:
  - `mark_failed`: `{"type":"ExecutionError","msg":reason,"timestamp":...,"phase":"bootstrap"}`
  - `mark_aborted`: `{"type":"AbortRequested","msg":reason,"timestamp":...,"phase":"supervisor"}`
- If a worker PID exists and not already present, it is automatically added to the details.

### 3. Bootstrap Integration (`src/control/supervisor/bootstrap.py`)

- All error paths now pass structured error details matching the artifact `error.json`.
- Error types:
  - `SpecParseError` – spec parsing failure
  - `UnknownHandler` – unknown handler name
  - `ValidationError` – validation failure
  - `ExecutionError` – runtime exception (includes traceback, truncated to 16k chars)
- The `error.json` artifact is still written for backward compatibility.

### 4. Supervisor Abort Enforcement (`src/control/supervisor/supervisor.py`)

- Added a new tick step `_handle_abort_requests()` that runs before spawning new workers.
- Fetches QUEUED and RUNNING jobs with `abort_requested = 1`.
- **QUEUED jobs**: immediately transition to `ABORTED` with error details `{"type":"AbortRequested","msg":"user_abort"}`.
- **RUNNING jobs**:
  1. Send `SIGTERM` to the worker PID (or process group if `start_new_session=True`).
  2. Wait up to 5 seconds (polling with small increments to avoid blocking the tick).
  3. If still alive, send `SIGKILL`.
  4. Transition job to `ABORTED` with error details containing `pid`.
- If PID is missing or already dead, still transition to `ABORTED` with `"process_missing": true`.
- Removes the job from `self.children` after killing.

### 5. API Exposure (`src/control/api.py` and `src/contracts/api.py`)

- `/api/v1/jobs` response now includes an `error_details` field (JSON object or `null`).
- The DB column (TEXT) is parsed with `json.loads()`; invalid JSON returns a fallback error details object.
- Backward compatible – existing clients ignore the new field.
- Contract models (`JobSchema`, `JobListResponse`) updated in `src/contracts/api.py`.

### 6. New Test Suite (`tests/control/test_supervisor_abort_enforcement_v1.py`)

- **Test 1**: Abort QUEUED job → transitions to ABORTED with error details.
- **Test 2**: Abort RUNNING job (real `sleep` subprocess) → kills PID and writes error details with PID.
- **Test 3**: Abort RUNNING job with missing PID → still marks ABORTED with appropriate details.
- **Test 4**: Multiple abort requests handled in a single tick.
- **Test 5**: Abort does not affect non‑abort‑requested jobs.
- All tests use a temporary SQLite DB and clean up subprocesses.

### 7. API Contract Snapshot Update

- Ran `make api-snapshot` to regenerate the OpenAPI snapshot with the new `error_details` field.
- Verified that `make check` passes with zero failures.

## Verification Results

### Unit Tests

- `make check` passes (0 failures, 0 errors). Total 1297 passed, 36 skipped, 3 deselected, 11 xfailed.
- New abort‑enforcement tests pass (5/5).
- Existing supervisor tests (`test_supervisor_abort_contract_v1.py`, `test_supervisor_db_contract_v1.py`) still pass.

### Smoke Test

- Supervisor starts and ticks without error (no jobs in DB). No log output indicates normal operation.
- No stray processes left after test runs.

### Evidence Files

All evidence stored under `outputs/_dp_evidence/phase_p0_2_abort_error_details/`:

- `rg_discovery.txt` – initial ripgrep of abort/error‑details code
- `rg_db_schema.txt` – DB schema inspection
- `rg_after_error_details.txt` – grep after implementation
- `rg_after_abort.txt` – grep after implementation
- `test_abort_enforcement.txt` – output of new test suite
- `make_check.txt` – final `make check` output (full)
- `make_api_snapshot.txt` – output of `make api-snapshot`
- `supervisor_smoke.txt` – supervisor startup smoke test
- `commit_hash.txt` – current Git commit

## Acceptance Criteria Met

- [x] Abort requested on QUEUED → transitions to ABORTED within a supervisor tick and writes error_details.
- [x] Abort requested on RUNNING → supervisor kills PID (TERM→KILL) and transitions job to ABORTED with error_details.pid.
- [x] Any mark_failed writes structured error_details (even if caller passes only string).
- [x] /api/v1/jobs includes error_details field and it is valid JSON/null.
- [x] make check has 0 failures.
- [x] Evidence bundle exists under outputs/_dp_evidence/phase_p0_2_abort_error_details/.
- [x] No new repo root files.

## Known Issues

None. The implementation satisfies all requirements and passes all tests.

## How to Reproduce Abort Behavior

1. Start the supervisor with a clean DB:
   ```bash
   PYTHONPATH=src python3 -m control.supervisor.supervisor --db outputs/jobs_v2.db --max-workers 2 --tick-interval 0.5
   ```

2. Via the API, submit a job (e.g., `run_research`). Wait until it reaches QUEUED or RUNNING.

3. Send a `POST /api/v1/jobs/{job_id}/abort` request (or set `abort_requested=1` directly in DB).

4. Within one tick interval, the supervisor will:
   - If QUEUED: transition the job to ABORTED with error_details.
   - If RUNNING: kill the worker process and transition to ABORTED.

5. Query `/api/v1/jobs` to see the `error_details` field populated.

## Next Steps

The system now provides deterministic abort enforcement and structured error observability. UI gates can rely on the `error_details` field to display failure reasons without parsing artifact files. The supervisor loop is the single source of truth for job lifecycle management.