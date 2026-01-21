# Phase 1 – UI Surface Lockdown (3 Main Tabs Only)

## Objective
Reduce the visible UI surface to exactly three main tabs: **Bar Prepare**, **Operation**, **Portfolio**. Keep hidden tabs (Report, Registry, Audit, Portfolio Admission, Gate Dashboard) instantiated but not added to the tab widget to preserve internal routing compatibility.

## Changes Made

### 1. Modified `src/gui/desktop/control_station.py`

#### a) Tab instantiation (lines 164‑173)
- Keep all eight tab objects (for backward compatibility).
- Add only three tabs to `self.tab_widget`:
  - `self.bar_prepare_tab` → label "Bar Prepare"
  - `self.op_tab` → label "Operation"
  - `self.allocation_tab` → label "Portfolio"
- Hidden tabs: `report_tab`, `registry_tab`, `audit_tab`, `portfolio_admission_tab`, `gate_summary_dashboard_tab` are instantiated but not added.

#### b) Tab mapping dictionaries (lines 188‑198)
- `_tab_index_by_tool` maps only visible tabs to their indices (0,1,2).
- `_tab_by_tool` includes all eight tools (visible + hidden) so that internal routing can still find the widget instances.

#### c) Step‑tool mapping (lines 200‑218)
- Updated `_step_tools` and `_step_default_tool` to route steps that previously pointed to removed tabs (Strategy, Decision, Export) to the **Operation** tab.
- This ensures step navigation still works (though step flow header is removed).

#### d) Signal connections (lines 220‑246)
- Restored connections for hidden tabs (log signals) to avoid AttributeError.
- Kept connections for the three main tabs.

#### e) `handle_artifact_state` (lines 255‑263)
- Restored registry‑tab refresh when artifact state becomes READY (registry tab exists as hidden).

#### f) `on_tab_changed` (lines 277‑283)
- Updated `tab_names` list to reflect the three visible tabs.

### 2. Added Regression Test

File: `tests/gui_desktop/test_control_station_single_shell.py`
- Added `test_control_station_has_only_three_visible_tabs()`:
  - Static analysis that verifies exactly three `addTab` calls on `self.tab_widget`.
  - Validates the tab labels are "Bar Prepare", "Operation", "Portfolio".
- This test locks the UI surface to three tabs and will fail if extra tabs are added.

## Verification

### Static Verification
- Run the new test (skipped if PySide6 missing, but static analysis passes).
- Manual inspection of the modified file confirms only three `addTab` calls.

### Runtime Verification (Manual)
- Launch `make up` – the desktop window should show exactly three tabs.
- Each tab should be functional (Bar Prepare, Operation, Portfolio).
- Hidden tabs are not visible but internal routing (e.g., audit report opening) should not crash (though the UI won't switch to a hidden tab).

## Impact on Existing Tests
- No existing tests depend on the exact number of tabs in `ControlStation` (except `test_analytics_tabs_clickable` which uses `AnalysisWidget`, not `ControlStation`).
- All static‑analysis tests (`test_control_station_single_shell`, `test_wayland_safe_geometry`) continue to pass.
- GUI tests that rely on hidden tabs (e.g., audit tab) will still work because the tab instances exist.

## Next Steps (Phase 2)
- **Closed‑loop enhancements** for each of the three main tabs:
  - BarPrepare: fix registry mismatch, enforce fixed timeframe enum.
  - Operation: bring output summary into same tab (no audit‑tab routing).
  - Portfolio: bring output summary into same tab (no audit‑tab routing).
- Adjust internal routing (`handle_router_url`, `handle_open_gate_dashboard`) to redirect “audit”, “gate_dashboard”, “report” targets to appropriate visible tabs.
- Implement 3‑gate smoke test.

## Evidence Files
- This REPORT.md
- Modified `src/gui/desktop/control_station.py` (diff available in git)
- Updated test file `tests/gui_desktop/test_control_station_single_shell.py`

## Commit Ready
The changes are minimal, surgical, and focused solely on UI surface reduction. No backend or supervisor logic is altered.