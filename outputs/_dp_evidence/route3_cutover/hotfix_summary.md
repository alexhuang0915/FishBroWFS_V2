# HOTFIX: Qt Import Issues in Card Selectors - COMPLETED

## Problem Statement
Desktop UI was crashing with two errors:
1. `NameError: name 'QSpacerItem' is not defined` in `base_card.py`
2. `AttributeError: 'OpTab' object has no attribute 'progress_signal'` in `control_station.py`

## Root Causes
1. **Missing Qt import**: `src/gui/desktop/widgets/card_selectors/base_card.py` used `QSpacerItem` but didn't import it
2. **Missing signals**: The new `OpTab` class (Route 3 cutover) was missing signals that `control_station.py` expects:
   - `progress_signal = Signal(int)`
   - `artifact_state_changed = Signal(str, str, str)`

## Fixes Applied

### 1. Fixed QSpacerItem Import (`base_card.py`)
**File**: `src/gui/desktop/widgets/card_selectors/base_card.py`
**Change**: Added `QSpacerItem` to imports
**Before**:
```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton, QSizePolicy
)
```
**After**:
```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton, QSizePolicy, QSpacerItem
)
```

### 2. Added Missing Signals (`op_tab.py`)
**File**: `src/gui/desktop/tabs/op_tab.py`
**Change**: Added missing signals to match legacy OpTab interface
**Before**:
```python
class OpTab(QWidget):
    log_signal = Signal(str)
    switch_to_audit_tab = Signal(str)  # job_id for report
```
**After**:
```python
class OpTab(QWidget):
    log_signal = Signal(str)
    switch_to_audit_tab = Signal(str)  # job_id for report
    progress_signal = Signal(int)  # progress updates
    artifact_state_changed = Signal(str, str, str)  # state, run_id, run_dir
```

## Verification

### 1. UI Launch Test
**Command**: `make up`
**Result**: UI launches successfully without crashes
**Evidence**: `outputs/_dp_evidence/route3_cutover/hotfix_qt_imports_after_make_up.txt`
- No `NameError` for `QSpacerItem`
- No `AttributeError` for `progress_signal`
- UI process starts and runs (terminated by timeout after 15 seconds)

### 2. Test Suite Verification
**Command**: `make check`
**Result**: All tests pass
**Evidence**: `outputs/_dp_evidence/route3_cutover/hotfix_qt_imports_after_make_check.txt`
- 1468 tests passed
- 43 tests skipped (expected)
- 11 tests xfailed (expected)
- 0 failures related to the fixes

### 3. Card Selector Import Audit
All card selector files were verified to have proper `QSpacerItem` imports:
- ✓ `base_card.py` - Fixed
- ✓ `timeframe_card_deck.py` - Already correct
- ✓ `mode_pill_cards.py` - Already correct
- ✓ `strategy_card_deck.py` - Already correct
- ✓ `instrument_card_list.py` - Already correct
- ✓ `derived_dataset_panel.py` - Already correct
- ✓ `date_range_selector.py` - Already correct
- ✓ `run_readiness_panel.py` - Already correct

## Impact
- **Route 3 Cutover**: The canonical OP tab with card-based UI now launches successfully
- **GUI Tests**: All GUI tests continue to pass (including newly enabled tests from Route 3)
- **Backward Compatibility**: OpTab now has all required signals for integration with ControlStation
- **User Experience**: Desktop UI no longer crashes on startup due to import/signal issues

## Files Changed
1. `src/gui/desktop/widgets/card_selectors/base_card.py` - Added QSpacerItem import
2. `src/gui/desktop/tabs/op_tab.py` - Added missing signals

## Evidence Files Created
1. `hotfix_qt_imports_before.txt` - Problem description
2. `hotfix_qt_imports_after.txt` - Fix description
3. `hotfix_qt_imports_after_make_up.txt` - UI launch verification
4. `hotfix_qt_imports_after_make_check.txt` - Test suite verification
5. `hotfix_summary.md` - This summary

## Status: ✅ COMPLETED
The HOTFIX is complete. The Desktop UI now launches without Qt import or signal errors, and all tests pass.