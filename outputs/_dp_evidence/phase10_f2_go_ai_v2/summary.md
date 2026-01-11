# GO AI v2 — Governance Gaps Fixes

## Overview

Two governance gaps were addressed:

1. **Patch B2**: Supervisor worker bootstrap import path changed from `src.control.supervisor.bootstrap` to `control.supervisor.bootstrap` (removing `src.` prefix).
2. **Patch C2**: API fail‑fast when dates missing (no empty‑string fallback). The `_build_run_research_v2_params` function now raises `ValueError` if `start_date` or `end_date` are missing or empty.

## Changes Applied

### Patch B2 – Supervisor worker bootstrap import path

**File**: `src/control/supervisor/supervisor.py` line 46

**Before**:
```python
module_str = "src.control.supervisor.bootstrap"
```

**After**:
```python
module_str = "control.supervisor.bootstrap"
```

**Evidence**:
- `rg -n "spawn_worker" -S src/control/supervisor/supervisor.py` shows the function definition and usage (no longer contains `src.` prefix in module string).
- The change ensures that the supervisor can spawn workers without relying on a `src` package in the Python path.

### Patch C2 – API fail‑fast when dates missing

**File**: `src/control/api.py` lines 954‑960

**Before**:
```python
start_date = req.get("start_date") or ""
if not isinstance(start_date, str):
    raise ValueError("start_date must be a string")

end_date = req.get("end_date") or ""
if not isinstance(end_date, str):
    raise ValueError("end_date must be a string")
```

**After**:
```python
start_date = req.get("start_date")
if not start_date or not isinstance(start_date, str) or start_date.strip() == "":
    raise ValueError("start_date is required and must be a non-empty string")

end_date = req.get("end_date")
if not end_date or not isinstance(end_date, str) or end_date.strip() == "":
    raise ValueError("end_date is required and must be a non-empty string")
```

**Evidence**:
- `rg -n "start_date.*or.*\"\"" -S src/control/api.py` returns **no matches** (the empty‑string fallback has been removed).
- `rg -n "end_date.*or.*\"\"" -S src/control/api.py` returns **no matches** (same).
- The new validation raises a clear `ValueError` that will be caught by the endpoint and turned into HTTP 422.

## Validation

### `make check` results

All product tests pass (1292 passed, 36 skipped, 3 deselected, 11 xfailed). No new failures introduced.

**Output saved**: `outputs/_dp_evidence/phase10_f2_go_ai_v2/make_check_output.txt`

### Test suite `tests/control/test_jobs_post_contract_422.py`

This test includes start_date and end_date fields; it continues to pass because the required fields are provided.

## Conclusion

Both governance gaps have been closed:

1. Supervisor worker spawning now uses the correct module path (`control.supervisor.bootstrap`), eliminating any dependency on a `src` package in the Python path.
2. The API now fails fast when start_date or end_date are missing or empty, preventing silent empty‑string fallback that could hide configuration errors.

All changes are backward‑compatible with existing UI contracts (the UI already sends start_date and end_date). The only breaking change is that missing dates will now cause a clear 422 error instead of a downstream validation error, which is the intended behavior.

**Evidence bundle**: All rg outputs and make check logs are stored in this directory.