# DP6: Explainable Ranking Phase I - System Snapshot

**Timestamp:** 2026-01-17 00:37:01 UTC+8  
**Git Status:** To be captured after implementation

## 1. System Architecture Overview

### 1.1 Current WFS Ranking Pipeline
```
WFS Execution → winners.json → scoring_breakdown.json → Top20/Batch Summary
```

### 1.2 DP6 Phase I Integration Points
```
winners.json + scoring_breakdown.json → ranking_explain_report.json → Explain Service → UI
```

## 2. Key Components for DP6 Implementation

### 2.1 New Models Required
1. **RankingExplainReportV1** - Main report container
2. **RankingExplainItemV1** - Individual ranked item with reason cards
3. **ContextWordingMapping** - CANDIDATE vs FINAL_SELECTION wording

### 2.2 Builder Function
**Location:** `src/control/ranking_explain.py`  
**Signature:**
```python
def build_ranking_explain_report(
    job_id: str,
    winners_data: Dict[str, Any],
    scoring_breakdown: Optional[Dict[str, Any]] = None,
    plateau_artifact_path: Optional[Path] = None,
    ranking_context: Literal["CANDIDATE", "FINAL_SELECTION"] = "CANDIDATE"
) -> RankingExplainReportV1:
```

### 2.3 Reason Codes (Phase I)
| Code | Type | Severity | Condition |
|------|------|----------|-----------|
| RANK_HIGH_NET_OVER_MDD | FACT | INFO | Net/MDD ratio in top 5% |
| RANK_TRADE_COUNT_SUPPORT | FACT | INFO | Trades >= 20 (from min_avg_profit logic) |
| RANK_LOW_TRADE_COUNT_PENALTY | FACT | INFO | Trades < 10 |
| RANK_PLATEAU_STABILITY | ARTIFACT-GATED | INFO | Only if plateau artifact exists |
| DATA_MISSING_PLATEAU_ARTIFACT | DATA_MISSING | INFO | Plateau artifact missing |
| RANK_CONCENTRATION_FACT | HEURISTIC | INFO | top1_share_of_top5 > 0.5 |

## 3. Context-Aware Wording Contract

### 3.1 CANDIDATE Context (候選/候選名單)
- **Title suffix:** "候選策略" (Candidate Strategy)
- **Why phrasing:** "此候選策略..." (This candidate strategy...)
- **Impact phrasing:** "影響候選排名..." (Affects candidate ranking...)
- **Action phrasing:** "檢視候選參數..." (Review candidate parameters...)

### 3.2 FINAL_SELECTION Context (最終/勝出)
- **Title suffix:** "勝出策略" (Winning Strategy)
- **Why phrasing:** "此勝出策略..." (This winning strategy...)
- **Impact phrasing:** "影響最終排名..." (Affects final ranking...)
- **Action phrasing:** "驗證勝出穩定性..." (Validate winning stability...)

### 3.3 Recommended Action Patterns
- "inspect the parameter neighborhood"
- "validate across nearby plateau parameters"
- "review scoring breakdown details"
- "check data alignment artifacts"

## 4. Plateau Artifact Gating Logic

### 4.1 Detection Flow
```
Check plateau_report.json exists?
├── Yes: Extract plateau boolean
│   ├── True: Emit RANK_PLATEAU_STABILITY
│   └── False: No card (plateau false = no stability claim)
└── No: Emit DATA_MISSING_PLATEAU_ARTIFACT
```

### 4.2 Plateau Artifact Path Resolution
1. Check `job_dir / "plateau" / "plateau_report.json"`
2. Check `job_dir / "plateau_report.json"`
3. Check artifacts dict for "plateau_report" key

## 5. Concentration Risk Heuristics

### 5.1 Calculation
```python
top5_scores = [item["final_score"] for item in items[:5]]
top1_share = top5_scores[0] / sum(top5_scores) if top5_scores else 0.0
```

### 5.2 Thresholds (Heuristic)
- **High concentration:** `top1_share > 0.5` (50% of top5 sum)
- **Moderate concentration:** `top1_share > 0.3` (30% of top5 sum)
- **Low concentration:** `top1_share <= 0.3`

### 5.3 INFO-only Statements
- "Top candidate accounts for X% of top 5 score sum"
- "Score distribution shows [high/moderate/low] concentration"
- "Consider reviewing runner-up candidates for diversification"

## 6. Integration Points

### 6.1 Artifact Writing Hook
**File:** `src/core/artifacts.py`  
**Function:** `write_run_artifacts()`  
**Insertion Point:** After winners.json is written
```python
# DP6: Generate ranking explain report
if winners and winners.get("topk"):
    from control.ranking_explain import build_ranking_explain_report
    report = build_ranking_explain_report(
        job_id=manifest.get("run_id", "unknown"),
        winners_data=winners,
        scoring_breakdown=load_scoring_breakdown(run_dir),
        ranking_context="CANDIDATE"  # Default for WFS runs
    )
    report_path = run_dir / "ranking_explain_report.json"
    report_path.write_text(report.json(indent=2), encoding="utf-8")
```

### 6.2 Explain Service Extension
**File:** `src/control/explain_service.py`  
**Function:** `build_job_explain()`  
**Extension:**
```python
def build_job_explain(job_id: str) -> Dict[str, Any]:
    payload = {
        "job_id": job_id,
        "gate_summary": get_gate_summary(job_id),
        "reason_cards": get_reason_cards(job_id),
        # DP6: Add ranking explain
        "ranking_explain": get_ranking_explain(job_id)
    }
    return payload

def get_ranking_explain(job_id: str) -> Dict[str, Any]:
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

### 6.3 Artifact Navigator Extension
**File:** `src/gui/desktop/tabs/report_tab.py`  
**Update artifact_defs:**
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
    ("ranking_explain_report.json", "Ranking explanations and reason cards"),  # DP6
]
```

## 7. Test Strategy

### 7.1 Unit Tests
**File:** `tests/gui/services/test_ranking_explain_builder.py`

**Test Cases:**
1. **Basic winners data** → report created with correct schema
2. **Missing plateau artifact** → DATA_MISSING_PLATEAU_ARTIFACT emitted
3. **Existing plateau artifact** → RANK_PLATEAU_STABILITY emitted
4. **High concentration** → RANK_CONCENTRATION_FACT emitted
5. **Context-aware wording** → CANDIDATE vs FINAL_SELECTION differences
6. **Metric breakdown** → net_over_mdd and trade_bonus calculated correctly

### 7.2 Integration Tests
**File:** `tests/control/test_ranking_explain_integration.py`

**Test Cases:**
1. **Artifact writing integration** → report written to correct path
2. **Explain service integration** → ranking_explain field in payload
3. **Missing artifact handling** → appropriate fallback message

### 7.3 Contract Tests
**File:** `tests/contracts/test_ranking_explain_contract.py`

**Test Cases:**
1. **Schema validation** → V1 schema compliance
2. **Reason card ordering** → deterministic ordering maintained
3. **INFO severity only** → no WARN/FAIL in Phase I

## 8. Non-Negotiable Compliance Checklist

- [ ] **No new root files** - All files under existing directories
- [ ] **No UI recompute** - Read-only from persisted artifacts
- [ ] **SSOT-only implementation** - No hard-coded heuristics as facts
- [ ] **Plateau artifact-gated** - DATA_MISSING if plateau artifact missing
- [ ] **INFO severity only** - No governance semantics in Phase I
- [ ] **Context-aware wording** - CANDIDATE vs FINAL_SELECTION mapping
- [ ] **Research-oriented actions** - "inspect", "validate", "review"
- [ ] **make check = 0 failures** - All existing tests pass

## 9. Implementation Sequence

### Phase 1: Core Models and Builder
1. Create Pydantic models in contracts-friendly location
2. Implement `build_ranking_explain_report()` with basic logic
3. Add context-aware wording mapping
4. Implement plateau artifact detection

### Phase 2: Integration
1. Wire into `write_run_artifacts()` hook
2. Extend explain service with `get_ranking_explain()`
3. Update Artifact Navigator artifact list

### Phase 3: Testing
1. Create unit tests for builder
2. Create integration tests
3. Create contract tests
4. Run `make check` verification

### Phase 4: Evidence and Verification
1. Create evidence bundle with test results
2. Verify all non-negotiables satisfied
3. Create final commit and push

## 10. Risk Mitigation

### 10.1 Technical Risks
- **Circular imports** - Place models in separate contracts module
- **Performance impact** - Builder only runs once per job, not in UI
- **Schema evolution** - Use schema_version field for future compatibility

### 10.2 Compliance Risks
- **INFO severity only** - Strict validation in builder and tests
- **Context wording** - Comprehensive mapping with fallback defaults
- **Artifact gating** - Clear DATA_MISSING pattern for missing artifacts

### 10.3 Testing Risks
- **Fixture complexity** - Use existing test fixtures where possible
- **Integration coverage** - Mock artifact paths for reliable testing
- **Deterministic ordering** - Test reason card ordering stability