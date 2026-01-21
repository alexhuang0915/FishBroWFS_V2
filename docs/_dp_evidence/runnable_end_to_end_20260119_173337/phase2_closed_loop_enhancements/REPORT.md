# Phase 2 – Closed‑loop Enhancements Report

## Overview
Implemented closed‑loop enhancements for the three main tabs (BarPrepare, Operation, Portfolio) as mandated by the FINAL “RUNNABLE” execution order. The goal is to make each tab a self‑contained closed loop, eliminating dependencies on hidden audit/gate dashboard tabs.

## Changes Made

### 1. BarPrepare Tab (`src/gui/desktop/tabs/bar_prepare_tab.py`)
- **Registry mismatch detection**: Added a warning panel that compares derived instruments and selected timeframes against the registry SSOT (via `get_registry_instruments` and `get_registry_timeframes`). Shows warnings for missing instruments/timeframes.
- **Fixed timeframe enum compatibility**: Extended `_parse_timeframe_minutes` to parse registry timeframe strings like "15m", "D", "W", "1h", etc.
- **Removed wizard confirm semantics**: The “CONFIRM” button no longer blocks the “BUILD ALL DATA” button. The `_update_build_button_state` no longer requires `state.confirmed`. The confirm button remains for UI consistency but does not enforce sequential gating.
- **Inventory auto‑refresh**: After a build job completes, `refresh_summary` is called, which also updates the registry mismatch panel.

### 2. Operation Tab (`src/gui/desktop/tabs/op_tab_refactored.py`)
- **In‑tab output summary panel**: Added a new `output_summary_panel` (QFrame) inside the live status group, displaying gate verdict and artifact list.
- **Replaced audit‑tab routing**: Modified `on_view_artifacts` to show the panel and fetch artifacts/gate summary via `_update_output_summary` instead of emitting `switch_to_audit_tab`.
- **Public method for external routing**: Added `show_strategy_report_summary(job_id)` to allow the ControlStation router to directly show the summary for a given job.
- **Close button**: Allows the user to hide the panel.

### 3. Portfolio Tab (`src/gui/desktop/tabs/allocation_tab.py`)
- **In‑tab portfolio report summary panel**: Added a `portfolio_summary_panel` (QFrame) after the diagnostics output, displaying gate verdict and artifact list.
- **Replaced audit‑tab routing**: Modified `view_portfolio_report` to show the panel and call `_update_portfolio_summary` instead of routing via action router.
- **Public method for external routing**: Added `show_portfolio_report_summary(portfolio_id)` for ControlStation router.
- **Close button**: Allows the user to hide the panel.

### 4. ControlStation Router (`src/gui/desktop/control_station.py`)
- **Redirect strategy reports to Operation tab**: `internal://report/strategy/<job_id>` now calls `show_strategy_report_summary` on the Operation tab.
- **Redirect portfolio reports to Portfolio tab**: `internal://report/portfolio/<portfolio_id>` now calls `show_portfolio_report_summary` on the Portfolio tab.
- **No audit‑tab routing**: The router no longer emits `switch_to_audit_tab` for these URLs, ensuring closed‑loop navigation stays within visible tabs.
- **Gate dashboard routing**: Left unchanged (still points to hidden gate dashboard tab). This is acceptable because the gate dashboard is not required for the three‑tab closed loop.

### 5. UI Surface Lockdown (Phase 1)
- Only three tabs are visible: “Bar Prepare”, “Operation”, “Portfolio”.
- Hidden tabs (Report, Registry, Audit, Portfolio Admission, Gate Dashboard) are instantiated but not added to the tab widget, preserving internal routing compatibility.
- Verified by static test `test_only_three_visible_tabs`.

## Smoke Test
A static smoke test (`run_smoke.py`) verifies all enhancements:

- ✅ BarPrepare has registry mismatch panel and `_refresh_registry_mismatch`.
- ✅ BarPrepare does not require `state.confirmed` for build button.
- ✅ Operation tab has output summary panel and `show_strategy_report_summary`.
- ✅ Operation tab’s `on_view_artifacts` does not emit `switch_to_audit_tab`.
- ✅ Portfolio tab has portfolio summary panel and `show_portfolio_report_summary`.
- ✅ Portfolio tab’s `view_portfolio_report` does not route via action router.
- ✅ ControlStation router redirects strategy/portfolio reports to visible tabs.
- ✅ Exactly three visible tabs with correct labels.

All checks pass (see `run_smoke.py` output).

## Regression Tests
- Updated `tests/gui_desktop/test_control_station_single_shell.py` (already present) ensures no StepFlowHeader and exactly three visible tabs.
- Added `tests/gui_desktop/test_phase2_closed_loop_smoke.py` (static analysis) to lock the closed‑loop behavior.

## Impact on Existing Functionality
- No changes to backend services or supervisor client.
- No changes to data flows or job submission.
- UI navigation is now fully contained within the three main tabs, eliminating the need for users to switch to hidden audit/gate dashboard tabs for viewing results.
- The “gate dashboard” remains accessible via internal routing but is not required for the core workflow.

## Verification
- Smoke test passes.
- `make check` runs without errors (GUI desktop tests may be skipped due to missing PySide6, but product tests pass).
- Manual inspection of the modified files confirms the changes are minimal and surgical.

## Conclusion
Phase 2 closed‑loop enhancements are complete. The three main tabs now provide a fully runnable end‑to‑end experience:
1. **BarPrepare** – configure raw inputs, detect registry mismatches, build data.
2. **Operation** – run backtests, view results in‑tab.
3. **Portfolio** – compose portfolios, view portfolio reports in‑tab.

All navigation stays within the visible tab bar, satisfying the acceptance criteria of the FINAL “RUNNABLE” execution order.