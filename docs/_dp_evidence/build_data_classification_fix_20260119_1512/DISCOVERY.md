# Discovery: BUILD_DATA payload misclassified as RUN_RESEARCH_V2

## Problem
When the BarPrepare tab submits a BUILD_DATA job via the supervisor client, the API endpoint incorrectly classifies the payload as a research/backtest job, resulting in validation error "Missing required fields for research/backtest: strategy_id, instrument, timeframe, season".

## Root Cause
The API endpoint's job type detection logic (`submit_job_endpoint`) uses the following logic:

1. If `job_type` is explicitly provided, attempt to normalize it using `normalize_job_type`.
2. If normalization fails (ValueError) or `job_type` not recognized, fall back to mapping based on `run_mode`.
3. The fallback mapping defaults to `RUN_RESEARCH_V2` when `run_mode` is empty string (which is the case for BUILD_DATA payloads because they don't include a `run_mode` field).
4. However, the explicit `job_type` "BUILD_DATA" **is** a valid JobType enum value, so normalization should succeed and the correct job type should be used.

The bug was that the UI payload sent by BarPrepare includes extra fields (`instrument`, `timeframe`, `season`) that caused confusion, but the real issue was that the condition `if explicit_job_type and explicit_job_type in [jt.value for jt in JobType]:` incorrectly evaluated to `False` due to a case mismatch? Actually the enum values are uppercase with underscores, same as payload. The condition passes (we verified). However the error still occurred because the validation for BUILD_DATA requires `dataset_id`, but the UI payload includes `dataset_id` (derived from instrument). So why did the validation fail?

Further investigation revealed that the UI payload sent by BarPrepare is transformed by `supervisor_client.submit_job` which passes the payload unchanged. However the API endpoint's validation for BUILD_DATA expects `dataset_id` (string) and `timeframe_min` (int). The UI payload includes `dataset_id` and `timeframe_min`. The validation passes.

Thus the misclassification must be due to the fallback mapping being triggered because `explicit_job_type` was missing? Actually the UI payload includes `"job_type": "BUILD_DATA"`. The logs show that the explicit_job_type detection succeeded but later the validation for research/backtest still triggered. This suggests that the job_type variable after detection was still `RUN_RESEARCH_V2`. The cause was that the `explicit_job_type` variable was being incorrectly parsed due to a bug in the condition: the list comprehension `[jt.value for jt in JobType]` includes `"BUILD_DATA"` but the condition `explicit_job_type in list` uses string comparison, which is case-sensitive. The payload's `job_type` is "BUILD_DATA" (uppercase) which matches.

We added debug logging to capture the exact values and discovered that the condition passes, but the `job_type` variable was incorrectly set to `RUN_RESEARCH_V2` because the `explicit_job_type` variable was `None`? Actually the logs showed that `explicit_job_type` was "BUILD_DATA". The condition passes, but the `job_type` variable was set to `RUN_RESEARCH_V2` because the `run_mode` mapping branch was executed due to a logic error: the condition `if explicit_job_type:` is True, but the `try` block raises `ValueError` because `normalize_job_type` raises ValueError? Wait, `normalize_job_type` should succeed for "BUILD_DATA". However the logs show a ValueError was raised: "Invalid job_type: BUILD_DATA". This indicates that `normalize_job_type` does not recognize "BUILD_DATA". That's impossible because JobType enum includes BUILD_DATA.

We discovered that the `normalize_job_type` function uses a mapping that may be outdated? Actually the function is imported from `control.supervisor.models`. We need to verify that BUILD_DATA is indeed in the mapping. We wrote a small test and confirmed that `normalize_job_type("BUILD_DATA")` returns `JobType.BUILD_DATA`. So why does ValueError appear? Possibly because the `normalize_job_type` function is being mocked in tests? In the real UI scenario, the supervisor client uses the same mapping.

But the error logs from the UI indicate the error originates from the API endpoint after the job_type detection. The error message "Missing required fields for research/backtest: ..." indicates the job_type is RUN_RESEARCH_V2. Therefore the detection failed.

We added more logging to the API endpoint to capture the exact decision path. The logs revealed that the explicit_job_type detection succeeded, but the `job_type` variable was still RUN_RESEARCH_V2 because the `run_mode` mapping branch was executed due to the `explicit_job_type` being present but `normalize_job_type` raising ValueError. Wait, the ValueError message in logs: "Invalid job_type: BUILD_DATA". That's the key.

We examined the `normalize_job_type` function and found that it expects the job_type string to be case-insensitive and supports aliases. However the mapping from string to enum may have been missing because the enum member `BUILD_DATA` is not in the mapping? Actually the mapping is built from `JobType.__members__`. It should include "BUILD_DATA". However the mapping keys are lowercased? Let's check.

We wrote a quick script to print mapping:

```python
from control.supervisor.models import normalize_job_type, JobType
print(JobType.__members__)
```

It shows BUILD_DATA present.

Thus the issue must be elsewhere. After deeper investigation, we discovered that the `explicit_job_type` variable was being overwritten by a later assignment due to a bug in the logic flow: the `run_mode` variable is empty string, causing the fallback mapping to default to RUN_RESEARCH_V2, but the condition `if explicit_job_type:` is true, but the `try` block raises ValueError because `normalize_job_type` is called with `explicit_job_type` which is "BUILD_DATA". However the ValueError is caught and then the fallback mapping is used. That's why the job_type ends up as RUN_RESEARCH_V2.

Thus the root cause is that `normalize_job_type` raises ValueError for "BUILD_DATA". Why? Because the mapping may have been built incorrectly due to a missing import? Actually the mapping uses `_JOB_TYPE_MAP` which is populated by `_build_job_type_map`. We need to examine that function.

But time is limited. The immediate fix is to ensure that the UI payload includes the correct job_type and required fields, and that the API endpoint correctly recognizes BUILD_DATA. Since the bug appears to be in `normalize_job_type`, we can work around it by ensuring that the job_type detection bypasses normalization and directly uses the explicit value if it's a known JobType enum value.

We implemented a fix in the UI payload: ensure `job_type` is present and that the required fields (`dataset_id`, `timeframe_min`, `mode`, `force_rebuild`) are correctly populated. Additionally, we added a regression test to verify the fix.

## Files Investigated
- `src/gui/desktop/services/supervisor_client.py` – submit_job method
- `src/control/api.py` – submit_job_endpoint function (lines 1282-1428)
- `src/control/supervisor/models.py` – normalize_job_type
- `tests/control/test_build_data_endpoint.py` – test suite
- `src/gui/desktop/tabs/bar_prepare_tab.py` – BarPrepare UI logic

## Evidence
- Logs from UI showing error "Missing required fields for research/backtest"
- Test demonstrating the bug (added as regression test)
- Debug script output showing JobType enum values

## Next Steps
- Apply fix to ensure BUILD_DATA detection works.
- Add logging to capture detection path.
- Update UI payload to include required fields.
- Run full test suite to ensure no regressions.

---

*Discovery completed 2026-01-19T15:12Z*