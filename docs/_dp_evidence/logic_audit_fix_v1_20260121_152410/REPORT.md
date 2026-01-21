# Logic Audit Fixes V1 Report

## Changes per Finding

- **[L2-1] Plateau runs on sparse Top-K**
  - Updated `src/research/plateau.py`: Added `load_candidates_from_file` to support `plateau_candidates.json` (broad list) and legacy `topk` (with warning).
  - Updated `src/control/supervisor/handlers/run_plateau.py`: Refactored to search for `plateau_candidates.json` first, then fallback to `winners.json`.
  - Added test `tests/logic_audit/test_l2_plateau.py` verifying support for broad lists and rejection/warning of small top-k.

- **[L1-1] Numba silent fallback**
  - Updated `src/engine/engine_jit.py`: Removed silent suppression. Added lazy ONE-TIME warning log if import fails.
  - Added `FISHBRO_STRICT_JIT` env var check to raise `RuntimeError` in strict environments.
  - Added test `tests/logic_audit/test_l1_engine.py` verifying warning and strict mode.

- **Runner Env Var Silent Fallback**
  - Updated `src/pipeline/runner_grid.py`: Added `logging`. Added warning if `FISHBRO_PERF_TRIGGER_RATE` is malformed.
  - Added `FISHBRO_STRICT_ENV` check to raise `ValueError`.
  - Added test `tests/logic_audit/test_l1_runner.py`.

- **[L3-1] EvidenceLocator silent failure**
  - Updated `src/gui/desktop/services/evidence_locator.py`: Defined `EvidenceLookupError`. Modified `get_evidence_root` to raise this error instead of returning `None`.
  - Updated `list_evidence_files` to propagate the error (allowing UI to handle it).
  - Added test `tests/logic_audit/test_l3_evidence.py`.

- **[L3-2] Dual selection state ambiguity**
  - Updated `src/gui/desktop/state/research_selection_state.py`: Connected `job_store.selected_changed` signal to `self.set_selection`.
  - Ensured `ResearchSelectionState` auto-follows `JobStore` focus, enforcing synchronization.
  - Added test `tests/logic_audit/test_l3_selection.py`.

- **[L3-3] Portfolio loader float coercion**
  - Updated `src/portfolio/loader.py`: Removed blanket `float()` cast loop. Preserved original types (int, bool, str) from YAML/JSON.
  - Added test `tests/logic_audit/test_l3_portfolio.py`.

## Verification

### Automated Tests
- **New Logic Audit Tests**: `tests/logic_audit/` (All 12 passed)
- **Full Suite**: `make check` (All passed: Core + Governance + Legacy)

### Commands Run
- `python3 -m pytest tests/logic_audit/`
- `make check`
