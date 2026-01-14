# Route 4: Data Prepare as First-Class Citizen - Evidence Bundle

## Overview
Successfully implemented Route 4: Data Prepare as First-Class Citizen in FishBroWFS_V2 desktop application. This work transforms data status into a governed, repairable workflow where:
- Prepare is explicit (never implicit)
- Prepare is separate from Run
- Prepare completion is required before Run unlocks
- Explain Hub tells users *why* data is stale/missing and *what will be built*

## Key Deliverables

### 1. DataPrepareService
**File**: `src/gui/services/data_prepare_service.py` (417 lines)
- Qt-based service with progress reporting via signals
- `PrepareStatus` enum with PREPARING/FAILED states
- `PrepareResult` dataclass for persistence
- Singleton access via `get_data_prepare_service()`
- Job submission via SupervisorClient BUILD_DATA jobs
- Artifact persistence for UI state restoration
- Progress polling with QTimer

### 2. DataPreparePanel UI Widget
**File**: `src/gui/desktop/widgets/data_prepare_panel.py` (468 lines)
- Qt widget for Explain Hub integration
- Shows dataset status with color-coded badges
- Action buttons: Build Cache, Rebuild Cache, Cancel, Retry
- Progress bars and result messages
- Integrated into OpTab Explain Hub

### 3. Enhanced Gate Enforcement
**File**: `src/gui/services/dataset_resolver.py` (modified)
- Added `evaluate_run_readiness_with_prepare_status()` method
- Enhanced gate evaluation to consider:
  - DATA1 must be READY (FAIL if not)
  - DATA2 evaluated per Option C rules (strategy-dependent)
  - Prepare status: FAIL if any dataset is PREPARING or FAILED
- Run button blocked until all gates PASS

### 4. Tests
**New File**: `tests/gui_services/test_data_prepare_service.py` (336 lines)
- Comprehensive tests for DataPrepareService
- Tests for artifact persistence, job polling, status tracking

**Modified File**: `tests/gui_services/test_dataset_resolver.py`
- Added tests for new `evaluate_run_readiness_with_prepare_status()` method
- Fixed import errors and mock paths

## Key Implementation Details

### Hybrid BC v1.1 Compliance
- Layer 1/2: No performance metrics in gate evaluation
- Layer 3: Metrics allowed only in analysis drawer
- Dataset as Derived Field: Users never manually select dataset IDs

### DATA2 Gate Option C (AUTO/strategy-dependent)
- If strategy requires DATA2 and DATA2 is MISSING => BLOCKER
- If strategy requires DATA2 and DATA2 is STALE => WARNING
- If strategy ignores DATA2 => PASS (even if DATA2 missing)
- Fallback: If strategy has no dependency declaration => BLOCKER (safe default)

### Supervisor Client API Updates
- Uses `get_job()` (not `get_job_status`) with `state` field (not `status`)
- Fixed import errors in test mocks
- Updated mock paths from `gui.services.dataset_resolver.get_data_prepare_service` to `gui.services.data_prepare_service.get_data_prepare_service`

## Files Changed

### New Files Created
1. `src/gui/services/data_prepare_service.py` - Core service implementation
2. `src/gui/desktop/widgets/data_prepare_panel.py` - UI widget
3. `tests/gui_services/test_data_prepare_service.py` - Service tests

### Modified Files
1. `src/gui/services/dataset_resolver.py` - Enhanced gate evaluation
2. `src/gui/desktop/tabs/op_tab.py` - Added DataPreparePanel to Explain Hub
3. `tests/gui_services/test_dataset_resolver.py` - Added tests, fixed imports

## Test Results

### `make check` Output
```
=== 1486 passed, 43 skipped, 3 deselected, 11 xfailed, 80 warnings in 35.93s ===
```

**Exit Code**: 0 (success)

### New Test Coverage
- DataPrepareService initialization and singleton access
- Prepare job submission and polling
- Artifact persistence and restoration
- Cancel and retry functionality
- Gate evaluation with prepare status
- DATA2 Option C logic validation

## Discovery Evidence

### Existing Data Prepare Infrastructure
Found existing BUILD_DATA job type in supervisor handlers:
- `src/control/supervisor/handlers/build_data.py` - Existing handler
- Job type: "BUILD_DATA" with dataset_id parameter
- Used for cache building and rebuilding

### Supervisor Client API
- `submit_job()` - Submit new job
- `get_job()` - Get job details (uses `state` field, not `status`)
- `abort_job()` - Request job abortion

## Compliance with Route 4 Requirements

### ✅ Data Prepare as First-Class Citizen
- [x] Prepare is explicit (never implicit) - User must click "Build Cache" or "Rebuild Cache"
- [x] Prepare is separate from Run - Separate panel, separate workflow
- [x] Prepare completion is required before Run unlocks - Gate evaluation enforces this
- [x] Explain Hub tells users why data is stale/missing and what will be built - DataPreparePanel shows status and actions

### ✅ Hybrid BC v1.1 Compliance
- [x] Layer 1/2: No performance metrics in gate evaluation
- [x] Layer 3: Metrics allowed only in analysis drawer
- [x] Dataset as Derived Field: Users never manually select dataset IDs

### ✅ DATA2 Gate Option C
- [x] Strategy-dependent gating implemented
- [x] Safe default (requires=True if declaration missing)
- [x] PASS/WARNING/FAIL logic per Red Team mandate

### ✅ Supervisor Client Integration
- [x] Uses existing BUILD_DATA job type
- [x] Proper error handling and progress reporting
- [x] Job cancellation support

## Technical Decisions

### 1. Qt Signals for Async Progress
Used PySide6 Qt signals (`progress`, `finished`, `status_changed`) for asynchronous progress reporting to UI.

### 2. Artifact Persistence
Store prepare results in `outputs/_runtime/data_prepare/` for UI state restoration across sessions.

### 3. Singleton Pattern
Both DataPrepareService and DatasetResolver use singleton pattern for consistent state across UI components.

### 4. Mock Fixes for Tests
Fixed import errors by:
- Updating from `get_job_status` to `get_job`
- Correcting mock paths for `get_data_prepare_service`
- Using `assert_any_call()` instead of `assert_called_with()` for multiple calls

## Verification

All tests pass with `make check` (0 failures). The implementation:
1. ✅ Does not break existing functionality
2. ✅ Adds comprehensive test coverage
3. ✅ Follows project coding standards
4. ✅ Maintains backward compatibility
5. ✅ Implements all Route 4 requirements

## Next Steps (Route 2)
Route 4 completes the Data Prepare as First-Class Citizen implementation. The next logical step would be Route 2: Dataset Derived Resolver + Registry Surface Defensive Adapter, which builds upon this foundation to:
1. Enhance dataset derivation transparency
2. Implement registry surface defensive adapter
3. Add more comprehensive error handling

---
**Evidence Created**: 2026-01-14T09:24:00Z  
**Route**: 4 (Data Prepare as First-Class Citizen)  
**Status**: COMPLETE ✅