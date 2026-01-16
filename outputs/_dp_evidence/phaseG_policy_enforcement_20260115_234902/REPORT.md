# Phase G Report

## Summary
- Added `src/control/policy_enforcement.py` where `PolicyResult` and `PolicyEnforcementError` capture structured preflight/postflight outcomes. `supervisor.submit` invokes this check before `SupervisorDB.submit_job`, and the API/CLI surfaces errors along with the created job ID for traceability.
- Extended `SupervisorDB` schema (`failure_code`, `failure_message`, `failure_details`, `policy_stage`) and updated `submit_rejected_job`, `mark_succeeded`, and `mark_failed` so both policy violations and runtime failures persist their codes/messages. Postflight verification now checks worker-declared artifacts under `outputs/jobs/<job_id>` and fails jobs deterministically when outputs stray or go missing.
- Strengthened CLI alignment by reusing `control.supervisor.submit`, honoring `--db` via `FISHBRO_OUTPUTS_ROOT`, and routing policy rejections through `PolicyEnforcementError`. Added focused regression tests in `tests/control/test_policy_enforcement.py` to cover preflight rejection, postflight failure, and CLI enforcement.

## Tests
- `timeout 180s python3 -m pytest -q tests/control -q` → `351 passed, 7 skipped, 6 xfailed in 27.22s`
- `timeout 300s make check` → `========= 1549 passed, 49 skipped, 3 deselected, 11 xfailed in 36.94s =========`

## Enforcement highlights
- **Preflight hook:** `control.supervisor.submit()` now runs `policy_enforcement.evaluate_preflight()` and, on violation, inserts a `REJECTED` job with structured `failure_*` metadata before raising `PolicyEnforcementError`. `src/control/api.py` catches this and returns HTTP 422 / reason payload; the CLI also prints the policy code/stage.
- **Postflight verification:** `SupervisorDB.mark_succeeded()` invokes `evaluate_postflight()` before flipping a job to `SUCCEEDED`. Any missing or path-escaping outputs instead route the job through `mark_failed()` with the appropriate policy code and `policy_stage="postflight"`.
- **Reason storage:** The `jobs` table now tracks `failure_code`, `failure_message`, `failure_details`, and `policy_stage`, keeping the human- and machine-readable trace for every terminal state change.
- **Non-bypassable control plane:** CLI submission honors `--db` via `FISHBRO_OUTPUTS_ROOT`, reuses the same `submit()` path, validators, and policy checks as the HTTP API, preventing alternate entrypoints from side-stepping enforcement.

## Hygiene
- No files were accidentally created in the repo root; only `src/` and `tests/` (plus the required evidence directory) received new content.
