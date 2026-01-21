# DP6 Phase III: Gate Summary × Ranking Explain (Default Mapping) - Discovery Evidence

## Discovery Summary
**Phase**: DP6 Phase III - Gate Summary × Ranking Explain (Default Mapping)
**Timestamp**: 2026-01-17T03:15:40Z
**Objective**: Integrate `ranking_explain_report.json` into Gate Summary as a read-only, non-recompute signal, producing PASS/WARN/FAIL outcome based solely on reason codes + severity and the policy mapping.

## 1. Gate Summary Architecture Discovery

### 1.1 Consolidated Gate Summary Service
**File**: `src/gui/services/consolidated_gate_summary_service.py`
**Purpose**: Main service that consolidates gates from multiple sources (system health, gatekeeper, portfolio admission)
**Key Findings**:
- Service follows Hybrid BC v1.1 (no performance metrics in Layer1/Layer2)
- Provides `fetch_all_gates()` method with optional `job_id` parameter
- Returns `GateSummaryV1` with consolidated counts and status
- Already has architecture for context-specific gates (job_id parameter)

### 1.2 Gate Summary Schemas
**File**: `contracts/portfolio/gate_summary_schemas.py`
**Purpose**: Defines data structures for gate summary
**Key Findings**:
- `GateItemV1`: Individual gate with fields: `gate_id`, `gate_name`, `status`, `message`, `reason_codes`, `evidence_refs`
- `GateSummaryV1`: Consolidated summary with counts and overall status
- `GateStatus` enum: `PASS`, `WARN`, `REJECT`, `UNKNOWN`

### 1.3 Ranking Explain Artifact Location
**File**: `control/explain_service.py` (inferred from imports)
**Purpose**: Provides access to ranking explain artifacts
**Key Findings**:
- Function `_get_ranking_explain(job_id)` returns ranking explain data
- Returns structure: `{"available": bool, "artifact": {...}, "message": str}`
- Artifact contains `reasons` array with reason cards

## 2. Ranking Explain Reason Codes Discovery

### 2.1 Ranking Explain Contracts
**File**: `src/contracts/ranking_explain.py`
**Purpose**: Defines ranking explain data structures and reason codes
**Key Findings**:
- `RankingExplainReasonCode` enum with all required Phase III codes:
  - `CONCENTRATION_HIGH`, `CONCENTRATION_MODERATE`
  - `MDD_INVALID_OR_ZERO`, `METRICS_MISSING_REQUIRED_FIELDS`
  - `PLATEAU_WEAK_STABILITY`, `PLATEAU_MISSING_ARTIFACT`
  - `TRADES_TOO_LOW_FOR_RANKING`, `AVG_PROFIT_BELOW_MIN`
- `RankingExplainSeverity` enum: `INFO`, `WARN`, `ERROR`

## 3. Integration Points Discovery

### 3.1 Gate Summary Service Extension Points
**Location**: `ConsolidatedGateSummaryService.fetch_all_gates(job_id: Optional[str])`
**Integration Strategy**: 
- Service already accepts optional `job_id` parameter
- Can add ranking explain gates when `job_id` is provided
- Returns `GateItemV1` with `gate_id="ranking_explain"`

### 3.2 No-Recompute Constraint Verification
**Constraint**: Gate summary must NOT import `ranking_explain_builder.py` or recompute metrics
**Verification**: 
- Service imports `_get_ranking_explain` from `control.explain_service`
- Only reads existing artifact, no recomputation
- Complies with "Details Ban" - uses only code + severity, not details/metrics/scores

## 4. Mapping Policy Discovery

### 4.1 Required Default Mapping (from Phase III requirements)
**BLOCK → FAIL**:
- `CONCENTRATION_HIGH`
- `MDD_INVALID_OR_ZERO`
- `METRICS_MISSING_REQUIRED_FIELDS`

**WARN_ONLY → WARN**:
- `CONCENTRATION_MODERATE`
- `PLATEAU_WEAK_STABILITY`
- `PLATEAU_MISSING_ARTIFACT`
- `TRADES_TOO_LOW_FOR_RANKING`
- `AVG_PROFIT_BELOW_MIN`

### 4.2 Missing Artifact Handling
**Policy Option A**: WARN status when `ranking_explain_report.json` missing
**Implementation**: Returns `GateItemV1` with `gate_id="ranking_explain_missing"` and `status=WARN`

## 5. Implementation Architecture

### 5.1 Created Files
1. `src/contracts/ranking_explain_gate_policy.py` - Mapping policy module
2. `tests/contracts/test_ranking_explain_gate_policy.py` - Policy unit tests
3. `tests/gui/services/test_ranking_explain_gate_integration.py` - Integration tests

### 5.2 Modified Files
1. `src/gui/services/consolidated_gate_summary_service.py` - Added ranking explain gate section builder

### 5.3 Key Implementation Details
- **Mapping Policy**: Deterministic mapping from reason codes to gate impacts
- **Section Builder**: `build_ranking_explain_gate_section(job_id)` method
- **Job Context**: Gates only included when `job_id` provided to `fetch_all_gates()`
- **Evidence References**: Includes `job:{job_id}/ranking_explain_report.json` reference
- **No Recompute**: Uses existing `_get_ranking_explain` function, no recomputation

## 6. Test Coverage Discovery

### 6.1 Unit Tests
- Mapping policy completeness and correctness
- Gate status determination from impacts
- Default mapping coverage verification

### 6.2 Integration Tests
- Ranking explain gate section building with valid artifact
- Missing artifact handling (WARN status)
- BLOCK reason mapping (FAIL status)
- Multiple reason cards aggregation
- Evidence references correctness
- No-recompute constraint verification
- Job-specific gate inclusion

## 7. SSOT (Single Source of Truth) Verification

### 7.1 Ranking Explain Artifact
**SSOT**: `outputs/jobs/{job_id}/ranking_explain_report.json`
**Usage**: Read-only access via `_get_ranking_explain(job_id)`
**Compliance**: No recompute, only reads existing artifact

### 7.2 Reason Codes
**SSOT**: `RankingExplainReasonCode` enum in `src/contracts/ranking_explain.py`
**Usage**: Direct enum usage, no string literals
**Compliance**: All required Phase III codes available

### 7.3 Gate Status Mapping
**SSOT**: `DEFAULT_RANKING_EXPLAIN_GATE_MAP` in `src/contracts/ranking_explain_gate_policy.py`
**Usage**: Deterministic mapping, no heuristic guessing
**Compliance**: Exactly matches Phase III requirements

## 8. Discovery Conclusions

1. **Architecture Fit**: Consolidated gate summary service already supports job-specific gates via `job_id` parameter
2. **No-Recompute Compliance**: Can use existing `_get_ranking_explain` function without importing `ranking_explain_builder.py`
3. **Mapping Feasibility**: All required reason codes exist in SSOT contracts
4. **Integration Simplicity**: Straightforward addition of ranking explain gate section builder
5. **Test Coverage**: Comprehensive test suite possible with existing testing patterns

**Implementation Ready**: Yes - all discovery confirms feasibility and compliance with Phase III requirements.