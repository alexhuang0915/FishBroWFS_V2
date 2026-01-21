# DP6 Phase I: Explainable Ranking Discovery Evidence

## 1. SSOT Discovery Summary

### 1.1 Scoring Formula SSOT
**Location:** `src/wfs/scoring_guards.py`
**Key Function:** `compute_final_score(net_profit: float, max_dd: float, trades: int, config: ScoringGuardConfig)`
**Formula:** `FinalScore = (Net/(MDD+eps)) * min(Trades, T_MAX)^ALPHA`
**Thresholds:**
- `t_max = 100` (trade count cap)
- `alpha = 0.25` (trade bonus exponent)
- `min_avg_profit = 5.0` (minimum average profit per trade)
- `robust_cliff_threshold = 0.1` (robustness threshold)

### 1.2 Winners.json V2 Schema SSOT
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

### 1.3 Plateau Artifact SSOT
**Location:** `src/research/plateau.py`
**Artifact:** `plateau_report.json`
**Key Field:** `stability_score` (float 0.0-1.0)

## 2. Implementation Integration Points

### 2.1 Artifact Writing Integration
**Location:** `src/core/artifacts.py`
**Function:** `write_run_artifacts()`
**Modification:** Added ranking_explain.json generation after winners.json writing
**Trigger:** When winners exist and have topk items
**Context Determination:** Based on stage_name ("final" or "selection" → FINAL_SELECTION, else CANDIDATE)

### 2.2 Explain Service Integration
**Location:** `src/control/explain_service.py`
**Function:** `get_ranking_explain_report()`
**Behavior:** Reads ranking_explain.json artifact, returns structured report or error message
**Integration:** Called from `build_job_explain()` to include ranking explanations in job explain payload

### 2.3 Artifact Navigator Integration
**Location:** `src/gui/desktop/tabs/report_tab.py`
**Modification:** Added "ranking_explain.json" to artifact checklist
**Location:** `src/gui/desktop/state/active_run_state.py`
**Modification:** Added ranking_explain_report_json diagnostics

## 3. Phase I Constraints Implemented

### 3.1 INFO Severity Only
- `RankingExplainSeverity` enum only has INFO value
- Validator enforces INFO-only for Phase I
- Future phases can add WARN/ERROR

### 3.2 Context-Aware Wording
- **CANDIDATE:** Chinese annotation "候選" (candidate)
- **FINAL_SELECTION:** Chinese annotation "勝出" (final selection)
- Different wording templates for each context

### 3.3 Plateau Artifact Gating
- Only emit `PLATEAU_CONFIRMED` reason if plateau_report.json exists
- Otherwise emit `DATA_MISSING_PLATEAU_ARTIFACT` reason
- Research-oriented actions only (inspect, validate, review)

### 3.4 Research-Oriented Actions
- All actions must start with: "inspect", "validate", "review"
- No governance semantics (no "reject", "block", "require")
- Phase I is observation-only

## 4. Reason Codes Implemented (Phase I)

### 4.1 Score Formula & Thresholds
1. `SCORE_FORMULA` - Explanation of scoring formula
2. `THRESHOLD_TMAX_APPLIED` - Trade count capped at t_max
3. `THRESHOLD_MIN_AVG_PROFIT_APPLIED` - Minimum average profit threshold met

### 4.2 Metric Summary
4. `METRIC_SUMMARY` - Performance metrics summary (net_profit, max_dd, trades)

### 4.3 Plateau Artifact Reasons
5. `PLATEAU_CONFIRMED` - Parameter plateau stability confirmed
6. `DATA_MISSING_PLATEAU_ARTIFACT` - Plateau artifact not available

### 4.4 Future Expansion (Reserved)
7. `CONCENTRATION_FACT` - Reserved for Phase II concentration analysis

## 5. File Changes Summary

### 5.1 New Files
1. `src/contracts/ranking_explain.py` - Pydantic v2 contracts
2. `src/gui/services/ranking_explain_builder.py` - Builder implementation
3. `tests/contracts/test_ranking_explain_contract.py` - Contract tests
4. `tests/gui/services/test_ranking_explain_builder.py` - Builder tests
5. `tests/control/test_ranking_explain_integration.py` - Integration tests

### 5.2 Modified Files
1. `src/core/artifacts.py` - Added ranking_explain.json generation
2. `src/control/explain_service.py` - Added ranking explain retrieval
3. `src/gui/desktop/tabs/report_tab.py` - Added to artifact checklist
4. `src/gui/desktop/state/active_run_state.py` - Added diagnostics

## 6. Test Coverage

### 6.1 Contract Tests (13 tests)
- Enum validation
- Pydantic model validation
- INFO severity enforcement
- Context-aware wording
- Research actions validation
- JSON serialization

### 6.2 Builder Tests (9 tests)
- File loading (winners.json, plateau_report.json)
- Report generation with/without plateau
- Threshold reason generation
- Missing metrics handling
- File writing integration

### 6.3 Integration Tests (11 tests)
- Explain service integration
- Artifact URL generation
- Error handling
- Context determination

## 7. SSOT Compliance Verification

✅ **No UI recompute** - All explanations precomputed in artifacts  
✅ **Deterministic wording** - Templates with Chinese annotations  
✅ **INFO severity only** - Phase I constraint enforced  
✅ **Artifact-gated plateau** - Only if plateau_report.json exists  
✅ **Research actions only** - inspect/validate/review verbs  
✅ **No new root files** - All files in appropriate directories  
✅ **codebase_search-first** - Discovery methodology followed  

## 8. Key Design Decisions

### 8.1 Phase I vs Phase II Separation
- Phase I: INFO-only, observation, research actions
- Phase II: WARN/ERROR, governance, concentration analysis
- Enum structure designed for forward compatibility

### 8.2 Context Determination
- Automatic from stage_name in winners.json
- CANDIDATE: default for non-final stages
- FINAL_SELECTION: when stage_name contains "final" or "selection"

### 8.3 Error Handling
- Graceful degradation when artifacts missing
- Clear error messages in explain payload
- No crash if ranking explain generation fails

### 8.4 Performance Considerations
- Lazy loading of ranking explain artifacts
- No recomputation on UI side
- Cached in explain service for repeated requests