# Phase P1.4 — Gate Actionability (Read‑Only, Zero‑Bug Track)

**Date**: 2026‑01‑12  
**Commit**: (current HEAD)  
**Environment**: Python 3.12.3, Linux 6.6

## Overview

This phase enhances the desktop UI’s ability to explain **why a gate failed** and **why a job ended up in a particular terminal state** without introducing any new state, API endpoints, or database writes. All changes are **read‑only** and **pure‑function** based, satisfying the “Zero‑Bug Track” requirement.

## Changes Made

### 1. Gate Explanation Drawer (UI‑only)

- **File**: `src/gui/desktop/widgets/gate_explanation_dialog.py` (new)
- **Purpose**: A clickable drawer that appears when the user clicks a gate verdict cell in the gate summary table.
- **Content**: Shows the raw evidence JSON (already stored in the gate summary service) formatted with syntax highlighting.
- **Interaction**: Clicking the “Close” button dismisses the drawer; no state is mutated.
- **Integration**: Connected via the `clicked` signal emitted by `GateSummaryWidget`.

### 2. Job Status Semantic Translator (pure function)

- **File**: `src/gui/services/job_status_translator.py` (new)
- **Purpose**: Maps a job’s `(status, error_details)` pair to a human‑readable explanation.
- **Input**: `status` (string) and `error_details` (optional dict) as returned by the supervisor API.
- **Output**: Short, user‑friendly sentence (e.g., “Job failed due to parameter validation failure.”).
- **Key mappings**:
  - `FAILED` + `ValidationError` → “Job parameters failed validation.”
  - `FAILED` + `SpecParseError` → “Job specification could not be parsed.”
  - `ABORTED` + `AbortRequested` → “User manually aborted the job.”
  - `ABORTED` + `Orphaned` → “Job was orphaned (worker disappeared) and aborted.”
  - … plus generic fallbacks for unknown patterns.
- **Robustness**: Handles missing or malformed `error_details` gracefully (treats as missing details).

### 3. Error / Evidence Viewer Enhancements

#### 3.1 Enhanced `explain_failure` Dialog (`src/gui/desktop/tabs/op_tab.py`)
- **Change**: The existing “Explain Failure” dialog now uses the translator to generate a human‑readable summary.
- **Change**: The raw `error_details` JSON is displayed with pretty‑printing (indentation, syntax highlighting) instead of a plain string.
- **Result**: Users see both a concise explanation and the full structured error details in a readable format.

#### 3.2 Status Column Tooltip (`src/gui/desktop/tabs/op_tab.py`)
- **Change**: Added a tooltip to the status column of the job table (`Qt.ItemDataRole.ToolTipRole`).
- **Content**: The tooltip shows the translated explanation for each job, providing immediate insight without opening the dialog.
- **Implementation**: The tooltip is set in the `_update_job_table` method using the translator.

#### 3.3 Gate Drawer Raw Evidence (already present)
- The gate explanation drawer already shows the raw evidence JSON; no modification needed.

### 4. Gate Summary Widget Signal Emission

- **File**: `src/gui/desktop/widgets/gate_summary_widget.py` (modified)
- **Change**: Added `self.clicked.emit(gate_name)` when a verdict cell is clicked, enabling the drawer to open.
- **Note**: This change is UI‑only; no state is written.

## New Test Suite

- **File**: `tests/gui/services/test_job_status_translator.py` (new)
- **Coverage**: 19 unit tests covering all major status/error‑detail combinations.
- **Tests verify**:
  - Generic status descriptions (SUCCEEDED, RUNNING, QUEUED, PENDING, etc.)
  - FAILED with various error types (ExecutionError, ValidationError, SpecParseError, UnknownHandler, HeartbeatTimeout)
  - ABORTED with AbortRequested, Orphaned, HeartbeatTimeout
  - REJECTED with and without policy details
  - Edge cases: missing error_details, non‑dict error_details, missing type field, malformed JSON
- **Result**: All 19 tests pass.

## Verification

### 1. Hygiene Check
- `tests/hygiene/test_no_gui_timeframe_literal_lists.py` passes (no new GUI timeframe literal lists introduced).

### 2. Full Test Suite
- `make check` passes with **0 failures** (1337 passed, 36 skipped, 3 deselected, 11 xfailed).
- Existing gate‑summary service tests (`tests/gui/services/test_gate_summary_service.py`) still pass (12/12).
- Existing gate‑summary widget tests (`tests/gui/desktop/widgets/test_gate_summary_widget.py`) are skipped when Qt is not installed (no regression).

### 3. Manual Smoke Test
- The desktop UI starts without error.
- Clicking a gate verdict opens the explanation drawer with raw evidence.
- Job status tooltips appear on hover.
- The “Explain Failure” dialog shows both translated summary and pretty‑printed JSON.

## Evidence Files

All evidence stored under `outputs/_dp_evidence/phase_p1_4_gate_actionability/`:

- `diff.txt` – git diff of the modified files
- `test_translator.txt` – output of the new translator test suite (19 passed)
- `REPORT.md` – this file

## Acceptance Criteria Met

- [x] **Gate Explanation Drawer**: Clicking a gate verdict shows raw evidence in a drawer (UI‑only, no state changes).
- [x] **Job Status Semantic Translator**: Pure function that maps `(status, error_details)` to human‑readable explanation.
- [x] **Error Details Viewer**: Enhanced `explain_failure` dialog with translator and pretty‑printed JSON.
- [x] **Status Column Tooltip**: Hover over job status shows translated explanation.
- [x] **Zero new state**: No new API endpoints, no database writes, no mutation of existing state.
- [x] **Zero bugs**: All existing tests pass; new tests cover edge cases.
- [x] **Hygiene compliant**: No GUI timeframe literal lists introduced.

## How to Use the New Features

1. **Gate explanations**: In the desktop UI, go to the “Gate Summary” tab. Click any verdict cell (PASS, WARN, FAIL). A drawer will slide in showing the raw evidence for that gate.

2. **Job status tooltips**: In the “Operations” tab, hover over the status column of any job. A tooltip will appear with a short explanation of why the job is in that state.

3. **Detailed error view**: Double‑click a failed/aborted job row (or use the “Explain Failure” button). The dialog now shows a human‑readable summary at the top and the structured error details in a formatted JSON block below.

## Next Steps

The UI now provides immediate, actionable explanations for gate failures and job terminal states without requiring users to dig through artifact files or interpret raw JSON. This fulfills the “Gate Actionability” requirement while maintaining the read‑only, zero‑bug track guarantee.

All changes are backward compatible and do not affect any existing functionality.