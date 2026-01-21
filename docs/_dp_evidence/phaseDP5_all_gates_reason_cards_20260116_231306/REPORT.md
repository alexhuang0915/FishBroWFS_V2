# DP5: Explainable WARN/FAIL Reason Cards for ALL Gates

## Implementation Summary

Successfully implemented deterministic Reason Cards for all gates in GateSummary and Explain services.

## Gate Keys Covered

1. **Slippage Stress Gate** (`slippage_stress`)
   - SLIPPAGE_STRESS_EXCEEDED
   - SLIPPAGE_STRESS_ARTIFACT_MISSING

2. **Readiness Gate** (`api_readiness`)
   - READINESS_DATA2_NOT_PREPARED
   - READINESS_DATA_COVERAGE_INSUFFICIENT
   - READINESS_ARTIFACT_MISSING

3. **Policy Enforcement Gate** (`policy_enforcement`)
   - POLICY_VIOLATION
   - POLICY_ARTIFACT_MISSING

4. **Control Actions Gate** (`control_actions`)
   - CONTROL_ACTION_EVIDENCE_MISSING
   - CONTROL_ACTION_DISCLOSURE_INCOMPLETE

5. **Shared Build Gate** (`shared_build`)
   - SHARED_BUILD_GATE_FAILED
   - SHARED_BUILD_GATE_WARN
   - SHARED_BUILD_ARTIFACT_MISSING

6. **Existing Gates Updated**:
   - Data Alignment Gate (`data_alignment`)
   - Resource/OOM Gate (`resource`)
   - Portfolio Admission Gate (`portfolio_admission`)

## Thresholds Applied

- Slippage Stress: S3 net profit > 0.0
- Data Alignment Forward Fill: 50% warning threshold
- Resource Memory: Default memory warning threshold
- Portfolio Correlation: Default correlation threshold
- Portfolio MDD: Default MDD threshold

## Files Created/Modified

### New Files
- `src/gui/services/gate_reason_cards_registry.py` - Central registry for all gate reason cards

### Modified Files
- `src/gui/services/gate_summary_service.py` - Integrated reason cards into all gates
- `src/control/explain_service.py` - Added `gate_reason_cards` mapping to Explain payload
- `src/gui/services/data_alignment_status.py` - Enhanced with reason card builder
- `src/gui/services/resource_status.py` - Enhanced with reason card builder
- `src/gui/services/portfolio_admission_status.py` - Enhanced with reason card builder

### Test Files Created
- `tests/gui/services/test_slippage_reason_cards.py`
- `tests/gui/services/test_readiness_reason_cards.py`
- `tests/gui/services/test_policy_reason_cards.py`
- `tests/gui/services/test_control_actions_reason_cards.py`
- `tests/gui/services/test_shared_build_reason_cards.py`
- `tests/gate/test_all_gates_have_reason_cards.py`

### Test Files Updated
- `tests/explain/test_data_alignment_disclosure.py`
- `tests/gate/test_data_alignment_gate.py`
- `tests/gui/services/test_gate_summary_service.py`

## Verification Results

All verification commands passed:
- All new reason card tests pass
- `make check` passes with 1640 tests passed
- GateSummary integration tests pass
- Explain service integration tests pass

## SSOT Compliance

- All reason cards derive from existing artifacts/status resolvers only
- No UI recompute introduced
- Deterministic wording and ordering
- Missing artifacts yield explicit cards (never silent PASS)

## Data Contract Compliance

- GateSummary: Every gate includes `reason_cards: list[ReasonCard]`
- Explain: Includes `gate_reason_cards: dict[str, list[ReasonCard]]`
- Cards match exactly between GateSummary and Explain
