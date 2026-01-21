# Discovery (SSOT Locations)

## Portfolio Tab implementation
- `src/gui/desktop/tabs/allocation_tab.py` — class `AllocationTab` (Portfolio Master Console implementation).

## OpTab implementation (reference)
- `src/gui/desktop/tabs/op_tab_refactored.py` — class `OpTabRefactored` (Backtest Master Console pattern).

## Portfolio jobs API / submissions
- `src/control/portfolio/api_v1.py` — `post_portfolio_build` endpoint builds `BUILD_PORTFOLIO_V2` jobs.
- `src/gui/services/supervisor_client.py` — `post_portfolio_build`, `get_outputs_summary`, `get_job`, `get_stdout_tail`, `get_artifacts`.

## Job model fields
- `src/control/supervisor/models.py` — `JobRow` includes `state`, `created_at`, `updated_at`, `progress`, `phase`, `failure_message`, `policy_stage`.
- `src/contracts/api.py` — `JobListResponse` exposes `status`, `created_at`, `failure_message`, `policy_stage` (used when polling job_id).

## Prepared Data Index access
- `src/gui/desktop/tabs/bar_prepare_tab_ssot.py` — `RuntimeIndexWorker` writes `bar_prepare_index.json` under `outputs_root()`.

## Season SSOT
- `src/gui/desktop/widgets/season_ssot_dialog.py` — `_load_seasons` uses `list_seasons_ssot()`.
- `src/control/api.py` — `/api/v1/seasons/ssot` endpoints.
- `src/core/season_context.py` — `current_season()` fallback.

## Navigation hooks
- `src/gui/desktop/control_station.py` — `handle_router_url()` handles `internal://report/portfolio/<portfolio_id>`.
- `src/gui/services/action_router_service.py` — `handle_action()` routes `gate_summary` for GateSummary navigation.
