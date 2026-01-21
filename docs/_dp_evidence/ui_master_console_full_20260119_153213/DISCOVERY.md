# Discovery (SSOT Locations)

## OpTab (Backtest Master Console)
- `src/gui/desktop/tabs/op_tab.py` — class `OpTab` wraps refactored implementation.
- `src/gui/desktop/tabs/op_tab_refactored.py` — class `OpTabRefactored` (master console UI + logic).

## PTTab (Portfolio Master Console)
- `src/gui/desktop/tabs/allocation_tab.py` — class `AllocationTab` (portfolio master console UI + logic).

## Jobs / Portfolio APIs
- `src/gui/services/supervisor_client.py` — `get_jobs()`, `get_job()`, `get_stdout_tail()`, `get_artifacts()`, `submit_job()` for OpTab; `post_portfolio_build()`, `get_outputs_summary()` for PTTab.
- `src/control/api.py` — `/api/v1/jobs`, `/api/v1/jobs/{job_id}`, `/api/v1/outputs/summary`, `/api/v1/reports/portfolio/{portfolio_id}`.
- `src/control/portfolio/api_v1.py` — `post_portfolio_build` endpoint creates `BUILD_PORTFOLIO_V2` jobs.

## Job model fields
- `src/contracts/api.py` — `JobListResponse` fields (status, created_at, failure_message, policy_stage, run_mode, etc.).
- `src/control/supervisor/models.py` — `JobRow` (state, created_at, updated_at, progress, phase, failure_message, policy_stage).

## Prepared Data Index SSOT
- `src/gui/desktop/tabs/bar_prepare_tab_ssot.py` — `RuntimeIndexWorker` writes `bar_prepare_index.json` under `outputs_root()`.

## Season SSOT
- `src/gui/desktop/widgets/season_ssot_dialog.py` — `_load_seasons()` uses `list_seasons_ssot()`.
- `src/control/api.py` — `/api/v1/seasons/ssot` endpoints.
- `src/core/season_context.py` — `current_season()` default season ID.

## Navigation hooks
- `src/gui/desktop/control_station.py` — `handle_router_url()` routes `internal://report/strategy/<job_id>` and `internal://report/portfolio/<portfolio_id>`.
- `src/gui/services/action_router_service.py` — `handle_action()` routes `gate_summary` for GateSummary navigation.
