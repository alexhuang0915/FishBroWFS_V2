# Outputs Prune Makecheck Fix Summary

## Problem
After YellowBoss pruned outputs aggressively, baseline tests failed because they expected a shared feature cache at:
`outputs/shared/2026Q1/CME.MNQ/features/features_60m.npz`

Failing tests:
- `tests/control/test_baseline_experiments.py::test_verify_feature_cache_with_dummy_data`
- `tests/control/test_baseline_experiments.py::test_missing_features_failure`
- `tests/control/test_baseline_experiments.py::test_main_failure_missing_features`

## Solution
Implemented a test-side session fixture that ensures minimal shared feature cache exists before baseline tests run.

### Changes Made

1. **Created `tests/control/conftest.py`** with fixture `ensure_minimal_shared_feature_cache`:
   - Scope: session, autouse=True
   - Creates dummy `features_60m.npz` file if missing
   - Includes minimal valid data with all S1/S2/S3 feature names
   - Uses tiny arrays (size 2) to keep file small
   - Does not interfere with tests that use their own temp directories

2. **No changes to production code** - only test infrastructure modified.

### Key Design Decisions

- **Test-only fix**: Avoids changing production behavior or committing dummy artifacts
- **Self-contained**: Tests pass even if outputs/shared is completely empty
- **Minimal footprint**: Dummy file is only created when missing, contains minimal data
- **Safe for CI**: No network dependencies, deterministic, fast
- **Respects outputs prune**: Does not restore actual feature data, just enough for tests to pass

## Verification

### Before Fix
- `make check` showed 3 failures in baseline tests
- FileNotFoundError for `outputs/shared/2026Q1/CME.MNQ/features/features_60m.npz`

### After Fix
- `make check`: **1392 passed, 36 skipped, 3 deselected, 10 xfailed, 0 failures**
- Acceptance harness: **PASS** (exit code 0)
- All baseline tests pass without requiring pre-existing outputs

### Evidence Files
- `00_before_fail_excerpt.txt`: Captured failure traceback
- `01_git_status_before.txt`: Git status before changes
- `02_changes_diff.txt`: Git diff showing only tests/control/conftest.py added
- `03_make_check_after.txt`: Full make check output showing 0 failures
- `04_acceptance_after.txt`: Acceptance harness PASS output

## Commit
Single commit with message:
"Test hardening: seed minimal shared feature cache for baseline tests (safe after outputs prune)"

## Compliance with Requirements

✅ **make check passes**: 0 failures  
✅ **acceptance harness PASS**: exit code 0  
✅ **No new files in repo root**: Only tests/control/conftest.py  
✅ **No committed artifacts under outputs/**: Dummy cache not committed  
✅ **Baseline tests self-seed**: No pre-existing outputs/shared required  
✅ **Test-only change**: No production code modified  

## Impact
- Baseline tests now resilient to outputs directory being pruned
- CI/CD pipeline remains stable after aggressive cleanup
- No performance impact (dummy file created once per test session)
- Maintains test isolation and determinism