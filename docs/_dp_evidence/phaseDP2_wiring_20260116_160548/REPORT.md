# Phase DP2 Wiring Report

**Evidence folder:** `outputs/_dp_evidence/phaseDP2_wiring_20260116_160548/`

## Discoveries & Architecture Notes
- `configs/registry/instruments.yaml` now records each instrument’s `timezone` and `trade_date_roll_time_local`, which the new loader enforces so we never hardcode a roll time on the handler path.
- `src/config/registry/instruments.py` validates the new fields before consumers load instrument metadata; missing or malformed values raise a `ConfigError`, which guards the entire flow.
- `src/control/supervisor/handlers/build_data.py` orchestrates the TimeframeAggregator → DataAligner path and emits `data_alignment_report.json` into `outputs/jobs/<job_id>/`.
- The Explain SSOT (`src/control/explain_service.py`) and Gate Summary Service (`src/gui/services/gate_summary_service.py`) now surface the alignment metrics and artifact without recomputing data, keeping UI/metrics purely observational.
- The new primitives in `src/core/timeframe_aggregator.py` and `src/core/data_aligner.py` are pure, timezone-aware, and reusable across the data pipeline.

## Modified Files (key changes)
- `configs/registry/instruments.yaml`
- `src/config/registry/instruments.py`
- `src/control/supervisor/handlers/build_data.py`
- `src/control/explain_service.py`
- `src/gui/services/gate_summary_service.py`
- `src/core/timeframe_aggregator.py`
- `src/core/data_aligner.py`
- `tests/control/test_build_data_alignment_artifact.py`
- `tests/core/test_timeframe_aggregator.py`
- `tests/core/test_data_aligner.py`
- `tests/explain/test_data_alignment_disclosure.py`
- `tests/gate/test_data_alignment_gate.py`
- `tests/registry/test_instruments_registry.py`
- `tests/gui/services/test_gate_summary_service.py`
- `tests/control/test_root_hygiene_guard.py`
- `docs/contracts/ROOT_TOPLEVEL_ALLOWLIST_V1.txt`

## Tests & Logs
- `python3 -m pytest -q tests/control -q` → see `rg_pytest_tests_control.txt`
- `python3 -m pytest -q tests/gui/services -q` → see `rg_pytest_tests_gui_services.txt`
- `make check` → see `rg_make_check.txt`

## Next Steps (for follow-up)
- Data Alignment gate warns when the artifact exists; otherwise it remains PASS so it does not break retrospective summary builds.

Current commit: 8937405f43b5b69f39bfef0c1a8d4a17e4c49ae6
