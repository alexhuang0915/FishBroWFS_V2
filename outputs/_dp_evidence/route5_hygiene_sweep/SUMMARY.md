# Route 5 Hygiene Sweep - Summary Report

## Overview
Completed hygiene sweep for FishBroWFS_V2 repository to reduce governance debt, remove noisy warnings, and tighten UI/service contracts without changing behavior, backend APIs, or weakening tests.

## Warning Delta

### Before (Baseline)
- **Total warnings**: 80
- **Breakdown**:
  - 78 DeprecationWarnings from `test_no_gui_timeframe_literal_lists.py` (ast.Str deprecated)
  - 1 SyntaxWarning from `test_no_import_src_package.py` (invalid escape sequence)
  - 1 UserWarning from `test_ui_reality.py` ("Hardcoded dropdown values found in UI modules")

### After (Post-fixes)
- **Total warnings**: 0
- **All warnings eliminated**

### Warning Reduction: 100% (80 → 0)

## Files Changed

### 1. `tests/hygiene/test_ui_reality.py`
- **Change**: Fixed false positive detection of "hardcoded_timeframe_like list"
- **Line**: 71-76 in `parse_ast_for_patterns` function
- **Issue**: Empty lists (`logs = []`) were incorrectly flagged because `all(v % 15 == 0 for v in values)` returns `True` for empty lists
- **Fix**: Added check for non-empty list: `if values is not None and values:`
- **Impact**: Eliminated UserWarning about "Hardcoded dropdown values"

### 2. `tests/hygiene/test_no_import_src_package.py`
- **Change**: Fixed SyntaxWarning from invalid escape sequence in docstring
- **Line**: 7 in docstring
- **Issue**: `\s` in docstring `^(from|import)\s+src\.` was interpreted as string escape
- **Fix**: Escaped backslashes: `^(from|import)\\s+src\\.`
- **Impact**: Eliminated SyntaxWarning

### 3. `tests/hygiene/test_no_gui_timeframe_literal_lists.py`
- **Change**: Fixed 78 DeprecationWarnings about `ast.Str` deprecation
- **Line**: 54-70 in `extract_string_value` function
- **Issue**: Checking for deprecated `ast.Str` (removed in Python 3.14)
- **Fix**: Removed `ast.Str` check (project requires Python >=3.10, uses `ast.Constant`)
- **Impact**: Eliminated all 78 DeprecationWarnings

## SSOT (Single Source of Truth) Accessors

### Timeframe SSOT
- **SSOT Location**: `src/config/registry/timeframes.py` (`DEFAULT_TIMEFRAMES = [15, 30, 60, 120, 240]`)
- **GUI Provider**: `src/gui/services/timeframe_options.py` (`get_timeframe_ids()`, `get_timeframe_id_label_pairs()`)
- **Status**: No actual hardcoded timeframe lists found in GUI code. All references use SSOT providers.

## Import Hygiene & Dead Code Cleanup

### Findings:
1. **`op_tab_legacy.py`**: File exists at `src/gui/desktop/tabs/op_tab_legacy.py` but is **not imported anywhere** (confirmed via grep)
2. **Root-level debug scripts**: No Python files in root directory; scripts directory organized with `_dev/` for debug scripts
3. **Unused imports**: No significant unused imports found requiring cleanup

## Contract Tightening

### VM Contracts
- **File**: `src/gui/services/hybrid_bc_vms.py`
- **Status**: Already well-defined with clear layer separation:
  - Layer 1/2 (`JobIndexVM`, `JobContextVM`): No performance metrics
  - Layer 3 (`JobAnalysisVM`): Allows metrics with `payload` field for backward compatibility
- **No changes needed**: Contract is already tight with clear documentation

## Testing Results

### Hardening Tests
- **Result**: 33 passed, 1 skipped in 1.27s
- **Status**: All hardening tests pass

### Full Test Suite (`make check`)
- **Result**: 1486 passed, 43 skipped, 3 deselected, 11 xfailed in 35.59s
- **Status**: 0 failures, 0 warnings

### UI Smoke Test (Optional)
- **Not performed**: As per requirements, optional UI smoke test with timeout was not required for completion

## Evidence Files Created

All required evidence files created in `outputs/_dp_evidence/route5_hygiene_sweep/`:
1. `make_check_before.txt` - Baseline `make check` output
2. `warnings_before.txt` - Baseline warnings extraction
3. `rg_hardcoded_hits.txt` - Search results for hardcoded patterns
4. `pytest_hardening_after.txt` - Hardening tests after fixes
5. `make_check_after.txt` - Full `make check` after fixes
6. `warnings_after.txt` - Warnings extraction after fixes (0 warnings)
7. `SUMMARY.md` - This summary file

## Acceptance Criteria Verification

| Criteria | Status | Notes |
|----------|--------|-------|
| 1. `make check` passes with 0 failures | ✅ PASS | 1486 passed, 0 failures |
| 2. Warning count reduced or unchanged with justification | ✅ PASS | 80 → 0 warnings eliminated |
| 3. "Hardcoded dropdown/timeframe_like list" warnings eliminated | ✅ PASS | Fixed false positive in test |
| 4. No behavior regressions (no UX changes, no new features) | ✅ PASS | Only test fixes, no behavior changes |
| 5. No new repo-root files; all changes follow hygiene | ✅ PASS | All changes in existing files |
| 6. Evidence bundle exists | ✅ PASS | All evidence files created |

## Conclusion

Route 5 Hygiene Sweep completed successfully with:
- **100% warning elimination** (80 warnings → 0 warnings)
- **No behavior changes** (only test fixes for false positives)
- **All tests pass** (1486 passed, 0 failures)
- **Evidence complete** (all required files created)
- **SSOT compliance verified** (no actual hardcoded timeframe lists in GUI)

The repository is now cleaner with reduced governance debt and eliminated noisy warnings while maintaining full backward compatibility and test coverage.