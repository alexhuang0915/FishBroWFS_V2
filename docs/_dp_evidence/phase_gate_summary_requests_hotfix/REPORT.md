# Gate Summary “requests” UnboundLocalError Hotfix Report

## Summary

Fixed a P0 bug where the gate summary service could raise `UnboundLocalError: cannot access local variable 'requests'` due to module‑level import missing and local imports inside exception handlers.

## Root Cause

The service contained two local `import requests` statements inside `_fetch_api_readiness` and `_fetch_registry_surface`. If the import succeeded, the variable `requests` was defined in the local scope. However, if the import itself raised `ModuleNotFoundError` (or any other exception) before the `except` block, the variable `requests` would be uninitialized when referenced in the exception handler (`requests.exceptions.ConnectionError`), causing `UnboundLocalError`.

## Changes Made

### 1. Module‑level import
- Added `import requests` at the top of `src/gui/services/gate_summary_service.py`.
- Removed the two local `import requests` lines inside the functions.

### 2. Fail‑closed UI behavior
- Wrapped the entire `fetch` method in a try‑except that catches any `Exception`.
- If a catastrophic exception occurs (e.g., `AttributeError`, `ImportError`), the service now returns a safe fallback `GateSummary` with a single error gate, preventing the UI from crashing.
- The fallback summary includes a gate with ID `catastrophic_failure` and status `FAIL`, providing enough information for debugging while keeping the UI functional.

### 3. Regression test
- Created `tests/gui/services/test_gate_summary_service_requests_regression.py` with four tests:
  1. `test_fetch_never_unboundlocal` – ensures fetch does not raise `UnboundLocalError` when `requests` is missing.
  2. `test_fetch_with_mocked_requests_get` – verifies fetch works when the lowest IO primitive is patched.
  3. `test_fallback_on_catastrophic_exception` – confirms that unexpected exceptions are caught and a fallback summary is returned.
  4. `test_requests_module_level_import` – static check that no function contains `import requests`.

## Verification

### Targeted tests
- Regression test passes (4/4).
- Existing gate summary service tests pass (12/12).
- Gate summary widget tests pass (9/9).

### Full test suite
- `make check` passes (1445 passed, 0 failures, 11 xfailed, 36 skipped).

### Runtime smoke
- Launched UI with `make up` (timeout 20s).
- No occurrences of `cannot access local variable 'requests'` or `Failed to fetch gate summary` errors.
- UI starts without crashing.

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| No `requests` UnboundLocalError at runtime smoke | ✅ PASS |
| Regression test added and passing | ✅ PASS |
| `make check` → 0 failures | ✅ PASS |
| No new repo‑root files | ✅ PASS |

## Files Modified

- `src/gui/services/gate_summary_service.py`
- `tests/gui/services/test_gate_summary_service_requests_regression.py` (new)

## Evidence Files

- `rg_gate_summary_service.txt` – discovery output
- `rg_gui_gate_summary_calls.txt` – call path references
- `pytest_regression.txt` – regression test output
- `pytest_gate_summary.txt` – existing gate summary tests output
- `make_check.txt` – full test suite output
- `make_up_timeout20s.txt` – UI launch output

## Conclusion

The hotfix eliminates the `UnboundLocalError` risk, ensures the service never crashes the OP tab, and adds a regression test to prevent future regressions. The changes are minimal, localized, and satisfy all hard rules (no new root files, tests under allowed directories, verification commands terminate).