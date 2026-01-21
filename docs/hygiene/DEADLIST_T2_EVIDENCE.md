# T2 Item Evidence Analysis

## 1. `scripts/freeze_season_with_manifest.py`
- **Classification**: **KEEP**
- **Ref-Count**: 1 (Used in `src`)
- **Usage**: Invoked by `src/control/supervisor/handlers/run_freeze.py` via `subprocess`.
- **Reason**: Critical implementation detail for the `RUN_FREEZE_V2` job type. Moving it to `src/` might be cleaner but `scripts/` usage is established pattern for subprocess CLI entrypoints.

## 2. `scripts/run_baseline.py`
- **Classification**: **KEEP**
- **Ref-Count**: 0 (Entrypoint)
- **Usage**: Manual CLI tool for running baseline experiments.
- **Reason**: Essential utility for research workflows. Not dead code.

## 3. `scripts/debug/dump_context.py` (Moved from `scripts/dump_context.py`)
- **Classification**: **KEEP**
- **Ref-Count**: 0 (Tool)
- **Usage**: Standalone utility for creating context snapshots (useful for LLM workflows).
- **Reason**: Debug/Support tool. Low maintenance cost.

## Conclusion
All T2 items analyzed are **ACTIVE** and should be **KEPT**.
No deletions required for T2 list.
