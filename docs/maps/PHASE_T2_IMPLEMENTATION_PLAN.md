# Phase T2: Test Hygiene & Governance Implementation Plan

## Goal
Implement surgically safe deletions of R3 tooling tests, isolate R2 legacy tests into a quarantine folder, and establish formalized test layering (core, governance, legacy) via `Makefile` targets.

## Proposed Changes

### 1. Safe Delete R3 Tests
#### [DELETE] [test_log_tail_reads_last_n_lines.py](file:///home/fishbro/FishBroWFS_V2/tests/tools/test_log_tail_reads_last_n_lines.py)
#### [DELETE] [test_make_clear.py](file:///home/fishbro/FishBroWFS_V2/tests/tools/test_make_clear.py)
- These are classified as R3 tooling-only and are safe to remove.

### 2. Legacy Quarantine (R2)
#### [NEW] [deprecated/legacy](file:///home/fishbro/FishBroWFS_V2/tests/deprecated/legacy/)
Move the following R2 tests to `tests/deprecated/legacy/`:
- `tests/legacy/test_b5_query_params.py`
- `tests/legacy/stage0/test_precision_rank_correlation.py`
- `tests/legacy/stage2/test_kernel_exit_gap_semantics.py`
- `tests/legacy/phases/test_phase13_param_grid.py`
- `tests/legacy/phases/test_phase14_order_exec_semantics.py`
- `tests/legacy/phases/test_phase14_policy_guards.py`
- `tests/legacy/phases/test_phase14_feature_registry_contract.py`
- `tests/legacy/phases/test_phase14_registry_overlay_contract.py`

### 3. Test Layering Implementation
#### [MODIFY] [Makefile](file:///home/fishbro/FishBroWFS_V2/Makefile)
Add and update targets:
- `make test-core`: runs `tests/product/`, `tests/control/`, `tests/portfolio/`, `tests/gui_desktop/`, etc. (R0)
- `make test-governance`: runs `tests/contracts/`, `tests/policy/`, `tests/hygiene/` (R1)
- `make test-legacy`: runs `tests/deprecated/legacy/` (R2)
- `make check-fast`: maps to `test-core` + `test-governance`
- `make check`: runs everything (core + governance + legacy)

### 4. Documentation
#### [NEW] [TEST_EXECUTION_PROFILES_V1.txt](file:///home/fishbro/FishBroWFS_V2/docs/tests/TEST_EXECUTION_PROFILES_V1.txt)
- Document the three profiles, their coverage, and usage.

## Verification Plan

### Automated Tests
1. Run `make check` after each step.
2. Verify `make test-core` passes.
3. Verify `make test-governance` passes.
4. Verify `make test-legacy` passes.
5. Verify `make check-fast` passes.
6. Verify `make check` passes.

### Evidence Generation
- `outputs/_dp_evidence/safe_delete_r3_.../`
- `outputs/_dp_evidence/legacy_quarantine_.../`
- `outputs/_dp_evidence/test_layering_.../`
