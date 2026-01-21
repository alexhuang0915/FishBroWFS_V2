# CI Profile V1 (2026-01-21)

## Summary
- **Total Duration**: ~67s (real)
- **Total Tests**: 2065 collected
- **Pass Rate**: 97% (2015 passed)
- **Slowest Layer**: Product/Control (Supervisor tests) & GUI Desktop (Gate Summary Widget)

## Wall Time
- `make check`/`pytest`: ~66.84s

## Top 30 Slowest Tests
| Duration | Test | Layer |
|---|---|---|
| 5.76s | `test_supervisor_abort_enforcement_v1.py::test_abort_requested_on_multiple_jobs` | Control |
| 5.58s | `test_gate_summary_widget.py::test_on_gate_clicked_ranking_explain_triggers_open` | GUI |
| 5.31s | `test_supervisor_abort_enforcement_v1.py::test_abort_running_job_kills_subprocess_and_error_details` | Control |
| 4.10s | `test_gate_summary_widget.py::test_widget_with_job_id_shows_job_title` | GUI |
| 2.65s | `test_supervisor_handler_build_data_v1.py::test_build_data_handler_minimal_harmless` | Control |
| 2.38s | `test_registry_preload_headless.py::test_registry_preload_headless` | Control |
| 2.06s | `test_supervisor_abort_contract_v1.py::test_cli_abort_command` | Control |
| 1.64s | `test_supervisor_ping_contract_v1.py::test_ping_integration_smoke` | Control |
| 1.55s | `test_supervisor_handler_clean_cache_v1.py::test_clean_cache_handler_dataset_scope` | Control |
| 1.54s | `test_supervisor_handler_build_data_v1.py::test_build_data_handler_cli_fallback` | Control |
| 1.53s | `test_supervisor_handler_clean_cache_v1.py::test_clean_cache_handler_dry_run` | Control |
| 1.38s | `test_dtype_compression_contract.py::test_simulate_arrays_accepts_uint8_enums` | Contracts |
| 1.37s | `test_gate_summary_duplicate_model_ban.py::test_gate_status_enum_documentation` | Contracts |
| 1.29s | `test_gate_summary_duplicate_model_ban.py::test_no_duplicate_gate_summary_models` | Contracts |
| 1.10s | `test_outputs_hygiene.py::test_outputs_no_generated_configs` | Contracts |
| 1.04s | `test_policy_enforcement.py::test_cli_submit_respects_policy` | Control |
| 1.03s | `test_supervisor_ping_contract_v1.py::test_ping_cli_submit` | Control |
| 0.87s | `test_subprocess_policy.py::test_subprocess_allowlist` | Contracts |
| 0.84s | `test_supervisor_abort_contract_v1.py::test_supervisor_abort_flow` | Control |
| 0.62s | `test_supervisor_handler_clean_cache_v1.py::test_clean_cache_handler_abort_before_invoke` | Control |
| 0.62s | `test_supervisor_handler_build_data_v1.py::test_build_data_handler_abort_before_invoke` | Control |
| 0.60s | `test_import_hygiene.py::test_src_does_not_import_from_tests` | Contracts |
| 0.53s | `test_supervisor_heartbeat_timeout_v1.py::test_supervisor_orphan_detection` | Control |
| 0.53s | `test_supervisor_abort_enforcement_v1.py::test_abort_running_job_with_missing_pid` | Control |
| 0.52s | `test_supervisor_heartbeat_timeout_v1.py::test_supervisor_handles_missing_worker` | Control |
| 0.52s | `test_supervisor_abort_enforcement_v1.py::test_abort_queued_job_with_error_details` | Control |
| 0.45s | `test_funnel_contract.py::test_each_stage_creates_run_dir_with_artifacts` | Product |
| 0.39s | `test_golden_kernel_verification.py::test_no_trade_case_does_not_crash_and_returns_zero_metrics` | Contracts |
| 0.39s | `test_feature_bank_v2_new_families.py::test_bbands_pb[5]` | Product |
| 0.36s | `test_qt_pydantic_pylance_guard.py::test_no_qt5_enums` | Contracts |

## Suspects & Observations
1.  **Supervisor Abort Tests**: `test_supervisor_abort_enforcement_v1.py` takes ~12s total. It likely sleeps or waits for subprocess termination timeouts.
2.  **Gate Summary Widget**: `test_gate_summary_widget_conversion` and related tests are slow (~10s). This might be due to QApplication setup or heavy widget initialization.
3.  **Clean Cache / Build Data Handlers**: These control tests take ~1.5s each, likely due to file system operations or mocks setups.
4.  **Contract Scans**: `test_gate_summary_duplicate_model_ban` and `test_outputs_hygiene` scan large parts of the repo (AST parsing / file walking), taking ~1s each.

## Recommendations (Future)
- Inspect `test_supervisor_abort_enforcement_v1.py` for hardcoded `sleep` or long polling intervals.
- Check if `GateSummaryWidget` tests are creating too many heavy objects or if `QApplication` reuse is suboptimal.
- optimize `find_class_definitions` in contract tests to avoid re-walking the tree multiple times if possible.
