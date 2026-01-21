# DP6 Phase II: Explainable Ranking for WFS Winners/Top20 - Governance & Risk Layer

## Discovery Summary

### 1. Phase II Scope Confirmation
- **Target**: WFS Winners & Top20 (FinalScore-based ranking)
- **Phase II Additions**: Governance & Risk layer with WARN/ERROR severity
- **Option A Policy**: Missing plateau artifact => WARN (not ERROR)
- **Backward Compatibility**: Must support both Phase I (INFO-only) and Phase II (INFO/WARN/ERROR)

### 2. SSOT Artifacts Discovery
- **Primary Artifact**: `ranking_explain_report.json` (canonical filename)
- **Location**: `outputs/jobs/<job_id>/ranking_explain_report.json`
- **Schema Version**: "1" (consistent with contract)
- **Existing UI Integration**: Already references `ranking_explain_report.json` in:
  - `src/gui/desktop/tabs/report_tab.py` (lines 101, 298, 322, 361, 478)
  - `src/gui/desktop/state/active_run_state.py` (lines 121, 137-138)

### 3. Threshold Sources (SSOT)
- **Concentration Analysis**: Top1 share thresholds from `RankingExplainConfig`
  - `concentration_top1_error`: 0.50 (≥50% => ERROR)
  - `concentration_top1_warn`: 0.35 (≥35% => WARN)
- **Plateau Quality**: Stability score threshold
  - `plateau_stability_warn_below`: 0.60 (<0.60 => WARN)
- **Robustness Checks**:
  - `mdd_abs_min_error`: 1e-12 (≤1e-12 => ERROR)
  - `trades_min_warn`: 10 (<10 => WARN)
  - Average profit threshold from `ScoringGuardConfig.min_avg_profit`

### 4. Reason Codes (Phase II Additions)
- **Concentration**: `CONCENTRATION_HIGH`, `CONCENTRATION_MODERATE`, `CONCENTRATION_OK`
- **Plateau Quality**: `PLATEAU_STRONG_STABILITY`, `PLATEAU_WEAK_STABILITY`, `PLATEAU_MISSING_ARTIFACT`
- **Guard Breach**: `AVG_PROFIT_BELOW_MIN`, `MDD_INVALID_OR_ZERO`, `TRADES_TOO_LOW_FOR_RANKING`, `METRICS_MISSING_REQUIRED_FIELDS`

### 5. Integration Points
- **Builder**: `src/gui/services/ranking_explain_builder.py` (updated for Phase II logic)
- **Contracts**: `src/contracts/ranking_explain.py` (expanded enums and templates)
- **Config**: `src/contracts/ranking_explain_config.py` (new file for thresholds)
- **Explain Service**: `src/control/explain_service.py` (updated for canonical filename)
- **Artifacts Writer**: `src/core/artifacts.py` (updated error messages)
- **UI**: Already integrated with correct filename

### 6. Filename Standardization
- **Old**: `ranking_explain.json` (Phase I)
- **New**: `ranking_explain_report.json` (canonical for Phase II)
- **All references updated**:
  - Builder writes to `ranking_explain_report.json`
  - Explain service reads from `ranking_explain_report.json`
  - UI checks for `ranking_explain_report.json`
  - Tests updated to expect `ranking_explain_report.json`

### 7. Test Coverage
- **Contract Tests**: Updated for Phase II severity (INFO/WARN/ERROR) and new reason codes
- **Builder Tests**: Updated for Phase II logic and canonical filename
- **Integration Tests**: Updated for canonical filename and schema version "1"
- **Make Check**: All tests pass (1673 passed, 49 skipped, 11 xfailed)

### 8. Key Design Decisions
1. **Option A for missing plateau**: WARN severity (not ERROR) to avoid blocking
2. **Backward compatibility**: Schema version "1" supports both phases
3. **Deterministic ordering**: Reasons sorted by code for consistent output
4. **SSOT-only thresholds**: All thresholds from existing configs or constants
5. **Research-oriented actions**: All actions use "inspect", "validate", "review" verbs

### 9. Evidence of Completion
- All Phase II reason codes implemented with context-aware wording
- Severity enum expanded to INFO/WARN/ERROR
- Concentration analysis with configurable thresholds
- Plateau quality evaluation with stability score
- Robustness checks for MDD, trades, average profit
- All tests pass with `make check = 0 failures`
- UI integration verified with canonical filename