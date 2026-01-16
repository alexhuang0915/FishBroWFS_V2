# DP6 Discovery: Explainable Ranking for WFS Winners/Top20

**Timestamp:** 2026-01-16T16:02:07Z  
**Discovery Method:** codebase_search-first exploration  
**Objective:** Locate WFS result writers, ranking metrics, and SSOT artifacts for explainable ranking implementation

## 1. WFS Result Writers (Winners/Top20)

### 1.1 Winners.json Artifact Structure
**Location:** `src/core/artifacts.py` (write_run_artifacts function)
**SSOT:** Winners are written as `winners.json` in job artifact directories
**Schema:** V2 schema enforced (legacy no longer supported)

**Key Code Block:**
```python
def write_run_artifacts(
    run_dir: Path,
    manifest: dict,
    config_snapshot: dict,
    metrics: dict,
    winners: Optional[dict] = None,
) -> None:
    """
    Write all standard artifacts for a run.
    
    Creates the following files:
    - manifest.json: Full AuditSchema data
    - config_snapshot.json: Original/normalized config
    - metrics.json: Performance metrics
    - winners.json: Top-K results (v2 schema only)
    - README.md: Human-readable summary
    - logs.txt: Execution logs (empty initially)
    """
```

### 1.2 Winners.json V2 Schema
**Location:** `tests/fixtures/artifacts/winners_v2_valid.json`
**Structure:**
```json
{
  "schema": "v2",
  "stage_name": "stage1_topk",
  "run_id": "test-123",
  "config_hash": "abc123",
  "topk": [
    {
      "candidate_id": "test:1",
      "strategy_id": "donchian_atr",
      "symbol": "CME.MNQ",
      "timeframe": "60m",
      "metrics": {
        "net_profit": 100.0,
        "max_dd": -10.0,
        "trades": 10,
        "param_id": 123
      },
      "score": 100.0
    }
  ]
}
```

### 1.3 Pipeline Winners Generation
**Location:** `src/pipeline/runner_adapter.py`
**SSOT:** Stage-specific winners generation with ranking

**Stage 0 (Coarse):**
```python
winners = {
    "topk": [
        {
            "param_id": int(r.param_id),
            "proxy_value": float(r.proxy_value),
        }
        for r in stage0_results
        if r.param_id in topk_param_ids
    ],
    "notes": {
        "schema": "v1",
        "stage": "stage0_coarse",
        "topk_count": len(topk_param_ids),
    },
}
```

**Stage 1 (TopK):**
```python
winners = {
    "topk": winners_list,
    "notes": {
        "schema": "v1",
        "stage": "stage1_topk",
        "topk_count": len(winners_list),
    },
}
```

**Stage 2 (Confirm):**
```python
winners = {
    "topk": winners_list,
    "notes": {
        "schema": "v1",
        "stage": "stage2_confirm",
        "full_confirm": True,
    },
}
```

## 2. Ranking Metrics and Scoring Formula

### 2.1 Scoring Formula SSOT
**Location:** `src/wfs/scoring_guards.py` (compute_final_score function)
**Formula:** `FinalScore = (Net/(MDD+eps)) * TradeMultiplier`
**Trade Multiplier:** `min(Trades, T_MAX)^ALPHA` where T_MAX=100, ALPHA=0.25
**Minimum Edge Gate:** `Net/Trades >= MinAvgProfit` (default 5.0)

**Key Code Block:**
```python
def compute_final_score(
    net_profit: float,
    max_dd: float,
    trades: int,
    config: ScoringGuardConfig
) -> Tuple[float, Dict[str, float]]:
    """
    Compute final score with anti-gaming guards.
    
    FinalScore = (Net/(MDD+eps)) * TradeMultiplier
    """
```

### 2.2 Canonical Metrics Extraction
**Location:** `src/research/extract.py` (extract_canonical_metrics function)
**SSOT:** Aggregates metrics from winners.json topk items
**Derived Scores:**
- `score_net_mdd = net_profit / max_drawdown` (raises if MDD=0)
- `score_final = score_net_mdd * (trades ** 0.25)`

**Key Code Block:**
```python
# score_final = score_net_mdd * (trades ** 0.25)
score_final = score_net_mdd * (total_trades ** 0.25) if total_trades > 0 else 0.0
```

### 2.3 Scoring Breakdown Artifact
**Location:** `src/wfs/artifact_reporting.py` (write_governance_and_scoring_artifacts)
**Artifact:** `scoring_breakdown.json` written to job directory
**Structure:**
```json
{
  "schema_version": "1.0",
  "job_id": "test_job",
  "created_at": "2025-01-01T00:00:00Z",
  "final": {
    "final_score": 8.5,
    "robustness_factor": 0.92,
    "trade_multiplier": 2.1
  },
  "raw": {
    "net_profit": 1200.0,
    "mdd": 180.0,
    "trades": 40
  },
  "guards": {
    "edge_gate": {"passed": True, "threshold": 5.0, "value": 30.0},
    "cliff_gate": {"passed": True, "threshold": 0.7, "value": 0.92}
  }
}
```

## 3. Job Artifact Structure and Ranking

### 3.1 Job Artifact Directory Layout
**Location:** `src/core/deployment/job_deployment_builder.py` (find_job_artifacts)
**SSOT:** Standard job artifacts include:
- `strategy_report_v1.json`
- `portfolio_config.json`
- `admission_report.json`
- `gate_summary_v1.json`
- `config_snapshot.json`
- `input_manifest.json`
- `winners.json`
- `manifest.json`

### 3.2 Batch Ranking and Top20
**Location:** `src/control/batch_aggregate.py` (compute_batch_summary)
**SSOT:** Computes TopK jobs based on score field
**Ranking Logic:**
```python
scored_jobs_sorted = sorted(
    scored_jobs,
    key=lambda j: (-float(j["score"]), j["job_id"])
)
```

### 3.3 Score Extraction from Manifests
**Location:** `src/control/batch_aggregate.py` (extract_score_from_manifest)
**SSOT:** Extracts score from job manifest with priority:
1. Direct `score` field
2. Nested in `metrics.score`
3. `final_score` field

## 4. Explain Integration Points

### 4.1 Explain Payload Structure
**Location:** `tests/gui/services/test_explain_adapter.py`
**SSOT:** Explain system expects structured payload with reason cards
**Integration:** Currently uses gate summaries and reason cards

### 4.2 Artifact Navigator Integration
**Location:** `src/gui/desktop/tabs/report_tab.py`
**SSOT:** Artifact list includes `scoring_breakdown.json`
**Artifact Definitions:**
```python
artifact_defs = [
    ("metrics.json", "Primary performance metrics"),
    ("manifest.json", "Run configuration and metadata"),
    ("run_record.json", "Execution timeline and logs"),
    ("equity.parquet", "Equity curve time series"),
    ("trades.parquet", "Individual trade records"),
    ("report.json", "Comprehensive analysis report"),
    ("governance_summary.json", "Governance compliance snapshot"),
    ("scoring_breakdown.json", "Detailed scoring breakdown"),
]
```

## 5. Required SSOT Artifacts for DP6

### 5.1 Existing Metrics Available
1. **Net Profit:** `net_profit` from winners.json metrics
2. **Max Drawdown:** `max_dd` from winners.json metrics (negative value)
3. **Trades:** `trades` from winners.json metrics
4. **Net/MDD Ratio:** Computed as `net_profit / abs(max_dd)`
5. **Trade Bonus:** Computed as `min(trades, 100)^0.25`
6. **Final Score:** Computed as `(net_profit / abs(max_dd)) * min(trades, 100)^0.25`

### 5.2 Thresholds and Constants
**Location:** `src/wfs/scoring_guards.py` (ScoringGuardConfig)
**SSOT Thresholds:**
- `t_max = 100` (trade cap)
- `alpha = 0.25` (trade exponent)
- `min_avg_profit = 5.0` (minimum edge gate)
- `robust_cliff_threshold = 0.7` (70% of base for cliff gate)

### 5.3 Ranking Reason Code Thresholds
Based on discovered SSOT:
1. **RANK_HIGH_NET_OVER_MDD:** Top 5% of Net/MDD ratio
2. **RANK_TRADE_COUNT_SUPPORT:** Trades >= 20 (from min_avg_profit logic)
3. **RANK_PLATEAU_STABILITY:** Requires plateau artifacts (to be discovered)
4. **RANK_CONCENTRATION_RISK:** Top score > 50% of sum of top 5 scores
5. **RANK_LOW_TRADE_COUNT_PENALTY:** Trades < 10 (edge case handling)

## 6. Implementation Location Recommendations

### 6.1 Ranking Explain Report Writer
**Recommended Location:** `src/control/ranking_explain.py`
**Integration Point:** After winners.json is written in `write_run_artifacts`
**Artifact Path:** `outputs/jobs/<job_id>/ranking_explain_report.json`

### 6.2 Builder Function Signature
```python
def build_ranking_explain_report(
    job_id: str,
    winners_data: dict,
    scoring_breakdown: Optional[dict] = None
) -> RankingExplainReport:
    """
    Build explainable ranking report from winners and scoring data.
    
    Reads existing winners.json and scoring_breakdown.json if available.
    Generates deterministic reason cards based on SSOT metrics.
    """
```

### 6.3 Explain Integration
**Location:** `src/gui/services/explain_adapter.py`
**Extension:** Add `ranking_explain` field to explain payload
**Fallback:** If artifact missing → explicit explain message (DP4 pattern)

### 6.4 Artifact Navigator Integration
**Location:** `src/gui/desktop/tabs/report_tab.py`
**Addition:** Add `ranking_explain_report.json` to artifact definitions
**View:** Clicking opens the report with structured reason cards

## 7. Discovery Summary

### 7.1 Key Findings
1. **Winners SSOT:** `winners.json` in job artifact directories (V2 schema)
2. **Scoring Formula SSOT:** `src/wfs/scoring_guards.py` compute_final_score
3. **Metrics SSOT:** `net_profit`, `max_dd`, `trades` from winners.json metrics
4. **Thresholds SSOT:** `ScoringGuardConfig` with t_max=100, alpha=0.25, min_avg_profit=5.0
5. **Artifact Integration:** `scoring_breakdown.json` already exists for scoring details

### 7.2 Gaps Identified
1. No existing `ranking_explain_report.json` artifact
2. No deterministic reason card generation for rankings
3. No integration of ranking explanations into Explain system
4. Plateau stability metrics require additional discovery

### 7.3 Next Steps
1. Implement `build_ranking_explain_report` function
2. Create `RankingExplainReport` Pydantic model
3. Integrate with existing artifact writing pipeline
4. Extend Explain adapter to include ranking explanations
5. Update Artifact Navigator to display new artifact

**Discovery Completed:** 2026-01-16T16:02:07Z