# OpTab Master Console Report

## What changed
- `src/gui/desktop/tabs/op_tab_refactored.py` now renders the Backtest Master Console layout: left input panel, right live status + monitor console. It adds polling, focused-job status, diagnostics, stall detection, and phase-based progress mapping in `OpTabRefactored`.
- `src/gui/desktop/tabs/bar_prepare_tab_ssot.py` now resolves outputs paths via `outputs_root()` to satisfy hardening rules and keep prepared index location consistent with environment overrides.
- `tests/gui_desktop/test_op_tab_cards.py` updated to validate SSOT v1.2 behaviors (gating, date range, polling, stall labels, progress mapping).

## Why
- Align OpTab with SSOT v1.2 requirements for a two-column backtest console, instrument gating by prepared index, date range auto-fill, and realtime monitoring with stall detection.
- Fix hardening guard failures for hardcoded outputs paths and attribute injection.

## Key behaviors implemented
- Prepared instrument filtering and gating in `OpTabRefactored.refresh_prepared_index`, `_get_prepared_instruments`, `_is_prepared`, `update_run_state`.
- Date range auto-fill from prepared coverage / season override in `update_date_range`, `_resolve_full_data_range`, `_resolve_season_range`.
- Live status + monitor console with polling, focus selection, progress mapping, diagnostics, and stall detection in `update_focus_job`, `_progress_for_job`, `_update_stall_label`, `run_diagnostics`.
