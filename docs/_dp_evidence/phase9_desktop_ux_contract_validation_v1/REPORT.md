# Phase 9 — Desktop ⇄ Supervisor UX Contract Validation + Evidence Consolidation

## Objective

Extract UI‑dependent logic from Qt‑based desktop components into pure‑Python, headless, deterministic modules that can be validated in CI without Qt, HTTP, or supervisor dependencies.

## Deliverables

1. **Pure‑logic module**: `src/gui/desktop/services/ux_contract_logic.py`
2. **Headless tests**: `tests/gui_desktop/test_phase9_ux_contract_logic.py`
3. **Validation evidence**: Full test run output, `make check` output, environment snapshot, and this report.

## Implementation Summary

### 1. Extracted Logic

The module `ux_contract_logic.py` contains the following pure‑logic functions:

- `stage_from_status` – maps job status to lifecycle stage (preflight/run/postflight/unknown)
- `relative_age` – human‑readable age formatting (just now, Xs ago, Xm ago, Xh ago, Xd ago)
- `explain_failure_from_artifacts` – semantic‑locked failure explanation with next‑action recommendations
- `categorize_evidence_paths` – deterministic categorization of evidence files (manifest, metrics, reports, logs, artifacts, other)
- `evaluate_readiness_dependencies` – readiness dependency evaluation with missing‑prerequisite reporting

All functions are:

- **Qt‑free**: No PySide6 imports
- **HTTP‑free**: No network calls
- **Supervisor‑free**: No dependency on supervisor API
- **Deterministic**: Same inputs produce same outputs
- **CI‑safe**: Can run in any environment without GUI or external services

### 2. Headless Test Suite

The test file `test_phase9_ux_contract_logic.py` contains 40 test cases covering:

- Stage mapping (14 parameterized cases)
- Relative age formatting (8 cases)
- Failure explanation (7 scenarios)
- Evidence categorization (2 scenarios)
- Readiness dependency evaluation (7 scenarios)
- Integration with existing services (2 import‑safety tests)

All tests pass without Qt; they are explicitly marked as headless and require no GUI.

### 3. Validation Results

#### 3.1 Pure‑Logic Test Run

```
40 passed in 0.13s
```

All 40 tests pass. No failures, no skips (after adjusting conftest to skip Qt import for Phase 9 tests).

#### 3.2 Full Product Test Suite (`make check`)

```
1336 passed, 36 skipped, 3 deselected, 10 xfailed, 18 warnings in 24.61s
```

The product test suite passes with expected xfails and warnings (third‑party numba warnings unrelated to UX contract logic). No test failures introduced by the new module.

### 4. Evidence Files

- `00_env.txt` – environment snapshot (Python version, system info)
- `01_rg_hardcode_before_after.txt` – not applicable (Phase 5 only)
- `02_rg_deprecated_before_after.txt` – not applicable (Phase 5 only)
- `03_pytest_warnings_budget.txt` – not applicable (Phase 5 only)
- `04_make_check_full.txt` – not applicable (Phase 5 only)
- `04_make_check_tail.txt` – not applicable (Phase 5 only)
- `COMMANDS.txt` – list of commands executed during validation
- `PYTEST_OUTPUT.txt` – full pytest output of Phase 9 tests
- `MAKE_CHECK_OUTPUT.txt` – full `make check` output
- `REPORT.md` – this report

### 5. Integration with Existing Services

The pure‑logic module is already imported by:

- `src/gui/desktop/services/job_reason_service.py`
- `src/gui/desktop/services/evidence_locator.py`

Both services now delegate UI‑independent logic to `ux_contract_logic`, enabling headless testing of those services in the future.

### 6. Compliance with Phase 9 Requirements

| Requirement | Status |
|-------------|--------|
| Extract UI logic into pure Python | ✅ |
| No PySide6 / Qt imports in Phase 9 tests | ✅ |
| No HTTP / supervisor dependencies | ✅ |
| Headless, deterministic, CI‑safe | ✅ |
| Full evidence bundle | ✅ |
| `make check` passes | ✅ |
| No new warnings introduced | ✅ (third‑party warnings unrelated) |

### 7. Conclusion

Phase 9 successfully validates the UX contract logic extraction. The pure‑logic module is ready for use in both desktop UI (Qt) and headless CI environments. All tests pass, and the product test suite remains green.

The evidence bundle provides a complete audit trail for future regression testing and compliance verification.

---
**Validated**: 2026‑01‑10T18:00:00Z  
**Branch**: phase9_desktop_ux_contract_validation_v1  
**Commit**: (pre‑golden‑broom snapshot)  
**Environment**: Linux 6.6, Python 3.12.3
