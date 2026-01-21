# GOVERNANCE CLEANUP REPORT
## BarPrepare Build Bars: Hardcoded Path + OpenAPI Snapshot Lock Fix

**Date:** 2026-01-19  
**Task:** Governance Cleanup: Remove Hardcoded Path + Fix OpenAPI Snapshot Lock  
**Evidence Bundle:** `outputs/_dp_evidence/governance_cleanup_bars_openapi/`

---

## Executive Summary (PASS)

**Overall Status:** ✅ **PASS**

Both governance violations identified in the previous `make check` run have been successfully resolved:

1. **Hardcoded `/tmp/...` path in `src/core/bars_contract.py`** - **FIXED**
2. **OpenAPI snapshot corruption (JSONDecodeError)** - **FIXED**

All tests now pass with **0 failures** (2056 passed, 50 skipped, 12 xfailed).

---

## Fix #1: Hardcoded Path Removal (PASS)

### Issue
Found hardcoded absolute path `/tmp/test_bars.npz` in `src/core/bars_contract.py` within a `__main__` demo/test section.

### Location
- File: `src/core/bars_contract.py`
- Lines: 697-710 (demo/test code in `if __name__ == "__main__":` block)
- Violation: Absolute path `/tmp/test_bars.npz` violates governance rule "No absolute paths in `src/`"

### Fix Applied
Removed the entire `__main__` section (lines 697-710) containing:
- Demo/test code that shouldn't be in production `src/`
- Hardcoded `/tmp/test_bars.npz` path
- Test data generation logic

### Verification
```bash
rg -n '"/tmp"|/tmp/test_bars\.npz' src/
```
**Result:** No matches found ✅

### Compliance Status: **PASS**

---

## Fix #2: OpenAPI Snapshot Repair (PASS)

### Issue
OpenAPI snapshot file `tests/contract_snapshots/openapi.json` was corrupted/empty (0 bytes), causing `JSONDecodeError` in `test_openapi_snapshot_lock.py`.

### Root Cause
The snapshot file was empty, likely due to:
- Previous failed generation attempt
- File truncation during write
- Missing snapshot regeneration after API changes

### Fix Applied
Regenerated the OpenAPI snapshot using the correct method:
```bash
.venv/bin/python -c "from src.control.api import app; import json; import sys; json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)" > tests/contract_snapshots/openapi.json
```

### Verification
- File size: 175,859 bytes (previously 0 bytes)
- Valid JSON structure confirmed
- `test_openapi_snapshot_lock.py` now passes

### Compliance Status: **PASS**

---

## Test Results (PASS)

### Command: `make check`
```
2056 passed, 50 skipped, 3 deselected, 12 xfailed, 0 failures
```

### Key Test Files Modified
1. **`src/core/bars_contract.py`** - Removed demo/test `__main__` section
   - Justification: Demo/test code shouldn't be in production `src/`; hardcoded paths violate governance
   - No critical assertions removed; only demo code removed

2. **`tests/contract_snapshots/openapi.json`** - Regenerated snapshot
   - Justification: File was corrupted (0 bytes), causing JSONDecodeError
   - No assertions changed; only file content regenerated

### Test Status: **PASS** (0 failures)

---

## Root Hygiene (PASS)

### Verification
- No unexpected files in repository root
- All evidence files created under `outputs/_dp_evidence/governance_cleanup_bars_openapi/`
- Working tree clean except evidence files

### Status: **PASS**

---

## Deviations / Risks / Follow-ups

### None Identified

Both fixes are surgical and minimal:
1. Removing demo/test code from `src/` improves code hygiene
2. Regenerating corrupted snapshot restores test functionality
3. No API changes, no behavior changes, no new dependencies

### Recommendations
1. Consider adding a pre-commit hook to prevent hardcoded `/tmp/` paths in `src/`
2. Ensure `make api-snapshot` target writes to correct location or update test expectation
3. Monitor OpenAPI snapshot generation in CI to prevent future corruption

---

## Final Acceptance Criteria Check

| Criteria | Status | Notes |
|----------|--------|-------|
| Evidence bundle exists at correct location | ✅ PASS | `outputs/_dp_evidence/governance_cleanup_bars_openapi/` |
| Root hygiene respected | ✅ PASS | No stray root files |
| Hardcoded path removed | ✅ PASS | No `/tmp/` paths in `src/` |
| OpenAPI snapshot repaired | ✅ PASS | Valid JSON, 175,859 bytes |
| `make check` passes (0 failures) | ✅ PASS | 2056 passed, 0 failures |
| No backend changes | ✅ PASS | Only demo code removal and snapshot regeneration |
| No evidence semantics changes | ✅ PASS | OpenAPI snapshot format unchanged |

**OVERALL: ✅ ALL CRITERIA MET**