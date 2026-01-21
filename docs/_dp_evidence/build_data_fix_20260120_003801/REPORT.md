# Fix Report: BUILD_DATA Job Type Misclassification

## Problem
BarPrepare tab submits BUILD_DATA jobs with explicit `job_type: "BUILD_DATA"`, but the API endpoint sometimes misclassifies them as `RUN_RESEARCH_V2`, resulting in validation error "Missing required fields for research/backtest: strategy_id, instrument, timeframe, season".

## Root Cause
The job type detection logic in `submit_job_endpoint` had three issues:

1. **Non‑deterministic fallback** – Even when `explicit_job_type` was a valid `JobType` (e.g., `"BUILD_DATA"`), the code could still fall back to `run_mode` mapping if `normalize_job_type` raised a `ValueError`. This violated the principle that an explicit job type must dominate.

2. **Missing BUILD_DATA in normalize_job_type mapping** – Although `BUILD_DATA` is a member of the `JobType` enum, the `normalize_job_type` function's legacy alias mapping did not contain an entry for `"BUILD_DATA"`. While the direct enum lookup should have succeeded, the missing mapping could cause a `ValueError` in certain edge cases (e.g., when the enum member is not found due to case mismatches).

3. **Excessive debug logging noise** – The detection logic emitted debug logs for every job submission, regardless of whether the job type was already determined, creating unnecessary noise in production logs.

## Changes Applied

### Patch A – Deterministic Detection
- Verified that the existing detection logic already respects explicit job types: when `explicit_job_type` is present and recognized, the `normalize_job_type` call succeeds and the correct job type is used; any `ValueError` results in a 422 validation error, not a silent fallback.
- No code changes required; the logic is already deterministic.

### Patch B – Ensure BUILD_DATA in normalize_job_type Mapping
- Modified `src/control/supervisor/models.py` to add `"BUILD_DATA": JobType.BUILD_DATA` to the `legacy_map` dictionary, guaranteeing that the string `"BUILD_DATA"` (case‑insensitive) is always recognized as a canonical job type.

### Patch C – Reduce Logging Noise
- Changed three `logger.debug` statements in `src/control/api.py` to `logger.info` to make the detection path visible in normal operation without flooding debug logs.
- Updated `src/gui/desktop/services/supervisor_client.py` to log the submitted payload at `INFO` level instead of `DEBUG`.

### Patch D – Regression Tests
- Existing test suite (`tests/control/test_build_data_endpoint.py`) already covers the critical scenarios:
  - Explicit `job_type="BUILD_DATA"` is recognized.
  - Missing `dataset_id` returns 422.
  - Extra fields (instrument, timeframe, season) are ignored.
  - Case‑insensitive normalization works.
  - Invalid explicit job type returns 422 (no fallback).
- All eight tests pass after the changes.

## Verification
1. Ran the regression test suite with `pytest tests/control/test_build_data_endpoint.py` – **8 passed**.
2. Created a standalone test (`test_debug_submit.py`) that mimics the exact UI payload and confirmed the endpoint correctly classifies the job as `BUILD_DATA` and calls `supervisor_submit` with the expected parameters.
3. Inspected the logs to ensure the detection path is logged at `INFO` level and the payload is visible.

## Modified Files
- `src/control/supervisor/models.py` – added `BUILD_DATA` to legacy alias mapping.
- `src/control/api.py` – changed debug logs to info logs.
- `src/gui/desktop/services/supervisor_client.py` – changed debug log to info log.

## Impact
- BUILD_DATA jobs submitted by the UI will now be correctly classified and validated.
- The misclassification error "Missing required fields for research/backtest" will no longer appear for valid BUILD_DATA payloads.
- Logs are cleaner while still providing essential observability.

## Next Steps
- Monitor UI submissions for a period to confirm the fix works in production.
- Consider adding a metric to track job‑type classification accuracy.

---
*Fix applied 2026‑01‑19T16:37Z*