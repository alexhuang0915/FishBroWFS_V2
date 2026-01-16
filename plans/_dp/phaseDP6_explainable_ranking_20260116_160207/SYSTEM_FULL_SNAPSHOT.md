# DP6 System Full Snapshot: Explainable Ranking for WFS Winners/Top20

**Timestamp:** 2026-01-16T16:02:07Z  
**Scope:** WFS ranking system architecture and SSOT artifacts

## 1. System Architecture Overview

### 1.1 WFS Pipeline Stages
```
Stage 0 (Coarse) → Stage 1 (TopK) → Stage 2 (Confirm) → Winners/Top20
```

### 1.2 Artifact Flow
```
Run Execution → write_run_artifacts() → Job Artifact Directory
                                            ├── manifest.json
                                            ├── metrics.json
                                            ├── config_snapshot.json
                                            ├── winners.json (V2)
                                            ├── scoring_breakdown.json
                                            └── governance_summary.json
```

## 2. Core SSOT Components

### 2.1 Scoring Formula (SSOT)
**File:** `src/wfs/scoring_guards.py`
**Function:** `compute_final_score()`
**Formula:** `FinalScore = (Net/(MDD+eps)) * TradeMultiplier`
**Parameters:**
- `t_max = 100` (maximum trades for cap)
- `alpha = 0.25` (trade exponent)
- `min_avg_profit = 5.0` (minimum edge gate)
- `robust_cliff_threshold = 0.7` (cliff gate threshold)

### 2.2 Winners Schema (SSOT)
**File:** `tests/fixtures/artifacts/winners_v2_valid.json`
**Required Fields:**
- `schema: "v2"`
- `stage_name: string`
- `run_id: string`
- `config_hash: string`
- `topk: array` of candidate objects

**Candidate Object:**
```json
{
  "candidate_id": "string",
  "strategy_id": "string",
  "symbol": "string",
  "timeframe": "string",
  "metrics": {
    "net_profit": "float",
    "max_dd": "float (negative)",
    "trades": "int",
    "param_id": "int"
  },
  "score": "float"
}
```

### 2.3 Canonical Metrics (SSOT)
**File:** `src/research/metrics.py`
**Class:** `CanonicalMetrics`
**Fields:**
- `run_id: str`
- `net_profit: float`
- `max_drawdown: float`
- `trades: int`
- `score_net_mdd: float` (Net/|MDD|)
- `score_final: float` (score_net_mdd * trades^0.25)

## 3. Ranking Infrastructure

### 3.1 Batch Ranking System
**File:** `src/control/batch_aggregate.py`
**Function:** `compute_batch_summary()`
**Ranking Logic:**
```python
scored_jobs_sorted = sorted(
    scored_jobs,
    key=lambda j: (-float(j["score"]), j["job_id"])
)
```

### 3.2 Score Extraction
**File:** `src/control/batch_aggregate.py`
**Function:** `extract_score_from_manifest()`
**Priority Order:**
1. Direct `score` field in manifest
2. Nested `metrics.score` field
3. `final_score` field

### 3.3 Top20 Selection
**Parameter:** `top_k = 20` (configurable)
**Output:** `top_k` field in batch summary

## 4. Artifact Writing Pipeline

### 4.1 Core Artifact Writer
**File:** `src/core/artifacts.py`
**Function:** `write_run_artifacts()`
**Creates:**
- `manifest.json`
- `config_snapshot.json`
- `metrics.json`
- `winners.json` (V2 schema)
- `README.md`
- `logs.txt`

### 4.2 Scoring Artifact Writer
**File:** `src/wfs/artifact_reporting.py`
**Function:** `write_governance_and_scoring_artifacts()`
**Creates:**
- `governance_summary.json`
- `scoring_breakdown.json`

### 4.3 Job Artifact Directory Structure
```
outputs/jobs/<job_id>/
├── manifest.json
├── metrics.json
├── config_snapshot.json
├── winners.json
├── scoring_breakdown.json
├── governance_summary.json
├── strategy_report_v1.json
├── portfolio_config.json
├── admission_report.json
└── gate_summary_v1.json
```

## 5. Integration Points

### 5.1 Explain System
**File:** `tests/gui/services/test_explain_adapter.py`
**Payload Structure:** Includes gate summaries and reason cards
**Extension Point:** Add `ranking_explain` field

### 5.2 Artifact Navigator
**File:** `src/gui/desktop/tabs/report_tab.py`
**Artifact List:** Predefined list of artifact definitions
**Extension Point:** Add `ranking_explain_report.json`

### 5.3 Control API
**File:** `src/control/api.py`
**Job Artifacts Endpoint:** `/api/v1/jobs/{job_id}/artifacts`
**Extension Point:** Serve `ranking_explain_report.json`

## 6. Thresholds and Constants (SSOT)

### 6.1 Scoring Guard Config
```python
@dataclass
class ScoringGuardConfig:
    t_max: int = 100
    alpha: float = 0.25
    min_avg_profit: float = 5.0
    robust_cliff_threshold: float = 0.7
    cluster_bimodality_threshold: float = 0.3
    min_cluster_size: int = 10
```

### 6.2 Ranking Thresholds
1. **High Net/MDD:** Top 5% percentile (requires batch context)
2. **Trade Count Support:** `trades >= 20` (derived from min_avg_profit)
3. **Low Trade Penalty:** `trades < 10` (edge case)
4. **Concentration Risk:** `top_score > 0.5 * sum(top_5_scores)`

### 6.3 Plateau Stability
**Requires Discovery:** Plateau artifacts not yet examined
**Potential Sources:**
- `plateau_report.json`
- `chosen_params.json`
- Stability metrics in governance artifacts

## 7. Data Flow for DP6 Implementation

### 7.1 Input Sources
1. **winners.json** → TopK candidates with metrics
2. **scoring_breakdown.json** → Scoring details and guards
3. **batch summary** → Relative ranking context
4. **plateau artifacts** → Stability metrics (if available)

### 7.2 Processing Steps
1. Read winners.json and extract candidate metrics
2. Compute derived metrics (Net/MDD, trade bonus)
3. Determine relative rankings within batch/job
4. Apply deterministic reason card rules
5. Generate ranking_explain_report.json

### 7.3 Output Artifact
**File:** `ranking_explain_report.json`
**Location:** `outputs/jobs/<job_id>/ranking_explain_report.json`
**Schema:** As defined in DP6 requirements

## 8. Dependencies and Constraints

### 8.1 Hard Dependencies
1. `winners.json` (V2 schema) must exist
2. Scoring formula constants from `ScoringGuardConfig`
3. Batch context for relative rankings

### 8.2 Soft Dependencies
1. `scoring_breakdown.json` (for detailed scoring info)
2. Plateau artifacts (for stability metrics)
3. Batch summary (for percentile calculations)

### 8.3 Constraints
1. **No new root files** → Must integrate with existing structure
2. **No UI recompute** → All explanations precomputed in artifact
3. **Deterministic** → Same inputs → same outputs
4. **SSOT-only** → No heuristic guessing outside discovered SSOT

## 9. Testing Infrastructure

### 9.1 Existing Test Patterns
**Location:** `tests/wfs/test_artifact_reporting.py`
**Pattern:** Test artifact generation and schema validation

### 9.2 Required Test Coverage
1. Unit tests for `build_ranking_explain_report()`
2. Integration tests with existing artifact pipeline
3. Explain adapter extension tests
4. Artifact navigator integration tests

### 9.3 Test Data Sources
1. `tests/fixtures/artifacts/winners_v2_valid.json`
2. `tests/fixtures/artifacts/governance_valid.json`
3. Generated test jobs with known rankings

## 10. Implementation Sequence

### Phase 1: Core Builder
1. Create `RankingExplainReport` Pydantic model
2. Implement `build_ranking_explain_report()` function
3. Add unit tests

### Phase 2: Pipeline Integration
1. Integrate with `write_run_artifacts()` or post-write hook
2. Add to job artifact directory
3. Test end-to-end artifact generation

### Phase 3: Explain Integration
1. Extend Explain adapter to read ranking explain report
2. Add to explain payload structure
3. Test explain endpoint integration

### Phase 4: UI Integration
1. Add to Artifact Navigator artifact list
2. Test UI rendering
3. Verify end-to-end user experience

**Snapshot Completed:** 2026-01-16T16:02:07Z