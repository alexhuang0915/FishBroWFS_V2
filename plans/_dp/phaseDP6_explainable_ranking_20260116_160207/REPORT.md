# DP6 Report: Explainable Ranking Implementation Plan

**Timestamp:** 2026-01-16T16:02:07Z  
**Phase:** DP6 - Explainable Ranking for WFS Winners/Top20

## 1. Reason Codes and Thresholds

### 1.1 Required Ranking Reason Codes

#### RANK_HIGH_NET_OVER_MDD
**Code:** `RANK_HIGH_NET_OVER_MDD`  
**Title:** "High return vs drawdown efficiency"  
**Severity:** `INFO`  
**Condition:** `Net/MDD ratio in top 5% of batch`  
**Why:** "Net/MDD = {value} ranked in top 5%"  
**Impact:** "Indicates strong capital efficiency"  
**Recommended Action:** "Validate stability across nearby plateau parameters"  
**Evidence Artifact:** `ranking_metrics.json`  
**Evidence Path:** `$.items[{rank}].metric_breakdown.net_over_mdd`  
**SSOT Source:** `src/wfs/scoring_guards.py` compute_final_score

#### RANK_TRADE_COUNT_SUPPORT
**Code:** `RANK_TRADE_COUNT_SUPPORT`  
**Title:** "Adequate trade count for statistical significance"  
**Severity:** `INFO`  
**Condition:** `trades >= 20`  
**Why:** "Trade count {trades} meets minimum threshold for statistical significance"  
**Impact:** "Reduces likelihood of results being due to random chance"  
**Recommended Action:** "Monitor trade frequency consistency across parameters"  
**Evidence Artifact:** `winners.json`  
**Evidence Path:** `$.topk[{index}].metrics.trades`  
**SSOT Source:** `ScoringGuardConfig.min_avg_profit = 5.0` implies minimum trades

#### RANK_PLATEAU_STABILITY
**Code:** `RANK_PLATEAU_STABILITY`  
**Title:** "Parameter plateau stability confirmed"  
**Severity:** `INFO`  
**Condition:** `Plateau stability score >= 0.8` (requires plateau artifacts)  
**Why:** "Parameter neighborhood shows consistent performance"  
**Impact:** "Reduces overfitting risk, increases robustness"  
**Recommended Action:** "Consider expanding parameter search around plateau"  
**Evidence Artifact:** `plateau_report.json`  
**Evidence Path:** `$.stability_metrics.score`  
**SSOT Source:** To be discovered in plateau artifacts

#### RANK_CONCENTRATION_RISK
**Code:** `RANK_CONCENTRATION_RISK`  
**Title:** "High concentration in top performer"  
**Severity:** `WARN`  
**Condition:** `top_score > 0.5 * sum(top_5_scores)`  
**Why:** "Top score represents {percentage}% of top 5 total"  
**Impact:** "Potential over-reliance on single parameter set"  
**Recommended Action:** "Diversify across multiple high-performing parameters"  
**Evidence Artifact:** `ranking_explain_report.json`  
**Evidence Path:** `$.concentration_metrics.top_score_ratio`  
**SSOT Source:** Derived from winners.json topk scores

#### RANK_LOW_TRADE_COUNT_PENALTY
**Code:** `RANK_LOW_TRADE_COUNT_PENALTY`  
**Title:** "Low trade count reduces statistical confidence"  
**Severity:** `WARN`  
**Condition:** `trades < 10`  
**Why:** "Only {trades} trades executed, below minimum for reliable inference"  
**Impact:** "Increased risk of results being random"  
**Recommended Action:** "Seek parameters with higher trade frequency"  
**Evidence Artifact:** `winners.json`  
**Evidence Path:** `$.topk[{index}].metrics.trades`  
**SSOT Source:** Edge case handling in scoring guards

### 1.2 Additional Recommended Reason Codes

#### RANK_EDGE_GATE_PASSED
**Code:** `RANK_EDGE_GATE_PASSED`  
**Title:** "Minimum edge gate satisfied"  
**Severity:** `INFO`  
**Condition:** `avg_profit >= 5.0`  
**Why:** "Average profit ${avg_profit:.2f} meets minimum threshold"  
**Impact:** "Strategy generates meaningful profit per trade"  
**Evidence Artifact:** `scoring_breakdown.json`  
**Evidence Path:** `$.guards.edge_gate`

#### RANK_CLIFF_GATE_PASSED
**Code:** `RANK_CLIFF_GATE_PASSED`  
**Title:** "Robustness cliff gate satisfied"  
**Severity:** `INFO`  
**Condition:** `All neighbor scores >= 70% of base score`  
**Why:** "Parameter neighborhood maintains {percentage}% of base performance"  
**Impact:** "Performance is robust to small parameter changes"  
**Evidence Artifact:** `scoring_breakdown.json`  
**Evidence Path:** `$.guards.cliff_gate`

## 2. Artifact Schema Design

### 2.1 ranking_explain_report.json Schema
```json
{
  "schema_version": "1.0",
  "ranking_type": "top20 | winners",
  "score_formula": "Net/MDD * Trades^0.25",
  "items": [
    {
      "rank": 1,
      "strategy_id": "string",
      "params_fingerprint": "string",
      "final_score": 1.2345,
      "metric_breakdown": {
        "net_profit": 123456,
        "max_drawdown": 34567,
        "trades": 420,
        "net_over_mdd": 3.56,
        "trade_bonus": 5.14
      },
      "reason_cards": [
        {
          "code": "RANK_HIGH_NET_OVER_MDD",
          "title": "High return vs drawdown efficiency",
          "severity": "INFO",
          "why": "Net/MDD = 3.56 ranked in top 5%",
          "impact": "Indicates strong capital efficiency",
          "recommended_action": "Validate stability across nearby plateau parameters",
          "evidence_artifact": "ranking_metrics.json",
          "evidence_path": "$.items[0].metric_breakdown.net_over_mdd",
          "action_target": "outputs/jobs/<job_id>/ranking_metrics.json"
        }
      ]
    }
  ],
  "batch_context": {
    "total_candidates": 150,
    "score_percentiles": {
      "p95": 4.2,
      "p75": 2.8,
      "p50": 1.5,
      "p25": 0.7
    }
  }
}
```

### 2.2 Integration with Existing Artifacts

#### 2.2.1 Required Input Artifacts
1. **winners.json** (V2 schema) - Source of candidates and metrics
2. **scoring_breakdown.json** - Source of scoring details and guard results
3. **batch summary** (optional) - For percentile calculations

#### 2.2.2 Generated Artifacts
1. **ranking_explain_report.json** - Primary DP6 output
2. **ranking_metrics.json** (optional) - Extended metrics for evidence

## 3. Implementation Details

### 3.1 Builder Function Implementation

**File:** `src/control/ranking_explain.py`
```python
from typing import Dict, List, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from datetime import datetime

class ReasonCard(BaseModel):
    code: str
    title: str
    severity: str  # "INFO", "WARN", "ERROR"
    why: str
    impact: str
    recommended_action: str
    evidence_artifact: str
    evidence_path: str
    action_target: str

class RankingItem(BaseModel):
    rank: int
    strategy_id: str
    params_fingerprint: str
    final_score: float
    metric_breakdown: Dict[str, float]
    reason_cards: List[ReasonCard]

class RankingExplainReport(BaseModel):
    schema_version: str = "1.0"
    ranking_type: str  # "top20" or "winners"
    score_formula: str = "Net/MDD * Trades^0.25"
    items: List[RankingItem]
    batch_context: Optional[Dict] = None
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

def build_ranking_explain_report(
    job_id: str,
    winners_data: Dict,
    scoring_breakdown: Optional[Dict] = None,
    batch_context: Optional[Dict] = None
) -> RankingExplainReport:
    """
    Build explainable ranking report from winners and scoring data.
    """
    # Implementation details...
```

### 3.2 Reason Card Generation Logic

```python
def generate_reason_cards(
    item: Dict,
    rank: int,
    batch_context: Dict,
    scoring_breakdown: Optional[Dict]
) -> List[ReasonCard]:
    """Generate deterministic reason cards for a ranked item."""
    cards = []
    
    # RANK_HIGH_NET_OVER_MDD
    net_over_mdd = item["metric_breakdown"]["net_over_mdd"]
    if batch_context and net_over_mdd >= batch_context["score_percentiles"]["p95"]:
        cards.append(ReasonCard(
            code="RANK_HIGH_NET_OVER_MDD",
            title="High return vs drawdown efficiency",
            severity="INFO",
            why=f"Net/MDD = {net_over_mdd:.2f} ranked in top 5%",
            impact="Indicates strong capital efficiency",
            recommended_action="Validate stability across nearby plateau parameters",
            evidence_artifact="ranking_metrics.json",
            evidence_path=f"$.items[{rank}].metric_breakdown.net_over_mdd",
            action_target=f"outputs/jobs/{job_id}/ranking_metrics.json"
        ))
    
    # RANK_TRADE_COUNT_SUPPORT
    trades = item["metric_breakdown"]["trades"]
    if trades >= 20:
        cards.append(ReasonCard(
            code="RANK_TRADE_COUNT_SUPPORT",
            title="Adequate trade count for statistical significance",
            severity="INFO",
            why=f"Trade count {trades} meets minimum threshold for statistical significance",
            impact="Reduces likelihood of results being due to random chance",
            recommended_action="Monitor trade frequency consistency across parameters",
            evidence_artifact="winners.json",
            evidence_path=f"$.topk[{rank}].metrics.trades",
            action_target=f"outputs/jobs/{job_id}/winners.json"
        ))
    
    # Additional reason cards...
    return cards
```

### 3.3 Integration Points

#### 3.3.1 Artifact Writing Integration
**Location:** `src/core/artifacts.py` (extend write_run_artifacts)
```python
def write_run_artifacts(
    run_dir: Path,
    manifest: dict,
    config_snapshot: dict,
    metrics: dict,
    winners: Optional[dict] = None,
) -> None:
    # Existing artifact writing...
    
    # DP6: Generate ranking explain report if winners exist
    if winners and winners.get("topk"):
        from control.ranking_explain import build_ranking_explain_report
        report = build_ranking_explain_report(
            job_id=manifest.get("run_id", "unknown"),
            winners_data=winners,
            scoring_breakdown=load_scoring_breakdown(run_dir),
            batch_context=get_batch_context(run_dir)
        )
        report_path = run_dir / "ranking_explain_report.json"
        report_path.write_text(report.json(indent=2), encoding="utf-8")
```

#### 3.3.2 Explain Integration
**Location:** `src/gui/services/explain_adapter.py`
```python
def get_explain_payload(job_id: str) -> Dict:
    payload = {
        "job_id": job_id,
        "gate_summary": get_gate_summary(job_id),
        "reason_cards": get_reason_cards(job_id),
        # DP6: Add ranking explain
        "ranking_explain": get_ranking_explain(job_id)
    }
    return payload

def get_ranking_explain(job_id: str) -> Dict:
    """Load ranking explain report if available."""
    artifact_path = get_job_artifact_path(job_id, "ranking_explain_report.json")
    if artifact_path.exists():
        return json.loads(artifact_path.read_text(encoding="utf-8"))
    else:
        return {
            "available": False,
            "message": "Ranking explain report not available for this job",
            "action": "Run WFS with ranking explain enabled"
        }
```

## 4. Test Plan

### 4.1 Unit Tests
**File:** `tests/gui/services/test_ranking_explain_builder.py`
```python
def test_build_ranking_explain_report():
    """Test building ranking explain report from winners data."""
    winners = {
        "schema": "v2",
        "topk": [
            {
                "candidate_id": "test:1",
                "strategy_id": "sma_cross",
                "metrics": {
                    "net_profit": 1000.0,
                    "max_dd": -200.0,
                    "trades": 50
                },
                "score": 4.2
            }
        ]
    }
    
    report = build_ranking_explain_report(
        job_id="test_job",
        winners_data=winners,
        batch_context={"score_percentiles": {"p95": 4.0}}
    )
    
    assert report.schema_version == "1.0"
    assert len(report.items) == 1
    assert report.items[0].rank == 1
    assert len(report.items[0].reason_cards) > 0
```

### 4.2 Integration Tests
**File:** `tests/control/test_job_explain_endpoint.py`
```python
def test_explain_endpoint_includes_ranking_explain():
    """Test that explain endpoint includes ranking explain when available."""
    # Create test job with ranking explain report
    # Call explain endpoint
    # Verify ranking_explain field in response
```

### 4.3 Artifact Contract Tests
**File:** `tests/test_ranking_explain_artifact_contract.py`
```python
def test_ranking_explain_report_schema():
    """Test that generated report matches schema."""
    report = generate_test_report()
    validated = RankingExplainReport.model_validate(report)
    assert validated.schema_version == "1.0"
```

## 5. Deployment and Verification

### 5.1 Verification Commands
```bash
# Run unit tests
python3 -m pytest -q tests/gui/services/test_ranking_explain_builder.py

# Run integration tests
python3 -m pytest -q tests/control/test_job_explain_endpoint.py

# Run artifact contract tests
python3 -m pytest -q tests/test_ranking_explain_artifact_contract.py

# Verify make check passes
make check
```

### 5.2 Success Criteria
1. ✅ Every Top20/winner has explainable reason cards
2. ✅ Explanations come only from SSOT metrics
3. ✅ Artifact is persisted and browsable
4. ✅ Explain + Artifact Navigator surface it consistently
5. ✅ codebase_search-first discovery documented
6. ✅ make check = 0 failures
7. ✅ No new root files

## 6. Timeline and Dependencies

### 6.1 Phase 1: Core Implementation (Day 1)
- Create RankingExplainReport model
- Implement build_ranking_explain_report()
- Add unit tests

### 6.2 Phase 2: Pipeline Integration (Day 2)
- Integrate with write_run_artifacts()
- Test end-to-end artifact generation
- Add integration tests

### 6.3 Phase 3: UI Integration (Day 3)
- Extend Explain adapter
- Update Artifact Navigator
- Test UI rendering

### 6.4 Phase 4: Validation and Deployment (Day 4)
- Run full test suite
- Verify make check passes
- Create final evidence bundle

**Report Generated:** 2026-01-16T16:02:07Z