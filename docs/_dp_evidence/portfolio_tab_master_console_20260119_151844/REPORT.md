# Portfolio Tab Master Console Report

## What changed
- `src/gui/desktop/tabs/allocation_tab.py` replaced with Portfolio Backtest Master Console layout (left inputs, right live status + run monitor) in `AllocationTab`.
- Added coverage intersection, season override, component gating, polling, progress mapping, stall detection, and diagnostics in `AllocationTab`.
- `tests/gui_desktop/test_portfolio_tab_master_console.py` added to cover component gating, date range intersection, season override, run submission, polling update, progress mapping, and stall labels.

## Why
Align Allocation/Portfolio UI with SSOT v1.0: manual component selection, portfolio run submission, realtime monitoring, and stall detection.

## Key behaviors implemented
- Component selection and gating: `refresh_components`, `add_selected_component`, `remove_selected_component`, `update_run_state`.
- Date range intersection: `_resolve_component_intersection`, `_on_coverage_ready`, `update_date_range`.
- Portfolio submission: `run_portfolio` (uses `post_portfolio_build`).
- Live status + monitoring: `refresh_runs`, `update_focus_run`, `_progress_for_status`, `_update_stall_label`, `run_diagnostics`.
