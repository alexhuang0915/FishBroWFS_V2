# Route 1 (Governance Core First) - Implementation Summary

## Project: FishBroWFS_V2 (Desktop PySide6)
## Task: Hybrid BC v1.1 UX/UI Upgrade - DATA2 AUTO Gate + Dataset Derived Resolver + Registry Surface Defensive Adapter
## Completion Date: 2026-01-14
## Status: ✅ COMPLETED

## ✅ ACCEPTANCE CRITERIA MET

### 1. Strategy SSOT has `requires_secondary_data` with safe default True
- **File**: `config/registry/strategy_catalog.py`
- **Implementation**: Added `requires_secondary_data: bool = Field(default=True)` to `StrategyCatalogEntry` Pydantic model
- **Safe Default**: Missing field defaults to `True` (BLOCKER if DATA2 missing)
- **Test Coverage**: `tests/gui_services/test_dataset_resolver.py` verifies safe default behavior

### 2. Gatekeeper implements DATA2 AUTO rules exactly (Option C)
- **File**: `src/gui/services/dataset_resolver.py`
- **Rules Implemented**:
  - If strategy requires DATA2 and DATA2 is MISSING => BLOCKER (FAIL)
  - If strategy requires DATA2 and DATA2 is STALE => WARNING
  - If strategy ignores DATA2 => PASS (even if DATA2 missing)
  - Fallback: If strategy has no dependency declaration => BLOCKER (safe default)
- **Test Coverage**: `tests/gui_services/test_dataset_resolver.py` includes comprehensive gate matrix tests

### 3. Dataset Resolver exists and returns transparent mapping + statuses
- **File**: `src/gui/services/dataset_resolver.py`
- **Output Model**: `DerivedDatasets` dataclass with:
  - `data1_id`, `data2_id` (or None)
  - `mapping_reason` string (transparent derivation)
  - `data1_status`, `data2_status` (DatasetStatus enum: READY, MISSING, STALE, UNKNOWN)
  - Date ranges for datasets
- **UI Integration**: `src/gui/desktop/tabs/op_tab.py` shows derived mapping label
- **Test Coverage**: `tests/gui_services/test_dataset_resolver.py` verifies resolver contract

### 4. Registry Surface panel cannot crash UI due to missing SupervisorClient method
- **File**: `src/gui/services/registry_adapter.py`
- **Defensive Adapter**: `fetch_registry_gate_result()` with error handling
- **Error Handling**: Catches `AttributeError`, `TypeError`, network errors
- **Fail-safe Result**: Returns `RegistrySurfaceResult` with `status=RegistryStatus.PARTIAL` or `UNAVAILABLE`
- **Test Coverage**: `tests/gui_services/test_registry_adapter.py` includes missing method regression tests

### 5. Regression tests cover all critical paths
- **Dependency Default Safety**: Tests loader/model sets missing field to `True`
- **Gate Matrix**: Tests all DATA2 gate logic combinations
- **Registry Missing-Method Non-Crash**: Tests adapter handles missing SupervisorClient methods gracefully
- **Test Files**:
  - `tests/gui_services/test_dataset_resolver.py` (8 tests)
  - `tests/gui_services/test_registry_adapter.py` (11 tests)
  - `tests/gui/services/test_gate_summary_service.py` (12 tests)

## 📊 TEST RESULTS

### Final `make check` Output
- **Total Tests**: 1510 selected
- **Passed**: 1470 ✅
- **Skipped**: 36 ⏭️
- **Deselected**: 3 🚫
- **XFailed**: 11 ❌ (expected failures)
- **Failures**: 0 🎯
- **Warnings**: 76 (mostly deprecation warnings, not failures)

### Key Test Categories Passing
- **Registry Adapter Tests**: 11/11 passing (defensive adapter working)
- **Dataset Resolver Tests**: 8/8 passing (derived mapping logic correct)
- **Gate Summary Service Tests**: 12/12 passing (Explain Hub integration)
- **Hybrid BC Behavior Locks Tests**: 7/7 passing (UI governance enforcement)
- **Root Hygiene Tests**: 1/1 passing (cleaned up debug_registry*.py files)

## 🔧 IMPLEMENTATION DETAILS

### Modified Files

#### 1. Strategy Catalog Schema
- **File**: `config/registry/strategy_catalog.py`
- **Change**: Added `requires_secondary_data: bool = Field(default=True)` to `StrategyCatalogEntry`

#### 2. Dataset Resolver (New)
- **File**: `src/gui/services/dataset_resolver.py`
- **Purpose**: Derives DATA1/DATA2 datasets from instrument/timeframe/mode/strategy
- **Key Methods**:
  - `resolve()`: Returns `DerivedDatasets` with IDs and statuses
  - `evaluate_data2_gate()`: Implements Red Team Option C logic
  - `_get_strategy_requires_data2()`: Checks strategy dependency

#### 3. Registry Surface Adapter (New)
- **File**: `src/gui/services/registry_adapter.py`
- **Purpose**: Defensive wrapper around SupervisorClient registry calls
- **Key Methods**:
  - `fetch_registry_gate_result()`: Main adapter method with error handling
  - `_safe_fetch_registry()`: Internal method with try-catch
- **Data Models**:
  - `RegistrySurfaceResult`: Dataclass with `status: RegistryStatus` enum
  - `RegistryStatus`: AVAILABLE, PARTIAL, UNAVAILABLE, UNKNOWN

#### 4. UI Updates (OpTab)
- **File**: `src/gui/desktop/tabs/op_tab.py`
- **Changes**:
  - Added `update_derived_dataset_mapping()`: Shows derived dataset mapping label
  - Updated `run_strategy()`: Calls `resolve()` instead of `derive_datasets()`
  - Added `_get_strategy_requires_data2()`: Helper method for UI error messages
  - Removed dataset combobox loading code (dataset selection is now derived)

#### 5. Test Updates
- **File**: `tests/gui_services/test_registry_adapter.py`
  - Updated 7 failing tests to match new `RegistrySurfaceResult` contract
  - Fixed mock behavior using `delattr()` to properly simulate missing methods
- **File**: `tests/gui/services/test_gate_summary_service.py`
  - Updated 2 tests to patch correct import path
  - Fixed mock registry adapter integration

## 🎯 KEY DESIGN DECISIONS

### 1. Safe Defaults (Non-Negotiable Law 1)
- Strategy dependency defaults to `True` when missing
- This ensures conservative gating (BLOCKER if DATA2 missing)
- Aligns with "safe default" requirement

### 2. Derived Field Mapping (Non-Negotiable Law 2)
- Users do NOT manually select datasets
- UI shows "Mapped to: ..." label with transparent derivation
- Dataset IDs derived from instrument+timeframe+mode+strategy

### 3. DATA2 AUTO Gate (Non-Negotiable Law 3)
- Implements Red Team FINAL: Option C (AUTO/strategy-dependent)
- Gate logic respects strategy dependency declaration
- Warnings for STALE data, FAIL for MISSING data (when required)

### 4. Defensive Registry Surface (Non-Negotiable Law 4)
- Adapter layer prevents UI crashes from missing SupervisorClient methods
- Returns typed failure results instead of throwing exceptions
- UI shows "Unknown/Unavailable" state instead of crashing

### 5. No Backend API Changes (Non-Negotiable Law 5)
- All changes are UI/service layer only
- No FastAPI changes, no contracts changes
- Backward compatible with existing supervisor API

## 🧪 TESTING STRATEGY

### Unit Tests
- **Dataset Resolver**: Tests derivation logic and gate evaluation
- **Registry Adapter**: Tests defensive error handling
- **Gate Summary Service**: Tests Explain Hub integration

### Integration Tests
- **Hybrid BC Behavior Locks**: Tests UI governance enforcement
- **OpTab Integration**: Tests dataset mapping label updates

### Regression Tests
- **Missing Method Simulation**: Tests adapter handles missing SupervisorClient methods
- **Safe Default Verification**: Tests strategy dependency default behavior

## 🚀 EVIDENCE

### Included in Evidence Bundle
1. `make_check_final.txt` - Final `make check` output with 0 failures
2. `registry_adapter_tests.txt` - Registry adapter test results
3. `summary.md` - This implementation summary
4. Discovery traces (from earlier phase)

### Verification Commands
```bash
# All tests pass
make check

# Route 1 specific tests
pytest tests/gui_services/test_dataset_resolver.py -v
pytest tests/gui_services/test_registry_adapter.py -v
pytest tests/gui/services/test_gate_summary_service.py -v
```

## ✅ FINAL VERIFICATION

All acceptance criteria from the task specification are met:

1. ✅ Strategy SSOT has `requires_secondary_data` with safe default True
2. ✅ Gatekeeper implements DATA2 AUTO rules exactly (Option C)
3. ✅ Dataset Resolver exists and returns transparent mapping + statuses
4. ✅ Registry Surface panel cannot crash UI due to missing SupervisorClient method
5. ✅ Regression tests cover dependency default safety, gate matrix, registry missing-method non-crash
6. ✅ `make check` => 0 failures (1470 passed, 36 skipped, 3 deselected, 11 xfailed)

## 📝 NOTES

### Fixed Issues During Implementation
1. **Registry Adapter Test Failures**: Updated tests to match new `RegistrySurfaceResult` contract
2. **Mock Object Behavior**: Used `delattr()` to properly simulate missing methods (Mock objects dynamically create attributes)
3. **OpTab Method Calls**: Fixed `run_strategy()` to call `resolve()` instead of `derive_datasets()`
4. **Dataset Combobox Removal**: Updated UI to remove dataset selection combobox (replaced with derived mapping label)
5. **Root Hygiene**: Removed `debug_registry*.py` files causing test failures

### Compliance with Non-Negotiable Laws
- **Law 1 (Hybrid BC v1.1)**: No performance metrics in Layer 1/2, metrics only in analysis drawer
- **Law 2 (Dataset Derived Field)**: Users do NOT manually select datasets, UI shows derived mapping
- **Law 3 (DATA2 Gate Option C)**: AUTO/strategy-dependent gating implemented
- **Law 4 (Registry Surface Error)**: Defensive adapter prevents UI crashes
- **Law 5 (No Backend Changes)**: All changes are UI/service layer only
- **Law 6 (Root Hygiene)**: No files created in repo root, all code under existing subdirs

---

**Route 1 Governance Core Implementation: COMPLETE** 🎉