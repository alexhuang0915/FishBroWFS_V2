# Final Acceptance Harness

One-click end-to-end acceptance test for FishBroWFS_V2, producing a complete auditable evidence bundle.

## Purpose

This harness validates the entire system from scratch, ensuring:

1. **Engineering Gate**: `make check` passes with 0 failures
2. **Repo Hygiene**: No unexpected files in root, clean git status
3. **Supervisor/API Gate**: Supervisor starts on 127.0.0.1:8000 (or uses existing), `/health` responds
4. **Security Gate**: Path traversal protection (403) and missing file handling (404) for job and portfolio artifacts
5. **Functional Smoke**: API endpoints return data, job submission works, polling reaches terminal status
6. **Outputs Summary**: `/api/v1/outputs/summary` returns version 1.0

## Files

- `run_final_acceptance.sh` - Main shell script (WSL zsh compatible)
- `final_acceptance_probe.py` - Python probe (stdlib only)
- `README.md` - This file

## Usage

```bash
zsh scripts/acceptance/run_final_acceptance.sh
```

### Exit Codes
- `0`: PASS (all gates passed)
- `2`: FAIL (any gate failed)

### Output
- Prints compact PASS/FAIL summary at the end
- Prints evidence directory path
- All evidence written to `outputs/_dp_evidence/final_acceptance/<timestamp>/`

## Evidence Bundle

The harness creates the following evidence files:

```
00_env.txt                    # System environment (uname, python, git, etc.)
01_git_status.txt             # git status --porcelain=v1
02_root_ls.txt                # ls -la at repo root
03_make_check.txt             # Output of `make check`
04_supervisor_status.txt      # Supervisor status (using existing or started)
05_health.txt                 # Raw /health response
06_openapi_snapshot_diff.txt  # git diff of OpenAPI snapshot
07_registry_endpoints.json    # Combined registry endpoints (strategies, instruments, datasets)
08_outputs_summary.json       # Outputs summary response
09_security_job_artifacts.txt # Job artifacts security test results
10_security_portfolio_artifacts.txt # Portfolio artifacts security test results
11_job_submit_response.json   # Smoke job submission response
12_job_poll_log.txt           # Job polling log with timestamps
13_job_artifacts_index.json   # Artifacts index for the smoke job
14_strategy_report_v1.json    # Strategy report (if available) or note file
80_manual_ui_checklist.md     # Manual UI verification checklist (informational)
99_final_summary.md           # Final summary with gate results
supervisor_stdout.log         # Supervisor stdout/stderr (if started)
supervisor_pid.txt            # Supervisor PID (if started)
```

## Hard Invariants

1. **No repo-root files**: Absolutely NO new files in repo root
2. **All new files** MUST be created only in:
   - `scripts/acceptance/`
   - `outputs/_dp_evidence/final_acceptance/**`
3. **Desktop UI dumb client invariant unchanged**: Script does not modify UI logic
4. **Do NOT change outputs directory contracts**: Read-only probes only
5. **Script must never delete anything under outputs/**: Read-only probes only
6. **If port 8000 is already occupied**:
   - Detect it
   - DO NOT kill processes
   - Proceed by using the existing Supervisor if `/health` is OK
   - Otherwise FAIL with clear message and evidence
7. **Use stdlib only for Python helper**: No new dependencies

## Implementation Details

### Shell Script (`run_final_acceptance.sh`)
- Sets strict shell options: `set -euo pipefail`
- Determines project root robustly
- Creates evidence directory with UTC timestamp
- Captures environment information
- Runs `make check` and fails if any test failures
- Starts Supervisor if not already running (with health polling)
- Calls Python probe
- Cleans up Supervisor if it was started
- Writes final summary

### Python Probe (`final_acceptance_probe.py`)
- Performs API validation using stdlib only (`urllib.request`)
- Checks OpenAPI snapshot diff via `git diff`
- Validates registry endpoints are non-empty
- Tests security gates (path traversal, missing files)
- Submits a minimal smoke job using discovered strategies/datasets
- Polls job until terminal status (up to 120 seconds)
- Fetches artifacts index and optional strategy report
- Writes manual UI checklist (informational)
- Generates final summary with gate results

## Testing

The harness itself should be tested by running it in a clean environment. Ensure:

1. `make check` passes before running the harness
2. No Supervisor is running on port 8000 (or it's healthy)
3. Sufficient system resources for a smoke job

## Integration with CI

This harness is designed to be run as the final acceptance step before release. It can be integrated into CI pipelines to provide auditable evidence of system readiness.

## Commit

Single commit message:
```
Add one-click final acceptance harness (scripts/acceptance)