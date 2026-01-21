# Phase P0+P1 Stack Startup & Readiness Endpoint Fix

**Date**: 2026-01-12  
**Commit**: $(git rev-parse HEAD)  
**Environment**: Python 3.12.3, Linux 6.6

## Overview

This phase addresses two proven bugs:

1. **P0 (Stack startup)**: The stack startup script (`scripts/run_stack.py`) was using the legacy worker loop with `jobs.db` instead of the supervisor with `jobs_v2.db`.
2. **P1 (Readiness endpoint)**: Missing readiness endpoint for UI gates (`/api/v1/readiness`).

## Changes Made

### 1. P0: Stack Startup Fix (`scripts/run_stack.py`)

- **Before**: `spawn_worker()` started `control.worker_main` with `jobs.db`.
- **After**: `spawn_worker()` now starts `control.supervisor.supervisor` with `jobs_v2.db`.
- **Configuration**: Added environment variables `FISHBRO_SUPERVISOR_MAX_WORKERS` and `FISHBRO_SUPERVISOR_TICK_INTERVAL` with defaults.
- **Process detection**: Updated `is_fishbro_process()` to include `"control.supervisor.supervisor"` and removed `"control.worker_main"`.
- **Evidence**: See `rg_before.txt` for discovery and diff.

### 2. P1: Readiness Endpoint (`src/control/api.py`)

- **Added**: New endpoint `@api_v1.get("/readiness")` returning `{"status":"ok"}`.
- **Location**: Placed after `/api/v1/identity` endpoint (line 492-495).
- **Contract**: Simple GET returning HTTP 200 with JSON object.
- **OpenAPI snapshot**: Updated `tests/policy/api_contract/openapi.json` to include the new endpoint.

### 3. Verification & Cleanup

- **Stray worker process**: Killed PID 138163 (legacy worker) and removed leftover files `outputs/worker.heartbeat` and `outputs/worker.pid`.
- **Hardening test**: Fixed `test_outputs_guard` failure due to stray files.
- **API contract test**: Updated snapshot to match new endpoint.

## Test Results

- **`make check` final run**: **1292 passed**, 36 skipped, 3 deselected, 11 xfailed, 0 failures.
- **Hardening tests**: 33 passed, 1 skipped.
- **API contract test**: Passed (endpoint present in snapshot).
- **Root hygiene**: No new files in repo root; all evidence stored under `outputs/_dp_evidence/`.

## Evidence Files

- `00_env_snapshot.txt` – git status, HEAD, Python version, pip freeze
- `01_root_ls.txt` – root directory listing
- `rg_before.txt` – discovery ripgrep outputs
- `make_check.txt` – initial test run (with failures)
- `test_outputs_guard.txt` – hardening test output
- `make_check_final.txt` – test run after fixing stray worker
- `make_check_final2.txt` – final test run after API snapshot update (all green)
- `REPORT.md` – this summary

## Known Issues

None. The fixes are complete and all tests pass.

## Acceptance Criteria Met

- [x] Stack startup uses supervisor and `jobs_v2.db`
- [x] Readiness endpoint `/api/v1/readiness` returns `{"status":"ok"}`
- [x] No stray worker processes or leftover files
- [x] All tests pass (`make check` zero failures)
- [x] No new repo root files
- [x] Evidence bundle complete under `outputs/_dp_evidence/phase_p0p1_stack_gate/`

## Next Steps

The system is now ready for UI gates to poll the readiness endpoint, and the supervisor loop is the single source of truth for job processing.