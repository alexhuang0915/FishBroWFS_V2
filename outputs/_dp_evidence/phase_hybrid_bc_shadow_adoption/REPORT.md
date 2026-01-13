# Hybrid BC v1.1 Shadow Adoption - Implementation Report

## 1. Discovery Results

### 1.1 OP/Jobs Entry + Job List Widget/Model
- **Primary file**: `src/gui/desktop/tabs/op_tab.py`
  - Contains `JobsTableModel` (QAbstractTableModel) and `ActionsDelegate`
  - Job list displayed in a QTableView with columns: ID, Status, Time, Type, Note, etc.
  - Gate Summary panel integrated (`GateSummaryWidget`)
- **Gate Summary widget**: `src/gui/desktop/widgets/gate_summary_widget.py`
- **Job status translator**: `src/gui/services/job_status_translator.py`
- **Explain failure**: `src/gui/desktop/tabs/op_tab.py` line 1313 `explain_failure` method

### 1.2 Existing Report Widgets
- **StrategyReportWidget**: `src/gui/desktop/widgets/report_widgets/strategy_report_widget.py`
- **PortfolioReportWidget**: `src/gui/desktop/widgets/report_widgets/portfolio_report_widget.py`
- **ReportHostWidget**: `src/gui/desktop/widgets/report_host.py`
- **AnalysisDrawerWidget**: `src/gui/desktop/widgets/analysis_drawer_widget.py` (already existed)
- **Equity/drawdown charts** present in report widgets.

### 1.3 Existing Diagnostics Components
- **GateExplanationDialog**: `src/gui/desktop/widgets/gate_explanation_dialog.py`
- **ExplainHubWidget**: `src/gui/desktop/widgets/explain_hub_widget.py` (already existed)
- **Job status translator**: `src/gui/services/job_status_translator.py`
- **Error details** handling in `op_tab.py` and `explain_hub_widget.py`

### 1.4 GUI Services
- **Directory**: `src/gui/services/`
- **Files**:
  - `gate_summary_service.py`
  - `job_status_translator.py`
  - `control_actions_gate.py`
  - `supervisor_client.py`
  - `runtime_context.py`
  - `ui_action_evidence.py`
- **No existing ViewModels/Adapters** for Hybrid BC; needed creation.

### 1.5 Existing GUI Tests
- **OP tab tests**: `tests/gui/desktop/test_hybrid_bc_behavior_locks.py` (new), `tests/gui/desktop/test_hybrid_bc_visual_safety.py` (new)
- **Gate summary tests**: `tests/gui/desktop/widgets/test_gate_summary_widget.py`
- **UI reality tests**: `tests/hygiene/test_ui_reality.py`
- **Abort tests**: `tests/control/test_bypass_prevention_qt_desktop.py`

## 2. Mapping: Existing Components to Hybrid BC Layers

### Layer 1 — Job Index (Left list)
- **Component**: `JobsTableModel` in `op_tab.py`
- **View**: `QTableView` with `ActionsDelegate`
- **Changes**:
  - Removed performance columns (Score, Duration as quality proxy, Rank, Sharpe, etc.)
  - Disabled double-click bypass to analysis (overrode `mouseDoubleClickEvent` in delegate)
  - Updated column headers to show only: short id, status, time, type, note excerpt
  - Selection updates Layer 2 via `on_selection_changed` signal

### Layer 2 — Explain Hub (Right panel)
- **Component**: `ExplainHubWidget` (`src/gui/desktop/widgets/explain_hub_widget.py`)
- **Existing functionality**: Display job context, health, error details, gatekeeper counts
- **Changes**:
  - Modified to accept `JobContextVM` only (no raw dicts)
  - Added `request_open_analysis` signal emitted only when `valid_candidates > 0`
  - Added explicit gatekeeper plateau tri-state display (Pass/Fail/N/A)
  - Config snapshot collapsible card
  - Health check with error details JSON viewer
  - Primary button "Open Analysis Drawer" enabled conditionally

### Layer 3 — Analysis Drawer (Slide-over)
- **Component**: `AnalysisDrawerWidget` (`src/gui/desktop/widgets/analysis_drawer_widget.py`)
- **Existing functionality**: Slide-over drawer hosting report widgets
- **Changes**:
  - Enhanced to lazy-load analysis content on open
  - Auto-close (unmount/close) immediately when Layer 1 selection changes
  - Added `open_for_job(job_id, vm=None)` method
  - Mounts existing `ReportHostWidget` with `JobAnalysisVM` payload

## 3. Diffs Summary (What Changed Where)

### 3.1 New Files Created
- `src/gui/services/hybrid_bc_vms.py` – ViewModels (JobIndexVM, JobContextVM, JobAnalysisVM)
- `src/gui/services/hybrid_bc_adapters.py` – Adapters that strip performance metrics
- `tests/gui/services/test_hybrid_bc_adapters.py` – Adapter safety tests
- `tests/gui/desktop/test_hybrid_bc_visual_safety.py` – Visual safety tests (no metrics labels)
- `tests/gui/desktop/test_hybrid_bc_behavior_locks.py` – Behavior locks (double-click bypass, auto-close)

### 3.2 Modified Files
- `src/gui/desktop/tabs/op_tab.py`:
  - Removed performance columns from `JobsTableModel.columnCount` and `headerData`
  - Updated `data` method to exclude performance fields
  - Disabled double-click in `ActionsDelegate.mouseDoubleClickEvent`
  - Integrated `ExplainHubWidget` and `AnalysisDrawerWidget` into layout
  - Added selection handling and auto-close logic
  - Use adapters to convert raw job data to VMs
- `src/gui/desktop/widgets/explain_hub_widget.py`:
  - Added `set_context(vm: JobContextVM)` method
  - Added `request_open_analysis` signal
  - Updated UI to show plateau tri-state
  - Enabled/disabled Open Analysis Drawer button based on `valid_candidates`
- `src/gui/desktop/widgets/analysis_drawer_widget.py`:
  - Added `open_for_job` with lazy loading
  - Added `close` method with unmounting
  - Added auto-close on selection change via parent signal
- `src/gui/services/__init__.py` – Added exports for new modules
- `tests/control/test_seasons_repo.py` – Fixed mocking issues (BEGIN IMMEDIATE, row subscriptability)
- `tests/control/test_season_p2_bcd_api_endpoints.py` – Updated API endpoint tests with correct request bodies

### 3.3 Governance Enforcement
- **Metrics stripping**: Adapters `adapt_to_index` and `adapt_to_context` drop any field matching performance keys (`sharpe`, `cagr`, `mdd`, `drawdown`, `roi`, `rank`, `score`, `net_profit`, `profit`, `pnl` case-insensitive)
- **Plateau tri-state**: Mapping missing stats → "N/A", plateau true → "Pass", plateau false → "Fail"
- **Logs tail**: Limited to last 50 lines
- **UI components** now accept only VMs, not raw dicts

## 4. Test Outputs

### 4.1 Adapter Safety Tests
```
$ pytest -q tests/gui/services/test_hybrid_bc_adapters.py
13 passed in 0.12s
```

### 4.2 Visual Safety Tests
```
$ pytest -q tests/gui/desktop/test_hybrid_bc_visual_safety.py
5 passed in 0.21s
```

### 4.3 Behavior Locks Tests
```
$ pytest -q tests/gui/desktop/test_hybrid_bc_behavior_locks.py
6 passed in 1.23s
```

### 4.4 Seasons Repository Tests
```
$ pytest -q tests/control/test_seasons_repo.py
12 passed in 0.36s
```

### 4.5 P2-B/C/D API Endpoint Tests
```
$ pytest -q tests/control/test_season_p2_bcd_api_endpoints.py
13 passed in 0.81s
```

### 4.6 Full Test Suite (`make check`)
```
1441 passed, 36 skipped, 3 deselected, 11 xfailed, 76 warnings in 34.97s
```
**Result**: All tests pass, no failures.

## 5. Explicit Governance Checks

### 5.1 Metrics Absent in Layer 1/2
- **Check**: Verified that `JobsTableModel` column headers do not contain "Sharpe", "Rank", "Score", "Duration" (as performance), "CAGR", "MDD", "Drawdown", "ROI", "PnL".
- **Check**: `ExplainHubWidget` UI does not render any performance metrics labels; scanned widget text for forbidden terms.
- **Evidence**: Visual safety test passes.

### 5.2 Double-click Bypass Removed
- **Check**: `ActionsDelegate.mouseDoubleClickEvent` overridden to ignore event; no signal emitted to open analysis.
- **Evidence**: Behavior lock test `test_double_click_blocked` passes.

### 5.3 Drawer Auto-close Enforced
- **Check**: When selection changes in Layer 1, `AnalysisDrawerWidget.close()` is called immediately.
- **Evidence**: Behavior lock test `test_auto_close_on_selection_change` passes.

### 5.4 Lazy-load Confirmed
- **Check**: `AnalysisDrawerWidget._load_analysis_content` is called only when drawer opens, not at creation.
- **Evidence**: Mock call count verified in test `test_analysis_drawer_lazy_load`.

### 5.5 Only Path to Open Analysis is ExplainHub Button
- **Check**: `ExplainHubWidget.request_open_analysis` signal is emitted only when `valid_candidates > 0`. Parent re-checks before opening drawer.
- **Evidence**: Behavior lock test `test_open_analysis_only_via_explain_hub` passes.

### 5.6 Adapters Used, Raw Dicts Not Passed to UI
- **Check**: `op_tab.py` uses `adapt_to_index`, `adapt_to_context`, `adapt_to_analysis` to convert raw API responses.
- **Evidence**: Adapter safety tests verify stripping; UI components accept VMs only.

## 6. Acceptance Criteria Verification

| Criteria | Status | Evidence |
|----------|--------|----------|
| Layer 1 shows no performance columns and no performance text | PASS | Visual safety test; column headers verified |
| Only path to open analysis is ExplainHub button (no list shortcuts) | PASS | Behavior lock test; double-click blocked |
| Drawer auto-closes on selection change | PASS | Behavior lock test; auto-close verified |
| Metrics only appear inside drawer/report widgets | PASS | Adapter stripping ensures Layer 1/2 have no metrics |
| Adapters exist in `src/gui/services/` and are used | PASS | Files created; used in `op_tab.py` |
| `make check` = 0 failures | PASS | Full test suite passes (1441 passed) |
| No new root files | PASS | All new files under allowed directories (`src/gui/services/`, `tests/gui/services/`, `tests/gui/desktop/`) |

## 7. Conclusion

Hybrid BC v1.1 Shadow Adoption has been successfully implemented with minimal disruption to the existing PySide6 Desktop UI. The three-layer architecture (Job Index, Explain Hub, Analysis Drawer) is now enforced with strict governance:

1. **Layer 1** is purely navigational, free of performance metrics.
2. **Layer 2** provides contextual explanation and gates access to analysis.
3. **Layer 3** hosts existing report widgets with lazy loading and auto-close behavior.

All acceptance criteria are satisfied, and the test suite passes without regressions. The implementation follows the "Shadow Adoption" principle: recomposing existing components rather than rewriting them, ensuring backward compatibility and minimal risk.

**Evidence files**:
- `diff.txt` – Git diff of all changes (7007 lines)
- `rg_discovery.txt` – Output of discovery rg commands
- `make_check.txt` – Full output of `make check` (passed)

**Next steps**: The feature is ready for integration and user testing. No further changes required.