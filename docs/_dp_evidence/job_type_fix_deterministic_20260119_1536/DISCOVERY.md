# Discovery: Deterministic Job Type Detection for BUILD_DATA

## Problem
The BarPrepare tab submits BUILD_DATA jobs with explicit `job_type: "BUILD_DATA"`, but the API endpoint sometimes misclassifies them as `RUN_RESEARCH_V2`, resulting in validation error "Missing required fields for research/backtest: strategy_id, instrument, timeframe, season".

Previous fix (2026-01-19T15:12Z) addressed UI payload fields and added logging but did not fully resolve the underlying detection logic flaw.

## Root Cause
The job type detection logic in `submit_job_endpoint` (`src/control/api.py`) uses the following decision flow:

1. Extract `explicit_job_type` from payload `job_type` field.
2. If `explicit_job_type` is present and matches a known `JobType` enum value, call `normalize_job_type` to convert to canonical `JobType`.
3. If `normalize_job_type` raises `ValueError`, catch it and fall back to mapping based on `run_mode`.
4. If `explicit_job_type` is missing, also fall back to `run_mode` mapping.

The bug had three components:

### A) Non‑deterministic fallback when explicit job_type is present
Even when `explicit_job_type` is a valid `JobType` (e.g., `"BUILD_DATA"`), the code could still fall back to `run_mode` mapping if `normalize_job_type` raised a `ValueError`. This could happen because:
- The `normalize_job_type` function did not include `BUILD_DATA` in its legacy alias mapping (though it should be recognized via direct enum lookup).
- The `ValueError` was being caught too broadly, treating any error (including potential bugs) as a reason to fall back.

This violated the principle that **an explicit job_type must dominate** – if the payload explicitly states a job type, the system must respect it and never silently fall back to a different type.

### B) Missing BUILD_DATA in normalize_job_type mapping
Although `BUILD_DATA` is a member of the `JobType` enum, the `normalize_job_type` function's legacy alias mapping did not contain an entry for `"BUILD_DATA"`. While the direct enum lookup should have succeeded, the presence of a missing mapping could cause a `ValueError` in certain edge cases (e.g., when the enum member is not found due to case mismatches). Adding `BUILD_DATA` to the mapping ensures robust recognition.

### C) Excessive debug logging noise
The detection logic emitted debug logs for every job submission, regardless of whether the job type was already determined. This created unnecessary noise in production logs and could obscure more important messages.

## Investigation Steps
1. **Locate detection code path** – traced the flow in `src/control/api.py` lines 1282‑1428.
2. **Identify SSOT definitions** – reviewed `src/control/supervisor/models.py` where `JobType` enum and `normalize_job_type` are defined.
3. **Examine existing tests** – found regression tests in `tests/control/test_build_data_endpoint.py` that already covered many scenarios but missed the deterministic rule.
4. **Verify bug reproduction** – wrote a test that confirmed explicit `job_type: "BUILD_DATA"` could still trigger the fallback path.

## Key Findings
- The condition `if explicit_job_type and explicit_job_type in [jt.value for jt in JobType]:` correctly evaluates to `True` for `"BUILD_DATA"`.
- However, the `try` block that calls `normalize_job_type` could raise `ValueError` due to a missing mapping, causing the fallback.
- The fallback mapping uses `run_mode` (empty string for BUILD_DATA payloads) and defaults to `RUN_RESEARCH_V2`, leading to the observed error.

## Impact
- BUILD_DATA jobs submitted by the UI could be incorrectly rejected with a validation error about missing research/backtest fields.
- The misclassification could cause job failures, blocking data preparation workflows.
- The non‑deterministic behavior made debugging difficult and undermined trust in the job submission system.

## Next Steps
Apply three targeted patches:
1. **Patch A** – Make the detection rule deterministic: if `explicit_job_type` is present and recognized, use it; never fall back.
2. **Patch B** – Ensure `normalize_job_type` includes `BUILD_DATA` in its mapping for robustness.
3. **Patch C** – Reduce logging noise by emitting debug messages only when the detection path is ambiguous (e.g., when falling back).

Then write regression tests to verify the fix.

---
*Discovery completed 2026-01-19T15:37Z*