# FishBroWFS_V2 Phase 0 Cleanup Audit Report

**Audit Date**: 2026-01-05  
**Auditor**: Repo Auditor (DP Role)  
**Mode**: PHASE 0 - CLEANUP AUDIT ONLY (NO REFACTOR, NO LOGIC CHANGES)  
**Evidence Directory**: `outputs/_dp_evidence/phase0_cleanup_audit/`

## 1. Executive Summary

This audit identifies cleanup candidates across the FishBroWFS_V2 repository, focusing on bypass entrypoints, legacy remnants, dead code, contract drift, and root hygiene risks. The audit was conducted using evidence‑driven scans (ripgrep, directory listings, Makefile excerpts) and confirms that the repository passes `make check` with zero failures. The findings are categorized by risk (HIGH, MED, LOW) and each includes concrete file paths, line numbers, evidence commands, and a single recommended cleanup action.

## 2. Top 5 HIGH Risk Findings

1. **Legacy wrapper scripts still executable** – Multiple `scripts/run_*.py` files contain `FISHBRO_ALLOW_LEGACY_WRAPPERS` checks but remain reachable; they should be removed or hardened to prevent accidental bypass of Supervisor‑API‑only policy.
2. **Makefile legacy targets clutter help output** – Numerous `legacy-*` targets (e.g., `legacy-gui`, `legacy-dashboard`) remain in the Makefile, confusing users and increasing maintenance surface.
3. **NiceGUI references in production code** – Several source files still mention NiceGUI in docstrings and comments, creating ambiguity about the current UI architecture.
4. **Subprocess bypass in GUI desktop code** – `src/gui/desktop/supervisor_lifecycle.py` uses `subprocess.Popen` directly; while currently necessary, it should be reviewed for Supervisor‑API‑only compliance.
5. **Legacy winners schema conversion code** – `src/core/winners_builder.py` and `src/core/winners_schema.py` contain legacy‑to‑v2 conversion logic that may be obsolete if all winners are already v2.

## 3. Findings

### FND-001
- **Risk**: HIGH
- **Title**: Legacy wrapper scripts bypass Supervisor‑API‑only policy
- **Location**: 
  - `scripts/run_research_v3.py:22-40`
  - `scripts/run_phase3a_plateau.py:32-40`
  - `scripts/run_phase3b_freeze.py:25-33`
  - `scripts/run_phase3c_compile.py:27-35`
  - `scripts/build_portfolio_from_research.py:25-33`
- **Evidence**: `rg -n "FISHBRO_ALLOW_LEGACY_WRAPPERS" scripts/` (see `outputs/_dp_evidence/phase0_cleanup_audit/rg_legacy.txt` lines 356‑402)
- **Impact**: Users can bypass the Desktop UI and Supervisor API by setting `FISHBRO_ALLOW_LEGACY_WRAPPERS=1`, undermining the Phase B hardening goal.
- **Cleanup Action**: Delete all five wrapper scripts (`run_research_v3.py`, `run_phase3a_plateau.py`, `run_phase3b_freeze.py`, `run_phase3c_compile.py`, `build_portfolio_from_research.py`) and remove their references from the Makefile.
- **Verification**: After removal, `make run-research`, `make run-plateau`, etc., should fail with a clear message directing users to the Desktop UI or Supervisor CLI.

### FND-002
- **Risk**: HIGH
- **Title**: Makefile contains deprecated legacy targets that confuse users
- **Location**: `Makefile:75-82` (LEGACY / DEPRECATED section) and targets `legacy-gui`, `legacy-dashboard`, `legacy-backend`, `legacy-worker`, `legacy-war`, `legacy-stop-war`, `legacy-up`, `clean-cache-legacy`, `build-data-legacy`, `generate-reports-legacy`
- **Evidence**: `rg -n "legacy" Makefile` (see `outputs/_dp_evidence/phase0_cleanup_audit/rg_legacy.txt` lines 1‑56)
- **Impact**: Clutters help output, increases maintenance burden, and signals that legacy web‑UI stack is still supported (it is not).
- **Cleanup Action**: Remove all legacy‑prefixed targets and their associated rules from the Makefile, keeping only the canonical Supervisor‑API targets.
- **Verification**: `make help` should show no legacy targets; `make legacy-gui` should return “command not found”.

### FND-003
- **Risk**: MED
- **Title**: NiceGUI references persist in source code docstrings and comments
- **Location**:
  - `src/research/run_index.py:4`
  - `src/gui/desktop/tabs/op_tab.py.backup:2-3`
  - `src/core/service_identity.py:5,107`
  - `src/gui/desktop/tabs/registry_tab.py:3`
  - `src/gui/desktop/tabs/op_tab.py:2,5`
  - `src/gui/desktop/control_station.py:3`
  - `src/control/lifecycle.py:277-279`
- **Evidence**: `rg -n "nicegui|NiceGUI" src` (see `outputs/_dp_evidence/phase0_cleanup_audit/rg_nicegui.txt`)
- **Impact**: Creates confusion about the current UI architecture (Qt Desktop is the only product UI) and may mislead new developers.
- **Cleanup Action**: Update docstrings and comments to remove NiceGUI mentions, replacing them with “Qt Desktop” or “Desktop UI” where appropriate. Delete the backup file `src/gui/desktop/tabs/op_tab.py.backup`.
- **Verification**: `rg -i nicegui src` should return zero matches after cleanup.

### FND-004
- **Risk**: MED
- **Title**: Subprocess usage in GUI desktop code could bypass Supervisor API
- **Location**: 
  - `src/gui/desktop/supervisor_lifecycle.py:240-299` (`start_supervisor_subprocess` uses `subprocess.Popen`)
  - `src/gui/services/runtime_context.py:121-250` (multiple `subprocess.run` calls)
  - `src/pipeline/funnel_runner.py:56-86` (`subprocess.run` for funnel execution)
- **Evidence**: `rg -n "subprocess\\.|os\\.system\(|Popen\(" src/gui/desktop src/gui/services src/pipeline` (see `outputs/_dp_evidence/phase0_cleanup_audit/rg_entrypoints.txt` lines 83‑96, 179‑203)
- **Impact**: Direct subprocess calls may circumvent the Supervisor API contract, introducing non‑deterministic behavior and making the system harder to monitor.
- **Cleanup Action**: Audit each subprocess call to ensure it is either (a) necessary for launching the Supervisor itself, or (b) can be replaced with a Supervisor job submission. For necessary calls, add a comment explaining why Supervisor API cannot be used.
- **Verification**: After audit, no new subprocess calls should be added without explicit justification documented in the code.

### FND-005
- **Risk**: MED
- **Title**: Legacy winners schema conversion code may be dead
- **Location**: 
  - `src/core/winners_builder.py` (full file)
  - `src/core/winners_schema.py:100-110` (`is_winners_legacy`)
  - `src/core/artifacts.py:75-101` (auto‑upgrade logic)
- **Evidence**: `rg -n "legacy.*winners|winners.*legacy" src/core` (see `outputs/_dp_evidence/phase0_cleanup_audit/rg_legacy.txt` lines 57‑107)
- **Impact**: Maintains compatibility with old winners format, but if all production winners are already v2, this code is dead weight and a potential source of bugs.
- **Cleanup Action**: Determine whether any legacy winners still exist in production outputs. If none, remove the conversion logic and require v2 winners everywhere. If some remain, schedule a migration and then remove the code.
- **Verification**: Scan `outputs/research/` and `outputs/research_runs/` for any `winners.json` files that are not v2 schema. If none found, conversion code can be safely deleted.

### FND-006
- **Risk**: LOW
- **Title**: Root directory contains large snapshot file that should be moved to outputs/
- **Location**: `SNAPSHOT_CLEAN.jsonl` (4.5 MB) in repository root
- **Evidence**: `ls -la` (see `outputs/_dp_evidence/phase0_cleanup_audit/root_ls.txt` line 14)
- **Impact**: Violates root hygiene principle; large data files should reside under `outputs/` or `data/`.
- **Cleanup Action**: Move `SNAPSHOT_CLEAN.jsonl` to `outputs/_dp_evidence/snapshots/` (or a dedicated snapshot directory) and update any references.
- **Verification**: `ls -la SNAPSHOT_CLEAN.jsonl` should fail; the file should be accessible at its new location.

### FND-007
- **Risk**: LOW
- **Title**: Deprecated `datetime.utcnow()` usage triggers warnings
- **Location**: 
  - `src/control/prepare_orchestration.py:83,128`
  - `tests/test_funnel_smoke_contract.py:32,83,115,146`
  - `tests/test_funnel_topk_determinism.py:99,110`
  - `tests/test_funnel_topk_no_human_contract.py:105,149,196`
- **Evidence**: `make check` output shows 539 warnings, many due to `datetime.utcnow()` deprecation.
- **Impact**: Pollutes test output, may break in future Python versions.
- **Cleanup Action**: Replace `datetime.utcnow()` with `datetime.now(datetime.UTC)` (Python 3.11+) or `datetime.now(timezone.utc)`.
- **Verification**: Run `make check` and verify no deprecation warnings about `utcnow()` remain.

### FND-008
- **Risk**: LOW
- **Title**: Legacy profile path checks in policy tests reference non‑existent directories
- **Location**: `tests/policy/test_no_legacy_profiles_path_stringban.py:30-65`
- **Evidence**: `rg -n "legacy.*profiles" tests/policy` (see `outputs/_dp_evidence/phase0_cleanup_audit/rg_legacy.txt` lines 157‑165)
- **Impact**: Test assumes legacy directory `src/data/profiles` may exist; if it does not, the test is a no‑op but still adds maintenance overhead.
- **Cleanup Action**: Remove the test or update it to verify that no code references the legacy path (already covered by other policy tests).
- **Verification**: After removal, `make check` still passes all policy tests.

### FND-009
- **Risk**: LOW
- **Title**: `scripts/run_stack.py` still contains GUI‑spawning logic for NiceGUI
- **Location**: `scripts/run_stack.py:232-236` (`spawn_gui` function)
- **Evidence**: `sed -n '1,320p' scripts/run_stack.py` (see `outputs/_dp_evidence/phase0_cleanup_audit/makefile_run_stack_excerpt.txt` lines 232‑236)
- **Impact**: The function prints an error and exits, but its presence suggests the stack could still try to start a web UI.
- **Cleanup Action**: Remove the `spawn_gui` function and all references to it (the `--no-gui` flag, GUI‑related constants).
- **Verification**: `python scripts/run_stack.py run --no-gui` should work without referencing any GUI code.

### FND-010
- **Risk**: LOW
- **Title**: Mixed legacy folder tolerance in run‑index may hide mis‑named directories
- **Location**: `src/research/run_index.py:42,150,303` (mentions “tolerates mixed legacy folders”)
- **Evidence**: `rg -n "legacy.*folder" src/research` (see `outputs/_dp_evidence/phase0_cleanup_audit/rg_nicegui.txt` line 1‑2)
- **Impact**: The code accepts both `run_*` and `artifact_*` directory names, which could allow incorrectly named directories to persist.
- **Cleanup Action**: Decide whether to enforce a single naming convention (`run_*`). If yes, update the run‑index to reject legacy `artifact_*` folders and rename existing ones.
- **Verification**: After cleanup, `src/research/run_index.py` should not contain “legacy” in its docstrings.

## 4. Cleanup Backlog Table

| ID       | Action | Verify |
|----------|--------|--------|
| FND‑001  | Delete five legacy wrapper scripts (`scripts/run_*.py`, `build_portfolio_*.py`) and update Makefile | `make run-research` fails with clear guidance |
| FND‑002  | Remove all `legacy-*` targets from Makefile | `make help` shows no legacy targets |
| FND‑003  | Update docstrings/comments to remove NiceGUI mentions; delete `op_tab.py.backup` | `rg -i nicegui src` returns zero matches |
| FND‑004  | Audit subprocess calls in GUI code; document necessary ones | No new subprocess calls added without justification |
| FND‑005  | Determine if legacy winners exist; remove conversion code if none | Scan outputs for non‑v2 winners.json |
| FND‑006  | Move `SNAPSHOT_CLEAN.jsonl` to `outputs/_dp_evidence/snapshots/` | File no longer in root |
| FND‑007  | Replace `datetime.utcnow()` with timezone‑aware alternatives | `make check` shows no utcnow warnings |
| FND‑008  | Remove or update `test_no_legacy_profiles_path_stringban.py` | Policy tests still pass |
| FND‑009  | Remove GUI‑spawning logic from `scripts/run_stack.py` | `run_stack.py` contains no GUI references |
| FND‑010  | Decide on run‑folder naming convention; update run‑index | Run‑index docstrings no longer mention “legacy” |

## 5. Appendix: Commands Executed

All evidence files are stored in `outputs/_dp_evidence/phase0_cleanup_audit/`.

1. **Root hygiene snapshot**  
   ```bash
   ls -la > outputs/_dp_evidence/phase0_cleanup_audit/root_ls.txt
   ```

2. **Entrypoint bypass scan**  
   ```bash
   rg -n "subprocess\.|os\.system\(|Popen\(|run_make_command|make\\s+run-|scripts/.*\\.py" src tests scripts Makefile > outputs/_dp_evidence/phase0_cleanup_audit/rg_entrypoints.txt || true
   ```

3. **Legacy / bypass signals**  
   ```bash
   rg -n "FISHBRO_ALLOW_LEGACY_WRAPPERS|legacy|NiceGUI|nicegui|ui\\.|socket\\.io|_nicegui" -S src scripts tests Makefile > outputs/_dp_evidence/phase0_cleanup_audit/rg_legacy.txt || true
   ```

4. **Makefile + run_stack inspection**  
   ```bash
   sed -n '1,260p' Makefile > outputs/_dp_evidence/phase0_cleanup_audit/makefile_run_stack_excerpt.txt
   if [ -f scripts/run_stack.py ]; then sed -n '1,320p' scripts/run_stack.py >> outputs/_dp_evidence/phase0_cleanup_audit/makefile_run_stack_excerpt.txt; fi
   ```

5. **Desktop UI: Supervisor‑API‑only and tab inventory**  
   ```bash
   rg -n "requests\\.|httpx\\.|Supervisor|supervisor_client|127\\.0\\.0\\.1:8000" src/gui/desktop > outputs/_dp_evidence/phase0_cleanup_audit/ui_tabs_scan.txt || true
   rg -n "subprocess|os\\.system|make\\s|scripts/" src/gui/desktop >> outputs/_dp_evidence/phase0_cleanup_audit/ui_tabs_scan.txt || true
   ls -la src/gui/desktop >> outputs/_dp_evidence/phase0_cleanup_audit/ui_tabs_scan.txt
   ls -la src/gui/desktop/tabs >> outputs/_dp_evidence/phase0_cleanup_audit/ui_tabs_scan.txt || true
   rg -n "QTabWidget|addTab\\(" src/gui/desktop >> outputs/_dp_evidence/phase0_cleanup_audit/ui_tabs_scan.txt || true
   ```

6. **Outputs/Artifacts contract scan**
   ```bash
   rg -n "jobs_v2\\.db|get_default_db_path|outputs/jobs|outputs/portfolios" src > outputs/_dp_evidence/phase0_cleanup_audit/rg_outputs_contracts.txt || true
   rg -n "manifest\\.json|policy_check\\.json|inputs_fingerprint\\.json|outputs_fingerprint\\.json|runtime_metrics\\.json|stdout_tail\\.log" src >> outputs/_dp_evidence/phase0_cleanup_audit/rg_outputs_contracts.txt || true
   rg -n "admission_decision\\.json|correlation_matrix\\.json|correlation_violations\\.json|risk_budget_snapshot\\.json|admitted_run_ids\\.json|rejected_run_ids\\.json" src >> outputs/_dp_evidence/phase0_cleanup_audit/rg_outputs_contracts.txt || true
   ```

7. **Legacy UI remnants (NiceGUI)**
   ```bash
   rg -n "nicegui|NiceGUI" src > outputs/_dp_evidence/phase0_cleanup_audit/rg_nicegui.txt || true
   if [ -d src/gui/nicegui ]; then ls -la src/gui/nicegui >> outputs/_dp_evidence/phase0_cleanup_audit/rg_nicegui.txt; fi
   ```

8. **Run tests (NO CHANGES EXPECTED)**
   ```bash
   make check
   ```