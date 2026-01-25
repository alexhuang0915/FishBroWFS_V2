# Developer Guide (Human + AI Friendly)

This is the **single entrypoint** for how to run and evolve this repo.

Rule:
- If anything disagrees with SSOT, **SSOT wins**.

## SSOT
- `docs/SPEC_ENGINE_V1.md` — execution semantics (data2/cross/features, fills/stops, WFS two-phase, costs, FX, result schema).

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
2) **WFS** (`3`): submit `RUN_RESEARCH_WFS`
3) **Portfolio** (`4`): submit `BUILD_PORTFOLIO_V2`
4) **Monitor** (`2`): inspect `outputs/artifacts/jobs/<job_id>/`

## Configs (SSOT Locations)

Registry (entity definitions):
- `configs/registry/instruments.yaml` — tick specs, roll rules, **cost_model** (profiles must not define costs)
- `configs/registry/margins.yaml` — margin rules
- `configs/registry/strategies.yaml` — strategy registry (what’s allowed to run)
- `configs/registry/feature_packs.yaml` — feature packs registry (SSOT for pack expansion)
- `configs/registry/fx.yaml` — fixed FX constants (V1 base currency: **TWD**)

Profiles (runtime session/timezone; **must not** define costs):
- `configs/profiles/*.yaml`

Strategies (per-strategy parameters):
- `configs/strategies/*.yaml`

## Reference / Generated
- `docs/REF_STRATEGY_FEATURE_MAP.md` — generated map (do not edit unless asked).

## Devlog
- `docs/DEVLOG.md` — append-only notes (not SSOT).

## Archived Docs
Older docs are kept for history:
- `docs/_archive/`
