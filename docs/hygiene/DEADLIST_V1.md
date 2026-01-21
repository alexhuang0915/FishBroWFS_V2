# DEADLIST V1 (Evidence-Based)

## T1: Safe Delete (Unreferenced + Unreachable)
These files are confirmed to be unused entrypoints or ad-hoc scripts with no internal references.

| Path | Evidence | Status |
|------|----------|--------|
| `scripts/check_atr.py` | Ad-hoc script. 0 grep hits. Not in Makefile. | [DELETED] |
| `scripts/check_features.py` | Ad-hoc script. 0 grep hits. Not in Makefile. | [DELETED] |
| `scripts/check_features2.py` | Ad-hoc script. 0 grep hits. Not in Makefile. | [DELETED] |
| `scripts/debug_config_loads.py` | Ad-hoc debugging. 0 grep hits. | [DELETED] |
| `scripts/test_s1_pass.py` | Ad-hoc test wrapper. 0 grep hits. Not in CI. | [DELETED] |
| `scripts/test_s1_error.py` | Ad-hoc test wrapper. 0 grep hits. Not in CI. | [DELETED] |
| `scripts/run_config_reachability.py` | Superseded by `run_config_reachability_v2.py`. | [DELETED] |

### T2: Delete After Manual Confirm (High Priority)
| Path | Status | Risk | Plan |
|---|---|---|---|
| `scripts/dump_context.py` | [KEEP] | Low | Debug/Support Tool |
| `scripts/run_baseline.py` | [KEEP] | Medium | Research Utility |
| `scripts/freeze_season_with_manifest.py` | [KEEP] | High | Used in `src/control` (subprocess) |

## T3: Keep But Relocate/Rename (Misleading Placement)
Code that is active but arguably in the wrong place.

| Path | Evidence |
|------|----------|
| `tests/gui/` | Contains component tests (`test_artifact_navigator_ui.py`). Should likely be merged into `tests/gui_desktop` or renamed `tests/gui_components`. |
| `tests/test_*.py` (root) | 50+ tests in root `tests/` folder. Should be organized into subdirectories. |

## Status Legend
- [PENDING]: Identified but not touched.
- [DELETED]: Physically removed (verified with `make check`).
- [DEFERRED]: Conflict found, deletion skipped.
