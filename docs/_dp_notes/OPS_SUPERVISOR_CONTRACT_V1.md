# OPS SUPERVISOR CONTRACT V1

## Overview
This document defines the operational contract for the FishBroWFS_V2 supervisor system. The supervisor provides deterministic, safe startup and shutdown of the full stack (backend, worker, GUI) with comprehensive pre-flight checks.

## Canonical Human Commands

### `make doctor`
**Purpose**: Diagnostic pre-flight checks without spawning any processes.
**Behavior**:
- Checks all required dependencies are importable
- Verifies ports 8000 (backend) and 8080 (GUI) are free or owned by fishbro processes
- Validates environment configuration
- Returns actionable error messages for any failures
- **Never spawns processes**

### `make run`
**Purpose**: Safe start of the full stack (backend + worker + GUI).
**Behavior**:
1. First runs `make doctor` internally
2. If doctor fails: stops immediately with same error code
3. If doctor passes: spawns backend, worker, and GUI in supervised manner
4. Writes child PIDs to stable location for later cleanup
5. Redirects logs to `/tmp/fishbro_{backend,worker,gui}.log`
6. On Ctrl+C: gracefully terminates all children

### `make down`
**Purpose**: Stop all fishbro processes started by `make run`.
**Behavior**:
- Kills processes identified by PID files
- Falls back to port-based cleanup (8000/8080)
- Confirms ports are freed
- Safe to run even if nothing is running

### `make status`
**Purpose**: Check health of running stack.
**Behavior**:
- Queries backend health endpoint (`http://127.0.0.1:8000/health`)
- Queries worker status endpoint (`http://127.0.0.1:8000/worker/status`)
- Queries GUI health endpoint (`http://127.0.0.1:8080/health`)
- Returns concise status summary

### `make logs`
**Purpose**: Tail logs of running processes.
**Behavior**:
- Shows last N lines from each log file
- Follow mode available via `make logs --follow`
- Log locations: `/tmp/fishbro_{backend,worker,gui}.log`

### `make ports`
**Purpose**: Show port ownership information.
**Behavior**:
- Lists processes listening on 8000 and 8080
- Shows PID, command line, and ownership (fishbro vs external)
- Helps diagnose port conflicts

### `make gui`
**Purpose**: Launch GUI only (safe version).
**Behavior**:
- Runs port check for 8080
- If free, launches GUI only
- If occupied by fishbro: offers to kill via `make down`
- If occupied by external: fails with actionable message

## Truth Table for Exit Codes

### `make doctor` Exit Codes
- **0**: All checks passed, system ready to start
- **10**: Dependency missing (e.g., psutil, requests, uvicorn, fastapi, nicegui)
- **11**: Port conflict (8000 or 8080 occupied by non-fishbro process)
- **12**: Environment misconfiguration (missing env vars, invalid paths)
- **13**: Health check failure (backend/GUI already running but unhealthy)

### `make run` Exit Codes
- **0**: Successfully started all components
- **Same as doctor**: If doctor fails, run exits with same code without spawning
- **130**: Interrupted by Ctrl+C (graceful shutdown)
- **Other**: Child process failure (propagates exit code)

## Guarantees

### Port Conflict Resolution
1. **Port 8000/8080 occupied by non-fishbro process**:
   - `make doctor` fails with exit 11
   - Message: "Port 8080 is used by PID=XXXX cmd=... Run: make down (if fishbro) or stop that program."
   - `make run` refuses to start

2. **Port 8000/8080 occupied by fishbro old process**:
   - `make doctor` detects ownership via cmdline containing repo path
   - `make down` clears the port
   - After `make down`, `make run` can proceed

### Dependency Safety
- Dependency check occurs **before** any process spawn
- Missing dependencies cause clean failure with installation instructions:
  ```
  Missing dependency: psutil
  Run: pip install -r requirements.txt
  ```
- No Python tracebacks shown to user

### Logging Guarantees
- Backend log: `/tmp/fishbro_backend.log`
- Worker log: `/tmp/fishbro_worker.log`
- GUI log: `/tmp/fishbro_gui.log`
- Logs are created on startup, appended during runtime
- Log rotation not implemented (use system logrotate if needed)

### Health Monitoring
- Backend health endpoint: `http://127.0.0.1:8000/health` (must return 200)
- Worker status endpoint: `http://127.0.0.1:8000/worker/status` (must return `{"alive": true}` within 10s of spawn)
- GUI health endpoint: `http://127.0.0.1:8080/health` (must return 200)
- `make status` uses these endpoints
- `make doctor` verifies health if processes already running

### Process Management
- Child PIDs stored in `outputs/_dp_evidence/ops_pids.json`
- Format: `{"backend": 1234, "worker": 1235, "gui": 1236}`
- `make down` reads this file for targeted termination
- Fallback to port-based cleanup if PID file missing/corrupt

## Implementation Notes

### Supervisor Script
- Located at `scripts/run_stack.py`
- Pure Python, uses psutil for process/port introspection
- No shell parsing (`lsof/ss`) for portability
- Lightweight imports (doesn't import project packages at import time)

### Environment Variables
- `FISHBRO_BACKEND_PORT`: Override default 8000
- `FISHBRO_GUI_PORT`: Override default 8080
- `FISHBRO_SUPERVISOR_FORCE_MISSING`: Test hook to simulate missing dependencies
- `PYTHONPATH=src`: Required for local package resolution
- `PYTHONDONTWRITEBYTECODE=1`: Performance optimization

### Error Messages
All error messages follow the pattern:
```
<ERROR_TYPE>: <Description>
Action: <Actionable instruction>
```

Examples:
```
PORT_CONFLICT: Port 8080 is used by PID=5678 cmd=/usr/bin/python3 -m http.server
Action: Run 'make down' (if fishbro) or stop that program.
```

```
MISSING_DEPENDENCY: psutil
Action: pip install -r requirements.txt
```

## Testing Contract

### Governance Tests
- Located in `tests/governance/test_ops_supervisor_doctor.py`
- Test dependency checking via `FISHBRO_SUPERVISOR_FORCE_MISSING`
- Test port conflict detection via ephemeral ports
- **Never spawn real processes** during tests
- Fast and deterministic

### Integration Tests
- `make check` must pass
- `FISHBRO_UI_CONTRACT=1 make ui-contract` must pass
- Full stack smoke test documented in evidence files

## Version History
- **V1 (2026-01-01)**: Initial contract with doctor/run/down/status/logs/ports commands

## Compliance
This contract is enforced by:
1. `scripts/run_stack.py` implementation
2. `Makefile` target mappings
3. `tests/governance/test_ops_supervisor_doctor.py` tests
4. `requirements.txt` dependency governance