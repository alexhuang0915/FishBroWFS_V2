# SYSTEM FULL SNAPSHOT - DP4: Explainable WARNs (GateSummary + Explain SSOT "Reason Cards")

**Project:** FishBroWFS_V2 - DP4: Explainable WARNs  
**Date:** 2026-01-16T13:07:00Z  
**Status:** DP4 IMPLEMENTATION COMPLETE ✅

## EXECUTIVE SUMMARY

The DP4 project has successfully converted opaque WARNs into explainable, actionable, SSOT-backed "Reason Cards" that clearly state:

1. **Why the WARN happened** (rule + measured value + threshold)
2. **Impact** (what downstream result is affected)
3. **Recommended action** (what the user should do next)

All implementation follows strict non-negotiables: no new root files, no analytics recompute in UI, SSOT-only consumption, deterministic messages, terminating verification commands, and evidence stored under `outputs/_dp_evidence/`.

## DP4 IMPLEMENTATION DETAILS

### 1. Reason Cards Datamodel

Created `src/gui/services/reason_cards.py` with frozen dataclass:

```python
@dataclass(frozen=True)
class ReasonCard:
    code: str
    title: str
    severity: Literal["WARN", "FAIL"]
    why: str
    impact: str
    recommended_action: str
    evidence_artifact: str
    evidence_path: str
    action_target: str
```

### 2. Data Alignment Reason Cards Builder

Added to `src/gui/services/data_alignment_status.py`:

- Constants: `DATA_ALIGNMENT_MISSING`, `DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO`, `DATA_ALIGNMENT_DROPPED_ROWS`
- Builder function: `build_data_alignment_reason_cards(job_id, status, warn_forward_fill_ratio)`
- Deterministic ordering: MISSING → HIGH_FF_RATIO → DROPPED_ROWS
- Uses existing SSOT: `DataAlignmentStatus` and `data_alignment_report.json` fields

### 3. GateSummary Service Integration

Updated `src/gui/services/gate_summary_service.py`:

- Import reason cards builder and constants
- Modified `_fetch_data_alignment_gate` to build reason cards
- Include `reason_cards` list in gate details under "Data Alignment" section
- No recomputation - uses existing status resolver

### 4. Explain Service Integration

Updated `src/control/explain_service.py`:

- Import reason cards builder and constants
- Added reason cards building in `_build_data_alignment_disclosure`
- Include `data_alignment_reason_cards` in explain payload
- No recomputation - uses same SSOT as GateSummary

### 5. Implemented Reason Cards

#### 5.1 DATA_ALIGNMENT_MISSING
- **Trigger**: `data_alignment_report.json` missing
- **Severity**: WARN
- **Why**: `data_alignment_report.json` not produced by BUILD_DATA
- **Impact**: Alignment quality cannot be audited; downstream metrics may be less trustworthy
- **Action**: Re-run BUILD_DATA for this job or inspect runner logs to confirm artifact generation
- **Evidence**: artifact expected path

#### 5.2 DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO
- **Trigger**: `forward_fill_ratio > threshold_warn` (0.5 default)
- **Severity**: WARN
- **Why**: Forward-fill ratio 0.75 exceeds warning threshold 0.5
- **Impact**: Data2 contains gaps; model inputs may be biased by forward-filled values
- **Action**: Inspect data_alignment_report.json and consider adjusting Data2 source/coverage or excluding affected windows
- **Evidence**: `data_alignment_report.json` → `$.forward_fill_ratio`

#### 5.3 DATA_ALIGNMENT_DROPPED_ROWS
- **Trigger**: `dropped_rows > 0`
- **Severity**: WARN
- **Why**: Dropped rows 42 > 0
- **Impact**: Data1 and Data2 have mismatched timestamps; some rows excluded from analysis
- **Action**: Review timestamp alignment in data_alignment_report.json and consider adjusting timezone or sampling
- **Evidence**: `data_alignment_report.json` → `$.dropped_rows`

### 6. SSOT Design Compliance

- **No new root files**: All files created/modified within existing directories
- **No UI recompute**: All data comes from SSOT artifacts/services
- **Deterministic messages**: Stable keys + stable phrasing
- **Evidence pointers**: Each card includes `evidence_artifact` and `evidence_path`
- **Action targets**: Each card includes `action_target` (path/URL to open artifact)

## FILES CREATED/MODIFIED

### New Files
```
src/gui/services/reason_cards.py                    # ReasonCard datamodel
tests/gui/services/test_data_alignment_reason_cards.py  # Unit tests for builder
```

### Modified Files
```
src/gui/services/data_alignment_status.py           # Added builder + constants
src/gui/services/gate_summary_service.py            # Integrated reason cards
src/control/explain_service.py                      # Added reason cards to explain
tests/gate/test_data_alignment_gate.py              # Updated gate tests
tests/explain/test_data_alignment_disclosure.py     # Updated explain tests
```

## TEST SUITE VERIFICATION

### Unit Tests
- `tests/gui/services/test_data_alignment_reason_cards.py`: 7 tests covering all card scenarios
- **Result**: All tests pass

### Gate Integration Tests
- `tests/gate/test_data_alignment_gate.py`: Updated to assert reason cards presence
- **Result**: All tests pass

### Explain Integration Tests
- `tests/explain/test_data_alignment_disclosure.py`: Updated to assert reason cards in explain payload
- **Result**: All tests pass

### Full Test Suite
```
make check
```
**Result**: All tests pass with 0 failures (see `rg_make_check.txt`)

## VERIFICATION COMMANDS OUTPUT

### 1. Reason Cards Unit Tests
```
python3 -m pytest -q tests/gui/services/test_data_alignment_reason_cards.py
```
**Result**: 7 passed (see `rg_pytest_dp4.txt`)

### 2. Gate Integration Tests
```
python3 -m pytest -q tests/gate/test_data_alignment_gate.py
```
**Result**: All tests pass (see `rg_pytest_dp4.txt`)

### 3. Explain Integration Tests
```
python3 -m pytest -q tests/explain/test_data_alignment_disclosure.py
```
**Result**: All tests pass (see `rg_pytest_dp4.txt`)

### 4. Make Check
```
make check
```
**Result**: All tests pass with 0 failures (see `rg_make_check.txt`)

## ACCEPTANCE CRITERIA VERIFICATION

### ✅ 1. GateSummary returns deterministic reason_cards for Data Alignment WARNs
- **Status**: Implemented for missing artifact, high FF ratio, dropped rows
- **Evidence**: Gate tests verify card presence and content

### ✅ 2. Explain payload includes the same reason cards
- **Status**: Explain service includes `data_alignment_reason_cards` in payload
- **Evidence**: Explain tests verify card presence

### ✅ 3. Every card includes evidence pointer + action target
- **Status**: All cards have `evidence_artifact`, `evidence_path`, `action_target`
- **Evidence**: Builder function sets these fields

### ✅ 4. No UI recompute; all data comes from SSOT artifact/status
- **Status**: GateSummary and Explain use existing `DataAlignmentStatus` resolver
- **Evidence**: No new analytics computation in UI layer

### ✅ 5. `make check` passes with 0 failures
- **Status**: All tests pass
- **Evidence**: `rg_make_check.txt` shows 0 failures

### ✅ 6. No new root files
- **Status**: All files created within existing directories
- **Evidence**: Root directory unchanged

## EVIDENCE BUNDLE CONTENTS

This evidence bundle (`outputs/_dp_evidence/phaseDP4_explainable_warns_20260116_210154/`) includes:

1. **SYSTEM_FULL_SNAPSHOT.md** - This document
2. **REPORT.md** - Detailed implementation report with acceptance checklist
3. **rg_pytest_dp4.txt** - Output of three pytest verification commands
4. **rg_make_check.txt** - Output of `make check`

## TECHNICAL IMPLEMENTATION NOTES

### Threshold Consistency
- Used existing threshold `DATA_ALIGNMENT_FORWARD_FILL_WARN_THRESHOLD` (0.5) from gate_summary_service
- No new configuration introduced

### Serialization
- `ReasonCard` objects converted to dict for JSON serialization in gate details and explain payload
- Frozen dataclass ensures immutability

### Deterministic Ordering
Cards returned in fixed order:
1. `DATA_ALIGNMENT_MISSING` (if triggered)
2. `DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO` (if triggered)
3. `DATA_ALIGNMENT_DROPPED_ROWS` (if triggered)

### Action Target Format
- Uses `file://` URL scheme for local artifacts
- Example: `file:///home/fishbro/FishBroWFS_V2/outputs/jobs/{job_id}/data_alignment_report.json`

## FUTURE EXTENSIONS

DP4 currently targets Data Alignment only. The architecture supports easy extension to other gate types:

1. **OOM Gate**: Add `build_oom_reason_cards`
2. **Portfolio Admission Gate**: Add `build_portfolio_admission_reason_cards`
3. **Plan Quality Gate**: Add `build_plan_quality_reason_cards`

The `ReasonCard` datamodel is generic and can be reused across all gate types.

## CONCLUSION

DP4 successfully implements explainable WARNs via SSOT-backed Reason Cards for Data Alignment. The implementation:

1. **Converts opaque WARNs** into actionable, human-readable explanations
2. **Maintains SSOT compliance** with no UI recomputation
3. **Provides deterministic messages** with stable keys and phrasing
4. **Includes evidence pointers** for direct artifact inspection
5. **Passes all verification tests** with 0 failures
6. **Maintains root hygiene** with no new root files

The system now provides clear, actionable explanations for Data Alignment WARNs in both GateSummary and Explain interfaces, improving user understanding and enabling faster issue resolution.

**DP4 STATUS: COMPLETE WITH ALL ACCEPTANCE CRITERIA MET ✅**
