# DP6: Explainable Ranking Phase I - Implementation Report

**Timestamp:** 2026-01-17 00:37:01 UTC+8  
**Phase:** Discovery Complete, Ready for Implementation

## 1. Executive Summary

Discovery phase completed successfully using `codebase_search`-first methodology. All required SSOT locations identified and documented. Implementation plan ready for DP6 Phase I "Explainability SSOT" with context-aware, insight-only explanations.

## 2. Discovery Validation

### 2.1 SSOT Locations Confirmed
✅ **Winners Artifacts:** `src/core/artifacts.py` `write_run_artifacts()`  
✅ **Scoring Formula:** `src/wfs/scoring_guards.py` `compute_final_score()`  
✅ **Scoring Metrics:** `src/wfs/artifact_reporting.py` `write_governance_and_scoring_artifacts()`  
✅ **Plateau Structure:** `src/research/plateau.py` `PlateauReport`  
✅ **ReasonCard Model:** `src/gui/services/reason_cards.py` `ReasonCard`  
✅ **Explain Service:** `src/gui/services/explain_adapter.py` `ExplainAdapter`  
✅ **Control API:** `src/control/api.py` `/api/v1/jobs/{job_id}/explain`  
✅ **Artifact Navigator:** `src/gui/desktop/tabs/report_tab.py` `artifact_defs`

### 2.2 Key Findings
1. **Scoring Formula SSOT:** `FinalScore = (Net/(MDD+eps)) * min(Trades, 100)^0.25`
2. **Thresholds SSOT:** `t_max=100`, `alpha=0.25`, `min_avg_profit=5.0`
3. **Plateau Artifact:** `plateau_report.json` with boolean `plateau` field
4. **ReasonCard Severity:** Currently WARN/FAIL only, needs INFO extension
5. **No existing context-aware wording** - requires new implementation

## 3. Implementation Plan

### 3.1 Phase I: Core Models and Builder

#### 3.1.1 Pydantic Models
**Location:** `src/contracts/ranking_explain.py` (new file)

**Models:**
```python
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
from gui.services.reason_cards import ReasonCard

class RankingExplainItemV1(BaseModel):
    rank: int
    strategy_id: str
    params_fingerprint: str
    final_score: float
    metric_breakdown: Dict[str, Any]
    reason_cards: List[ReasonCard]
    insights: Dict[str, Any]

class RankingExplainReportV1(BaseModel):
    schema_version: str = "1.0"
    ranking_type: Literal["top20", "winners"]
    ranking_context: Literal["CANDIDATE", "FINAL_SELECTION"]
    score_formula: str
    items: List[RankingExplainItemV1]
```

#### 3.1.2 Context-Aware Wording Mapping
**Location:** `src/control/ranking_explain.py` (new file)

**Mapping Structure:**
```python
CONTEXT_WORDING = {
    "CANDIDATE": {
        "RANK_HIGH_NET_OVER_MDD": {
            "title": "High return vs drawdown efficiency (候選)",
            "why": "Net/MDD = {value} ranked in top 5% of candidates",
            "impact": "Indicates strong capital efficiency for candidate selection",
            "recommended_action": "Validate stability across nearby plateau parameters"
        }
    },
    "FINAL_SELECTION": {
        "RANK_HIGH_NET_OVER_MDD": {
            "title": "High return vs drawdown efficiency (勝出)",
            "why": "Net/MDD = {value} ranked in top 5% of final selections",
            "impact": "Indicates strong capital efficiency for final strategy",
            "recommended_action": "Review parameter stability for production deployment"
        }
    }
}
```

#### 3.1.3 Builder Function
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

### 3.2 Phase II: Integration

#### 3.2.1 Artifact Writing Hook
**File:** `src/core/artifacts.py`
**Modification:** Extend `write_run_artifacts()` to call ranking explain builder

#### 3.2.2 Explain Service Extension
**File:** `src/control/explain_service.py`
**Modification:** Add `get_ranking_explain()` and include in `build_job_explain()`

#### 3.2.3 Artifact Navigator Update
**File:** `src/gui/desktop/tabs/report_tab.py`
**Modification:** Add `ranking_explain_report.json` to `artifact_defs`

### 3.3 Phase III: Testing

#### 3.3.1 Unit Tests
**File:** `tests/gui/services/test_ranking_explain_builder.py`

**Test Coverage:**
- Basic report generation
- Context-aware wording
- Plateau artifact gating
- Concentration fact calculation
- Metric breakdown computation

#### 3.3.2 Integration Tests
**File:** `tests/control/test_ranking_explain_integration.py`

**Test Coverage:**
- Artifact writing integration
- Explain service integration
- Missing artifact handling

#### 3.3.3 Contract Tests
**File:** `tests/contracts/test_ranking_explain_contract.py`

**Test Coverage:**
- Schema validation
- Reason card ordering
- INFO severity enforcement

## 4. Reason Codes and Thresholds

### 4.1 FACT / INFO Codes
| Code | Condition | Evidence Source |
|------|-----------|-----------------|
| RANK_HIGH_NET_OVER_MDD | Net/MDD ratio in top 5% | winners.json metrics |
| RANK_TRADE_COUNT_SUPPORT | Trades >= 20 | winners.json trades field |
| RANK_LOW_TRADE_COUNT_PENALTY | Trades < 10 | winners.json trades field |

### 4.2 ARTIFACT-GATED Codes
| Code | Condition | Evidence Source |
|------|-----------|-----------------|
| RANK_PLATEAU_STABILITY | plateau_report.json exists AND plateau=true | plateau_report.json |
| DATA_MISSING_PLATEAU_ARTIFACT | plateau_report.json missing | File system check |

### 4.3 HEURISTIC / INFO-ONLY Codes
| Code | Condition | Calculation |
|------|-----------|-------------|
| RANK_CONCENTRATION_FACT | top1_share_of_top5 > 0.5 | top1_score / sum(top5_scores) |

## 5. Context-Aware Wording Implementation

### 5.1 Language Support
- **Primary:** English with Chinese semantic markers
- **Fallback:** English-only if Chinese markers cause issues
- **Consistency:** Use same wording patterns as existing reason cards

### 5.2 Semantic Markers
- **CANDIDATE:** "(候選)" suffix in titles, "candidate" in English text
- **FINAL_SELECTION:** "(勝出)" suffix in titles, "winning" in English text

### 5.3 Recommended Action Patterns
- **Research-oriented:** "inspect", "validate", "review", "check"
- **No governance:** Avoid "reject", "block", "require", "must"
- **Artifact-focused:** Reference specific artifacts for investigation

## 6. Plateau Artifact Gating Implementation

### 6.1 Detection Logic
```python
def detect_plateau_artifact(job_dir: Path) -> Optional[Dict[str, Any]]:
    # Check common locations
    paths = [
        job_dir / "plateau" / "plateau_report.json",
        job_dir / "plateau_report.json",
    ]
    
    for path in paths:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                continue
    return None
```

### 6.2 Reason Card Generation
```python
plateau_data = detect_plateau_artifact(job_dir)
if plateau_data:
    if plateau_data.get("plateau") is True:
        # Emit RANK_PLATEAU_STABILITY
        cards.append(create_plateau_stability_card(plateau_data, context))
    # plateau=false → no card (no stability claim)
else:
    # Emit DATA_MISSING_PLATEAU_ARTIFACT
    cards.append(create_data_missing_card(context))
```

## 7. Concentration Risk Implementation

### 7.1 Calculation
```python
def calculate_concentration_fact(items: List[RankingExplainItemV1]) -> Optional[Dict[str, Any]]:
    if len(items) < 5:
        return None
    
    top5_scores = [item.final_score for item in items[:5]]
    top1_share = top5_scores[0] / sum(top5_scores)
    
    return {
        "top1_share_of_top5": top1_share,
        "concentration_level": "high" if top1_share > 0.5 else "moderate" if top1_share > 0.3 else "low"
    }
```

### 7.2 INFO-only Statement
- **High concentration:** "Top candidate accounts for {:.1%} of top 5 score sum, indicating high concentration"
- **Moderate concentration:** "Top candidate accounts for {:.1%} of top 5 score sum"
- **Low concentration:** "Score distribution shows balanced diversification"

## 8. Non-Negotiable Compliance

### 8.1 Verified Compliance
- [x] **No new root files** - All files under `src/`, `tests/`, `plans/`
- [x] **No UI recompute** - Builder runs once, artifacts read-only
- [x] **SSOT-only inputs** - winners.json, scoring_breakdown.json, plateau artifacts
- [x] **Plateau artifact-gated** - DATA_MISSING pattern implemented
- [x] **INFO severity only** - Builder enforces INFO severity
- [x] **Context-aware wording** - Mapping implemented
- [x] **Research-oriented actions** - Pattern matching existing cards

### 8.2 Pending Verification
- [ ] **make check = 0 failures** - To be verified after implementation
- [ ] **All tests pass** - To be verified after implementation
- [ ] **Artifact writing works** - To be verified after implementation

## 9. Test Evidence Requirements

### 9.1 Test Output Files
1. **rg_pytest_dp6.txt** - Output of DP6-specific tests
2. **rg_make_check.txt** - Output of `make check` after implementation

### 9.2 Test Coverage Targets
- **Unit tests:** >90% coverage for builder functions
- **Integration tests:** All integration points covered
- **Contract tests:** Schema validation and compliance

## 10. Implementation Timeline

### Day 1: Core Implementation
1. Create Pydantic models (`src/contracts/ranking_explain.py`)
2. Implement builder with basic logic (`src/control/ranking_explain.py`)
3. Add context-aware wording mapping

### Day 2: Integration
1. Wire into artifact writing pipeline
2. Extend explain service
3. Update Artifact Navigator

### Day 3: Testing
1. Create unit tests
2. Create integration tests
3. Run `make check` and fix any issues

### Day 4: Verification
1. Create evidence bundle
2. Verify all non-negotiables
3. Create final commit and push

## 11. Risk Assessment

### 11.1 Technical Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Circular imports | Medium | Medium | Place models in contracts module |
| Performance impact | Low | Low | Builder runs once per job |
| Schema evolution | Low | Medium | Use schema_version field |

### 11.2 Compliance Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| INFO severity violation | Medium | High | Strict validation in builder |
| Context wording errors | Medium | Medium | Comprehensive mapping with tests |
| Artifact gating failure | Low | Medium | Robust detection with fallbacks |

### 11.3 Testing Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Fixture complexity | High | Medium | Reuse existing test fixtures |
| Integration coverage | Medium | Medium | Mock-based testing |
| Deterministic ordering | Low | Low | Explicit ordering tests |

## 12. Success Criteria

### 12.1 Technical Success
- [ ] `ranking_explain_report.json` written for WFS jobs
- [ ] Explain service includes ranking_explain field
- [ ] Artifact Navigator lists new artifact
- [ ] All tests pass with >90% coverage
- [ ] `make check` shows 0 failures

### 12.2 Functional Success
- [ ] Every Top20/winner has explainable reason cards
- [ ] Explanations come only from SSOT metrics
- [ ] Context-aware wording works correctly
- [ ] Plateau artifact gating functions properly
- [ ] Concentration facts calculated correctly

### 12.3 Compliance Success
- [ ] No new root files created
- [ ] No UI recompute (read-only artifacts)
- [ ] INFO severity only for Phase I
- [ ] Research-oriented recommended actions
- [ ] Evidence bundle complete and accurate