# UI Master Console Report (OpTab + PTTab)

## OpTab changes
- `src/gui/desktop/tabs/op_tab_refactored.py` implements the Backtest Master Console layout and behavior in `OpTabRefactored` with inputs, live status, monitor console, polling, diagnostics, progress mapping, and stall detection.
- Gating and date range logic is handled in `update_run_state()` and `update_date_range()`, using prepared index (`refresh_prepared_index`) and coverage in `CoverageWorker`.

## PTTab changes
- `src/gui/desktop/tabs/allocation_tab.py` now implements the Portfolio Master Console in `AllocationTab` with component selection, intersection date range, season override, portfolio submission, monitoring, progress, diagnostics, and stall detection.
- Portfolio runs list is driven by `/api/v1/outputs/summary` with job status overlay for submitted jobs in `_refresh_submitted_jobs()`.

## Tests
- `tests/gui_desktop/test_op_tab_cards.py` validates OpTab gating, coverage default, season override, polling, progress mapping, and stall labels.
- `tests/gui_desktop/test_portfolio_tab_master_console.py` validates PTTab component gating, date range intersection, season override, run submission, polling, and progress/stall logic.
