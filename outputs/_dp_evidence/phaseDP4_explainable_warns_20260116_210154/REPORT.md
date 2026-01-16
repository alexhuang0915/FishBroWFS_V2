# DP4: Explainable WARNs - Implementation Report

**Project:** FishBroWFS_V2 DP4  
**Date:** 2026-01-16T13:06:00Z  
**Commit Hash:** ac1c4b68a3def21d662eb514555c8e32bf100145

## 1. Overview

DP4 implements explainable WARNs via SSOT-backed "Reason Cards" for Data Alignment issues. The goal is to convert opaque WARNs into actionable, human-readable explanations that clearly state why a WARN happened, its impact, and recommended action, without UI recomputation.

## 2. Implemented Reason Cards

### 2.1 DATA_ALIGNMENT_MISSING
- **Code:** `DATA_ALIGNMENT_MISSING`
- **Trigger:** `data_alignment_report.json` missing
- **Severity:** WARN
- **Why:** `data_alignment_report.json` not produced by BUILD_DATA
- **Impact:** Alignment quality cannot be audited; downstream metrics may be less trustworthy
- **Action:** Re-run BUILD_DATA for this job or inspect runner logs to confirm artifact generation
- **Evidence:** artifact expected path
- **Action Target:** `file:///home/fishbro/FishBroWFS_V2/outputs/jobs/{job_id}/data_alignment_report.json`

### 2.2 DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO
- **Code:** `DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO`
- **Trigger:** `forward_fill_ratio > threshold_warn` (0.5 default)
- **Severity:** WARN
- **Why:** Forward-fill ratio {measured} exceeds warning threshold {threshold}
- **Impact:** Data2 contains gaps; model inputs may be biased by forward-filled values
- **Action:** Inspect data_alignment_report.json and consider adjusting Data2 source/coverage or excluding affected windows
- **Evidence:** `data_alignment_report.json` → `$.forward_fill_ratio`
- **Action Target:** `file:///home/fishbro/FishBroWFS_V2/outputs/jobs/{job_id}/data_alignment_report.json#forward_fill_ratio`

### 2.3 DATA_ALIGNMENT_DROPPED_ROWS
- **Code:** `DATA_ALIGNMENT_DROPPED_ROWS`
- **Trigger:** `dropped_rows > 0`
- **Severity:** WARN
- **Why:** Dropped rows {count} > 0
- **Impact:** Data1 and Data2 have mismatched timestamps; some rows excluded from analysis
- **Action:** Review timestamp alignment in data_alignment_report.json and consider adjusting timezone or sampling
- **Evidence:** `data_alignment_report.json` → `$.dropped_rows`
- **Action Target:** `file:///home/fishbro/FishBroWFS_V2/outputs/jobs/{job_id}/data_alignment_report.json#dropped_rows`

## 3. Thresholds Used

- **Forward-fill warning threshold:** 0.5 (existing constant `DATA_ALIGNMENT_FORWARD_FILL_WARN_THRESHOLD` from gate_summary_service)
- **Dropped rows threshold:** > 0 (any non-zero dropped rows triggers WARN)

## 4. Implementation Details

### 4.1 Files Created
- `src/gui/services/reason_cards.py` - ReasonCard datamodel (frozen dataclass)
- `tests/gui/services/test_data_alignment_reason_cards.py` - Unit tests for builder

### 4.2 Files Modified
- `src/gui/services/data_alignment_status.py` - Added builder function and constants
- `src/gui/services/gate_summary_service.py` - Integrated reason cards into data alignment gate
- `src/control/explain_service.py` - Added reason cards to explain payload
- `tests/gate/test_data_alignment_gate.py` - Updated to assert reason cards presence
- `tests/explain/test_data_alignment_disclosure.py` - Updated to assert reason cards in explain

### 4.3 Key Design Decisions
1. **SSOT-only**: All data comes from existing `DataAlignmentStatus` resolver and `data_alignment_report.json`
2. **No UI recompute**: GateSummary and Explain services use same SSOT data
3. **Deterministic ordering**: Cards returned in fixed order (MISSING → HIGH_FF_RATIO → DROPPED_ROWS)
4. **Frozen dataclass**: `ReasonCard` is immutable for thread safety and hashability
5. **Action targets**: Use `file://` URLs for local artifact navigation

## 5. Acceptance Checklist

### ✅ 1. GateSummary returns deterministic reason_cards for Data Alignment WARNs
- **Status:** Implemented
- **Verification:** `tests/gate/test_data_alignment_gate.py` passes
- **Evidence:** Gate details include `reason_cards` list with correct codes

### ✅ 2. Explain payload includes the same reason cards
- **Status:** Implemented
- **Verification:** `tests/explain/test_data_alignment_disclosure.py` passes
- **Evidence:** Explain payload includes `data_alignment_reason_cards` with same cards

### ✅ 3. Every card includes evidence pointer + action target
- **Status:** Implemented
- **Verification:** Builder function sets `evidence_artifact`, `evidence_path`, `action_target`
- **Evidence:** All cards have non-empty evidence fields

### ✅ 4. No UI recompute; all data comes from SSOT artifact/status
- **Status:** Implemented
- **Verification:** No new analytics computation in UI layer
- **Evidence:** GateSummary and Explain use existing `DataAlignmentStatus` resolver

### ✅ 5. `make check` passes with 0 failures
- **Status:** Implemented
- **Verification:** `make check` output shows 0 failures
- **Evidence:** See `rg_make_check.txt`

### ✅ 6. No new root files
- **Status:** Implemented
- **Verification:** All files created within existing directories
- **Evidence:** Root directory unchanged

## 6. Test Results

### 6.1 Unit Tests
```
python3 -m pytest -q tests/gui/services/test_data_alignment_reason_cards.py
```
**Result:** 7 tests passed (see `rg_pytest_dp4.txt`)

### 6.2 Gate Integration Tests
```
python3 -m pytest -q tests/gate/test_data_alignment_gate.py
```
**Result:** 2 tests passed (see `rg_pytest_dp4.txt`)

### 6.3 Explain Integration Tests
```
python3 -m pytest -q tests/explain/test_data_alignment_disclosure.py
```
**Result:** 2 tests passed (see `rg_pytest_dp4.txt`)

### 6.4 Full Test Suite
```
make check
```
**Result:** 1586 passed, 49 skipped, 3 deselected, 11 xfailed, 0 failures (see `rg_make_check.txt`)

## 7. Evidence Files

This evidence bundle includes:
- `SYSTEM_FULL_SNAPSHOT.md` - Comprehensive system snapshot
- `REPORT.md` - This implementation report
- `rg_pytest_dp4.txt` - Output of three pytest verification commands
- `rg_make_check.txt` - Output of `make check`

## 8. Future Extensions

DP4 currently targets Data Alignment only. The architecture supports easy extension to other gate types:

1. **OOM Gate**: Add `build_oom_reason_cards`
2. **Portfolio Admission Gate**: Add `build_portfolio_admission_reason_cards`
3. **Plan Quality Gate**: Add `build_plan_quality_reason_cards`

The `ReasonCard` datamodel is generic and can be reused across all gate types.

## 9. Conclusion

DP4 successfully implements explainable WARNs via SSOT-backed Reason Cards for Data Alignment. All acceptance criteria are met, tests pass, and the implementation follows all non-negotiables (no new root files, no UI recompute, SSOT-only, deterministic messages).

**DP4 STATUS: COMPLETE ✅**
