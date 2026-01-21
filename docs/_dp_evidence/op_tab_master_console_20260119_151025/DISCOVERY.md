# Discovery (SSOT Locations)

## OpTab implementation
- `src/gui/desktop/tabs/op_tab.py` — class `OpTab` (refactored wrapper used by ControlStation).
- `src/gui/desktop/tabs/op_tab_refactored.py` — class `OpTabRefactored` (Backtest Master Console implementation).

## Supervisor client / jobs API call sites
- `src/gui/services/supervisor_client.py` — `get_jobs()`, `get_job()`, `get_stdout_tail()`, `get_artifacts()`, `submit_job()`.
- `src/control/api.py` — `/api/v1/jobs` and `/api/v1/jobs/{job_id}` endpoints (`list_jobs_endpoint`, `get_job_endpoint`).

## Job response model fields
- `src/contracts/api.py` — `JobListResponse` fields: `job_id`, `status`, `created_at`, `finished_at`, `strategy_name`, `instrument`, `timeframe`, `run_mode`, `season`, `error_details`, `failure_code`, `failure_message`, `policy_stage`.
- `src/control/supervisor/models.py` — `JobRow` includes `updated_at`, `last_heartbeat`, `progress`, `phase`, `state_reason` (not surfaced in `JobListResponse`).

## Prepared Data Index access (BarPrepareTab SSOT)
- `src/gui/desktop/tabs/bar_prepare_tab_ssot.py` — `RuntimeIndexWorker` builds and writes `bar_prepare_index.json` under `outputs_root() / "_runtime"`.

## Season definitions / SSOT
- `src/gui/desktop/widgets/season_ssot_dialog.py` — `_load_seasons()` uses `list_seasons_ssot()` for season list.
- `src/control/api.py` — `list_seasons_ssot` / `get_season_ssot` endpoints.
- `src/core/season_context.py` — `current_season()` default format `YYYYQ#` used as fallback indicator.
- `src/gui/desktop/tabs/allocation_tab.py` — season input placeholder `2026Q1` (evidence for quarter-formatted season IDs).

## Navigation hooks
- `src/gui/desktop/control_station.py` — `handle_open_report_request()` routes `internal://report/strategy/<job_id>` to report tab.
- `src/gui/services/action_router_service.py` — `handle_action()` handles `gate_summary` target for GateSummary navigation.
