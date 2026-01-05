# Phase E – Portfolio Admission Gate – Implementation Summary

**Date**: 2026-01-05  
**DP Role**: Local Builder (DeepSeek)  
**Project**: FishBroWFS_V2  
**Mode**: PHASE E v1.1 – Portfolio Admission Gate (GovernanceParams + Evidence Contracts) – EXECUTE

## ✅ Final Acceptance Criteria Status

| Criterion | Status | Evidence |
|-----------|--------|----------|
| A) Thresholds NOT hardcoded; loaded from GovernanceParams; evidence snapshot saved. | ✅ **PASS** | `GovernanceParams` extended with `max_pairwise_correlation` and `portfolio_risk_budget_max`; loader supports JSON overrides; `governance_params_snapshot.json` written in evidence bundle. |
| B) Runs with `downstream_admissible=false` are rejected. | ✅ **PASS** | Precondition gate reads `policy_check.json` from Phase C; runs with `downstream_admissible: false` are filtered out before correlation/risk gates. |
| C) Correlation gate enforced using returns series; no implicit fallback. | ✅ **PASS** | `RunEvidenceReader` reads `equity.parquet`; Pearson correlation on aligned daily returns; missing returns → explicit rejection with reason. |
| D) Risk budget enforced; deterministic removal steps recorded. | ✅ **PASS** | Risk budget gate uses max drawdown contributions; iteratively rejects lowest‑score runs; steps recorded in `risk_budget_snapshot.json`. |
| E) Full admission evidence bundle written with all mandatory files. | ✅ **PASS** | `PortfolioAdmissionController` writes 7 mandatory JSON files under `outputs/seasons/{season}/portfolios/{portfolio_id}/admission/`. |
| F) `BUILD_PORTFOLIO_V2` cannot build portfolio unless admission passes. | ✅ **PASS** | Handler calls admission controller; if `admitted == False`, job fails with clear reasons; no portfolio artifacts emitted. |
| G) `make check == 0` failures. | ✅ **PASS** | `make check` passes with **1401 passed, 28 skipped, 3 deselected, 10 xfailed, 0 failures**. |
| H) Repo root remains clean (before/after evidence). | ✅ **PASS** | No new files created in repo root; all changes confined to allowed directories (`src/control/portfolio/`, `src/contracts/portfolio/`, etc.). |

## 📁 Key Files Created/Modified

### 1. GovernanceParams Extension
- **Modified**: `src/portfolio/models/governance_models.py` – added `max_pairwise_correlation` and `portfolio_risk_budget_max` fields.
- **Modified**: `configs/portfolio/governance_params.json` – added default values (`0.60`, `1.00`).
- **Test**: `tests/portfolio/test_governance_params_thresholds_loaded.py` – verifies JSON overrides work without code change.

### 2. Admission Contracts
- **Created**: `src/contracts/portfolio/admission_schemas.py` – `AdmissionDecision` schema and evidence file name constants.

### 3. Run Evidence Reader
- **Created**: `src/control/portfolio/evidence_reader.py` – `RunEvidenceReader` class reads policy_check, score, max drawdown, and returns series from research run artifacts.
- **Test**: `tests/portfolio/test_admission_missing_artifacts_fails_cleanly.py` – ensures missing artifacts cause clean rejection.

### 4. Policy Implementations
- **Created**: `src/control/portfolio/policies/correlation.py` – `CorrelationGate` with Pearson correlation, normalization, alignment, and deterministic violation resolution.
- **Created**: `src/control/portfolio/policies/risk_budget.py` – `RiskBudgetGate` with max‑drawdown‑based risk contributions and iterative rejection.
- **Test**: `tests/portfolio/test_admission_gates.py` – integration tests for both gates.

### 5. Portfolio Admission Controller
- **Created**: `src/control/portfolio/admission.py` – `PortfolioAdmissionController` orchestrates the three gates (precondition, correlation, risk budget) and writes evidence bundle.

### 6. Supervisor Integration
- **Modified**: `src/control/supervisor/handlers/build_portfolio.py` – `BUILD_PORTFOLIO_V2` handler now:
  1. Loads `GovernanceParams` and `RunEvidenceReader`.
  2. Determines candidate run IDs from research decisions (KEEP).
  3. Calls `PortfolioAdmissionController.evaluate_and_write_evidence`.
  4. If admission fails, job fails with clear reasons.
  5. If admission passes, builds portfolio using admitted run IDs via `build_portfolio_from_research` and writes portfolio artifacts.
- **Fixed**: Removed infinite‑recursion bug (subprocess call to wrapper script replaced with direct function calls).

### 7. Research Bridge Extension
- **Modified**: `src/portfolio/research_bridge.py` – `build_portfolio_from_research` now accepts optional `run_ids_allowlist` parameter.

## 🔬 Evidence Bundle Contents

Each admission evaluation writes the following JSON files (atomic, deterministic order):

```
outputs/seasons/{season}/portfolios/{portfolio_id}/admission/
├── admission_decision.json           # Overall decision, admitted/rejected lists, reasons
├── governance_params_snapshot.json   # Snapshot of GovernanceParams used
├── correlation_matrix.json           # Pairwise correlation matrix (normalized returns)
├── correlation_violations.json       # Violation pairs and resolution details
├── risk_budget_snapshot.json         # Budget max, per‑run risk, total, rejection steps
├── admitted_run_ids.json             # Sorted list of admitted run IDs
└── rejected_run_ids.json             # Sorted list of rejected run IDs with reasons
```

## 🧪 CI Tests Added

- `tests/portfolio/test_governance_params_thresholds_loaded.py`
- `tests/portfolio/test_admission_missing_artifacts_fails_cleanly.py`
- `tests/portfolio/test_admission_gates.py` (covers correlation and risk budget gates)

All tests are deterministic, CI‑safe, and use fixtures + `tmp_path`.

## 📊 Determinism Guarantees

- **Input order invariance**: Candidate run IDs are sorted lexicographically before evaluation.
- **Tie‑breaking**: When correlation violation occurs, lower‑score run is rejected; if scores equal, lexicographically larger run ID is rejected.
- **Risk budget removal**: Iteratively rejects lowest‑score runs; ties broken lexicographically.
- **Evidence file ordering**: JSON keys are sorted for stable serialization.

## 🚫 No Magic Numbers

All thresholds are loaded from `GovernanceParams`:
- `max_pairwise_correlation` (default 0.60)
- `portfolio_risk_budget_max` (default 1.00)

These can be overridden via `configs/portfolio/governance_params.json` without code changes.

## 🧹 Root Hygiene

- **Before**: `outputs/_dp_evidence/phase_e_root_ls_before.txt`
- **After**: `outputs/_dp_evidence/phase_e_root_ls_after.txt`
- **Make check output**: `outputs/_dp_evidence/phase_e_make_check.txt`
- **Sample evidence tree**: `outputs/_dp_evidence/phase_e_admission_evidence_tree_sample.txt`

No new files were created in the repo root; all outputs are confined to `outputs/` and allowed source directories.

## 🎯 Conclusion

Phase E – Portfolio Admission Gate – has been successfully implemented and integrated into the FishBroWFS_V2 pipeline. The admission gate enforces:

1. **Phase C downstream_admissible precondition**
2. **Correlation constraint** (using actual returns series, no implicit fallback)
3. **Risk budget constraint** (max‑drawdown‑based contributions)

The gate is fully configurable via `GovernanceParams`, produces a complete, replayable evidence bundle, and ensures `BUILD_PORTFOLIO_V2` cannot produce a portfolio unless all three gates are satisfied.

All acceptance criteria are met, and the existing test suite passes without regressions.