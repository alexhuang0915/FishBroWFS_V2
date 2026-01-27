# Dev Log (Project Notes)

Purpose: a lightweight, append-friendly log for **human + AI** collaboration.

- This is **not** SSOT; it points to the SSOT docs.
- Keep entries short and link to the spec that changed.

## 2026-01-25

- Locked V1 execution semantics + WFS search + stops + cross features in `docs/SPEC_ENGINE_V1.md`.
- Unified base currency to **TWD** and fixed FX constants in `configs/registry/fx.yaml`.
- Moved trading costs SSOT into `configs/registry/instruments.yaml`:
  - `cost_model.commission_per_side` (instrument currency)
  - `cost_model.slippage_per_side_ticks` (V1 fixed = 1)
  - Profiles must not define `cost_model` (fail-closed guard enforced in code).
- Started implementation of V1 cross features:
  - Added deterministic compute module `src/core/features/cross.py`
  - Added unit test `tests/core/test_cross_features_v1.py`

## 2026-01-26

- Data2 coverage now matches **MultiCharts semantics**:
  - `data2_missing_ratio_pct` = post-align true-missing only (aligned Data2 still `NaN` after ffill)
  - Added `data2_update_ratio_pct` + `data2_hold_ratio_pct` for audit/debug and Report detail view.
- Added Data2 pairing SSOT + matrix automation:
  - SSOT: `configs/registry/data2_pairs.yaml`
  - AutoWFS can run **matrix** runs (same params, multiple data2 candidates, independent runs).
- Shared bars resample is now clipped to a fixed anchor start:
  - `2019-01-01 00:00:00` (inclusive), applied before writing `normalized_bars.npz` / `resampled_*.npz`.
- Cross features correctness fixes for cross-asset use:
  - `rel_vol_ratio` switched to ATR% ratio (dimensionless): `(ATR1/close1)/(ATR2/close2)` to avoid price-scale blowups.
  - `compute_atr_14` made NaN-aware so it recovers after missing segments (strict 14-valid window).
  - Added unit tests: `tests/core/test_cross_features_rel_vol_ratio.py`, `tests/core/test_atr_nan_recovery.py`.
- WFS rich output now records a window-scoped **OOS trades ledger** (`windows[i].oos_trades[]`) so Report/debug can inspect actual trades without re-running simulation.
- Produced a full end-to-end matrix run (non-dry-run) to validate closure:
  - Auto run manifest: `outputs/artifacts/auto_runs/auto_2026Q1_20260126_042423/manifest.json`
  - Outputs: 10 WFS results + portfolio recommendations + finalize artifacts.
 - Fixed `BUILD_FEATURES (feature_scope=all_packs)` caching after momentum pack expansion:
   - `atr_pct_*` / `atr_pct_z_*` dispatch no longer collides with the generic `atr_*` prefix.
   - `all_packs` registry now includes momentum feature prefixes + warmup rules (MACD, ATR% z-score).
 - Added YAML-only strategy template for LLM authoring:
   - Strategy: `dsl_linear_v1` (linear score over existing SSOT features; no Python codegen)
   - `static_params` in strategy YAML is now supported and always passed into the strategy class constructor.
 - Expanded `dsl_linear_v1` to cover all engine-supported intent types (V1):
   - Market via `target_dir`
   - Stop-entry via `static_params.dsl.entry` (writes `long_stop/short_stop`, fail-closed if invalid)
   - Stop-exit via `stops.exit_atr_mult` (writes `exit_long_stop/exit_short_stop`)

### Reporting & Workflow Closure
- Added **drawdown series** and **returns histogram** calculation to `StrategyReportV1`.
- Reduced "N/A" in Report UI by ensuring stable population from `wfs_result` artifacts.
- Enhanced `matrix_summary_cli` with `--latest-auto-run` discovery.
- Added **Matrix Summary Screen** to TUI with shortcut `m` on Report screen for the latest matrix results.
- Verified with E2E tests: `tests/handlers/test_baseline_v1_trades.py` confirms drawdown/histogram presence.

### Cache Closure
- Added `control.shared_cli purge-numba` and a `Purge Numba Cache` button in Data Prepare.
- Numba purge is audited via `cache/numba/purge_manifest.json` and tested by `tests/control/test_purge_numba_cache.py`.

## 2026-01-26-B (Matrix Selection & Action Closure)
- Added `control.matrix_select_cli` for deterministic selection output (filters: grade, trades, missing_ratio, top-k).
- Enhanced `MatrixSummaryScreen` in TUI with "Export Selection" button and hotkey `e`.
- Verification: `tests/test_matrix_select_cli.py` confirms deterministic sorting, grade/trades filtering, and top-k per instrument.

## 2026-01-26-C (Auto-run Stability Closure)
- Implemented retry mechanism in `run_auto_wfs` orchestrator for `ORPHANED` jobs.
- Updated manifest schema to include `retry_log` and explicit timeout error messages.
- Verification: `tests/test_auto_orchestrator_retry.py` validates that `ORPHANED` states trigger a retry while `FAILED` states do not.

## 2026-01-26-D (Build Data Purge & Audit Closure)
- Added `purge` subcommand to `control.shared_cli` for selective or full cache deletion.
- Implemented `purge_manifest.json` audit record to track what was deleted and when.
- Enhanced TUI Data Prepare screen with a "Purge Cache Only" button for manual maintenance.
- Verification: `tests/handlers/test_build_data_purge.py` confirms selective file deletion and audit manifest generation.

## 2026-01-26-E (Report Metrics Completeness Closure)
- Implemented **Profit Factor**, **Sharpe (Daily)**, and **Calmar** ratios in report builders.
- Fixed trade ledger key mapping (`entry_t`, `exit_t`, `net_pnl`) for accurate Profit Factor calculation.
- Improved Calmar robustness with a drawdown floor to handle zero-drawdown scenarios (always-increasing equity).
- Verification: `tests/handlers/test_baseline_v1_trades.py` confirms presence and non-zero values for all new metrics in V1 reports.
