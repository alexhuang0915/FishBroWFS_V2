# Developer Guide (Human + AI Friendly)

This is the **single entrypoint** for how to run and evolve this repo.

Rule:
- If anything disagrees with SSOT, **SSOT wins**.

## SSOT
- `docs/SPEC_ENGINE_V1.md` — execution semantics (data2/cross/features, fills/stops, WFS two-phase, costs, FX, result schema).

## Current Status (V1)
- Engine SSOT locked in `docs/SPEC_ENGINE_V1.md` (data2/cross features, execution fills/stops, two-phase WFS, costs + FX).
- Report UI supports MultiCharts-style Data2 coverage (`missing/update/hold` ratios) and window-scoped OOS trades ledger.
- AutoWFS supports **data2 matrix runs** (same params, multiple `data2` candidates, independent runs) via `configs/registry/data2_pairs.yaml`.
- Shared bars resample is clipped to a fixed anchor start: `2019-01-01 00:00:00` (inclusive).
- Metrics: Net Profit, Max Drawdown, Trades, Win Rate, **Profit Factor** (Gains/Losses), **Sharpe** (Daily, risk-free=0), **Calmar** (Ann. Return / MaxDD).
- Strategy authoring supports YAML-only templates (LLM-friendly): e.g. `dsl_linear_v1` uses `static_params` + packs, no Python codegen.

## Quick Start

Start Worker (Terminal A, keep running):
```bash
PYTHONPATH=src python3 -m control.supervisor.worker --max-workers 1 --tick-interval 0.2
```

Start TUI (Terminal B):
```bash
PYTHONPATH=src FISHBRO_RAW_ROOT=FishBroData python3 src/gui/tui/app.py
```

## TUI Workflow (V1)
1) **Data Prepare** (`1`): run `BUILD_BARS` then `BUILD_FEATURES`  
   - `BUILD_FEATURES` is **prompt-only**: if bars are missing, TUI shows a message and does not submit the job.
   - `Purge Cache Only` clears `cache/shared/<season>/<dataset_id>/` (audited via `purge_manifest.json`).
   - `Purge Numba Cache` clears `cache/numba/` (audited via `cache/numba/purge_manifest.json`).
2) **WFS** (`3`): submit `RUN_RESEARCH_WFS`
3) **Portfolio** (`4`): submit `BUILD_PORTFOLIO_V2`
4) **Monitor** (`2`): inspect `outputs/artifacts/jobs/<job_id>/`
5) **Matrix Summary**: press `m` on Report screen to see matrix comparison for the latest auto-run.

## Auto WFS (Headless)

Run end-to-end (deterministic default):
```bash
PYTHONPATH=src python3 -m control.auto_cli --tfs 60 --max-workers 1
```

Season semantics (V1):
- `--season` controls the **snapshot/build season** used for cache/artifacts paths (e.g. `cache/shared/2026Q1/...`).
- The **WFS window range** comes from the portfolio spec:
  - If `seasons: ["2026Q1"]` => start=end=`2026Q1`
  - If `seasons: ["2019Q1", "2025Q4"]` => start=`2019Q1`, end=`2025Q4`

Matrix mode (SSOT-driven data2 candidates per instrument):
```bash
PYTHONPATH=src python3 -m control.auto_cli --data2-mode matrix --tfs 60
```

Single mode (SSOT-driven `primary` per instrument):
```bash
PYTHONPATH=src python3 -m control.auto_cli --data2-mode single --tfs 60
```

Override a single `data2` for all instruments:
```bash
PYTHONPATH=src python3 -m control.auto_cli --data2 CFE.VX --tfs 60
```

Add a global timeout (seconds):
```bash
PYTHONPATH=src python3 -m control.auto_cli --data2 CFE.VX --tfs 60 --timeout-sec 3600
```

Example: run `dsl_linear_v1` matrix for MNQ+MXF across ALL tfs, using cache snapshot `2026Q1`, and WFS range `2019Q1..2025Q4`:
```bash
PYTHONPATH=src python3 -m control.auto_cli \\
  --spec configs/portfolio/dsl_linear_matrix_mnq_mxf_2019Q1_2025Q4.yaml \\
  --season 2026Q1 \\
  --tfs 15,30,60,120,240 \\
  --data2-mode matrix \\
  --max-workers 10 \\
  --timeout-sec 28800
```

## DSL Optimizer (Autonomous Loop)

Run an unattended optimization loop (edits `configs/strategies/dsl_linear_v1.yaml`, runs matrix WFS, reads `matrix_summary.json`, repeats until closure or iteration limit):
```bash
PYTHONPATH=src python3 -m control.dsl_optimize_cli \\
  --spec configs/portfolio/dsl_linear_matrix_mnq_mxf_2019Q1_2025Q4.yaml \\
  --snapshot-season 2026Q1 \\
  --tfs 15,30,60,120,240 \\
  --max-workers 10 \\
  --iterations 10 \\
  --min-grade B \\
  --min-trades 120 \\
  --timeout-sec 28800
```
Outputs: `outputs/optimizer/dsl_linear_v1_<timestamp>/run_state.json` (best run + per-iteration log).

## Matrix Summary

Generate a cross-comparison table for matrix WFS results:

Auto-run mode (discovery from manifest):
```bash
PYTHONPATH=src python3 -m control.matrix_summary_cli --auto-run <run_id>
```

Latest auto-run (recommended):
```bash
PYTHONPATH=src python3 -m control.matrix_summary_cli --latest-auto-run
```

Manual mode:
```bash
PYTHONPATH=src python3 -m control.matrix_summary_cli --season 2026Q1 --job-ids job1,job2
```

Outputs: `matrix_summary.json`, `matrix_summary.csv`

## Matrix Selection

Perform deterministic selection from matrix results:
```bash
PYTHONPATH=src python3 -m control.matrix_select_cli --run-dir outputs/artifacts/auto_runs/<run_id> --top-k 1 --min-grade B
```
Filters: `--min-grade`, `--min-trades`, `--max-missing-ratio`, `--top-k` (per instrument).

## Cache Management (Purge)

Cleanly delete cached bars/features with audit trail:
```bash
PYTHONPATH=src python3 -m control.shared_cli purge --season 2026Q1 --dataset-id CME.MNQ --all
```
Selective: `--bars` or `--features` with optional `--tfs 60,240`.
Generates: `purge_manifest.json` in the dataset directory for auditability.

Purge Numba JIT disk cache (compile cache):
```bash
PYTHONPATH=src python3 -m control.shared_cli purge-numba
```
Generates: `cache/numba/purge_manifest.json`.

## Configs (SSOT Locations)

Registry (entity definitions):
- `configs/registry/instruments.yaml` — tick specs, roll rules, **cost_model** (profiles must not define costs)
- `configs/registry/margins.yaml` — margin rules
- `configs/registry/strategies.yaml` — strategy registry (what’s allowed to run)
- `configs/registry/feature_packs.yaml` — feature packs registry (SSOT for pack expansion)
- `configs/registry/data2_pairs.yaml` — data2 pairing SSOT (matrix candidates + primary per data1)
- `configs/registry/fx.yaml` — fixed FX constants (V1 base currency: **TWD**)

Profiles (runtime session/timezone; **must not** define costs):
- `configs/profiles/*.yaml`

Strategies (per-strategy parameters):
- `configs/strategies/*.yaml`

## Reference / Generated
- `docs/REF_STRATEGY_FEATURE_MAP.md` — generated map (do not edit unless asked).

## Devlog
- `docs/DEVLOG.md` — append-only notes (not SSOT).

## Data Coverage
- `docs/DATA_COVERAGE_RAW.md` — per-instrument raw file coverage (first/last timestamp + rows).

## Feature Inventory
- `docs/FEATURE_INVENTORY.md` — what features exist + how strategy configs reference packs.

## Archived Docs
Older docs are kept for history:
- `docs/_archive/`
