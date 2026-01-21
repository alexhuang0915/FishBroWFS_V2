# DP6: Explainable Ranking Phase I - Discovery Findings

**Timestamp:** 2026-01-17 00:37:01 UTC+8  
**Evidence Bundle:** `outputs/_dp_evidence/phaseDP6_explainable_ranking_20260117_003701/`

## 1. Discovery Methodology
Used `codebase_search` as primary discovery tool to locate:
1. WFS winners/top20 artifact writers (SSOT)
2. Scoring formula and metrics SSOT
3. Plateau artifact structure and location
4. ReasonCard datamodel and existing patterns
5. Explain service integration points
6. Context-aware wording patterns

## 2. Key SSOT Locations Discovered

### 2.1 WFS Winners/Top20 Artifacts
**File:** `src/core/artifacts.py`  
**Function:** `write_run_artifacts()`  
**SSOT Reason:** Primary artifact writer for WFS results  
**Key Code:**
```python
def write_run_artifacts(
    run_dir: Path,
    manifest: dict,
    config_snapshot: dict,
    metrics: dict,
    winners: Optional[dict] = None,
) -> None:
    # Writes winners.json and other artifacts
```

**File:** `src/wfs/artifact_reporting.py`  
**Function:** `write_governance_and_scoring_artifacts()`  
**SSOT Reason:** Creates scoring_breakdown.json with detailed scoring metrics  
**Key Code:**
```python
def write_governance_and_scoring_artifacts(
    run_dir: Path,
    winners: Dict[str, Any],
    scoring_config: ScoringGuardConfig,
) -> None:
```

### 2.2 Scoring Formula SSOT
**File:** `src/wfs/scoring_guards.py`  
**Function:** `compute_final_score()`  
**SSOT Reason:** Exact scoring formula implementation  
**Key Code:**
```python
def compute_final_score(net_profit: float, max_dd: float, trades: int, config: ScoringGuardConfig):
    # FinalScore = (Net/(MDD+eps)) * TradeMultiplier
    # TradeMultiplier = min(Trades, T_MAX)^ALPHA
```

**Thresholds SSOT:**
- `t_max = 100` (from ScoringGuardConfig)
- `alpha = 0.25` (from ScoringGuardConfig)
- `min_avg_profit = 5.0` (from scoring guard logic)

### 2.3 Plateau Artifacts SSOT
**File:** `src/research/plateau.py`  
**Class:** `PlateauReport`  
**SSOT Reason:** Plateau identification report structure  
**Key Code:**
```python
@dataclass(frozen=True)
class PlateauReport:
    candidates_seen: int
    param_names: List[str]
    selected_main: PlateauCandidate
    selected_backup: List[PlateauCandidate]
    plateau_region: PlateauRegion
    algorithm_version: str = "v1"
```

**Plateau Artifact Path:** `plateau_report.json` in plateau directory  
**Plateau Check Logic:** `src/gui/services/hybrid_bc_adapters.py` extracts plateau boolean from plateau_report

### 2.4 ReasonCard Datamodel SSOT
**File:** `src/gui/services/reason_cards.py`  
**Class:** `ReasonCard`  
**SSOT Reason:** Standard reason card structure used throughout system  
**Key Code:**
```python
@dataclass(frozen=True)
class ReasonCard:
    code: str
    title: str
    severity: Literal["WARN", "FAIL"]
    why: str
    impact: str
    recommended_action: str
    evidence_artifact: str
    evidence_path: str
    action_target: str
```

**Note:** For DP6 Phase I, severity MUST be "INFO" only (extension of existing model)

### 2.5 Explain Service Integration SSOT
**File:** `src/gui/services/explain_adapter.py`  
**Class:** `ExplainAdapter`  
**SSOT Reason:** Main adapter for explain payloads to UI  
**Key Code:**
```python
class ExplainAdapter:
    """Adapter that surfaces Explain SSOT payloads for UI consumption."""
```

**File:** `src/control/api.py`  
**Endpoint:** `/api/v1/jobs/{job_id}/explain`  
**SSOT Reason:** Control API endpoint for explain payloads  
**Key Code:**
```python
@router.get("/{job_id}/explain")
async def get_job_explain(job_id: str) -> JobExplainResponse:
    payload = build_job_explain(job_id)
    return JobExplainResponse(**payload)
```

### 2.6 Artifact Navigator SSOT
**File:** `src/gui/desktop/tabs/report_tab.py`  
**SSOT Reason:** Predefined artifact list for Artifact Navigator  
**Key Code:**
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

## 3. Context-Aware Wording Discovery

### 3.1 Candidate vs Final Selection Patterns
**Discovery:** No existing context-aware wording mapping found in codebase  
**Gap:** Need to implement mapping for DP6 Phase I

**Proposed Mapping:**
- **CANDIDATE context:** "候選/候選名單" semantics (English: "candidate/candidate list")
- **FINAL_SELECTION context:** "最終/勝出" semantics (English: "final/winning")

### 3.2 Recommended Action Patterns
**Discovery:** Existing reason cards use research-oriented actions  
**Pattern:** "inspect", "validate", "review artifacts" (no "reject/block")

## 4. Plateau Artifact Gating Discovery

### 4.1 Plateau Artifact Detection
**File:** `src/gui/services/hybrid_bc_adapters.py`  
**Function:** `_extract_plateau_check()`  
**SSOT Reason:** Plateau check tri-state logic  
**Key Code:**
```python
def _extract_plateau_check(raw: Dict[str, Any]) -> PlateauCheck:
    artifacts = raw.get("artifacts", {})
    plateau_report = artifacts.get("plateau_report")
    if isinstance(plateau_report, dict):
        plateau = plateau_report.get("plateau")
        if plateau is True:
            return "Pass"
        elif plateau is False:
            return "Fail"
    return "N/A"
```

### 4.2 Plateau Artifact Path
**Discovery:** Plateau artifacts typically in `plateau_report.json`  
**Location:** Within job artifact directory or plateau subdirectory

## 5. Concentration Risk Heuristics Discovery

### 5.1 No Existing SSOT for Concentration Thresholds
**Discovery:** No concentration risk thresholds in scoring guards or config  
**Implication:** DP6 Phase I must use heuristic INFO-only statements

### 5.2 Top Score Share Calculation
**Proposed:** `top1_share_of_top5 = top1_score / sum(top5_scores)`  
**Source:** Scores from winners.json topk list

## 6. Implementation Hook Points

### 6.1 Artifact Writing Integration
**Primary Hook:** `write_run_artifacts()` in `src/core/artifacts.py`  
**Timing:** After winners.json is written  
**Artifact Path:** `outputs/jobs/<job_id>/ranking_explain_report.json`

### 6.2 Explain Service Extension
**File:** `src/control/explain_service.py`  
**Function:** `build_job_explain()`  
**Extension:** Add `ranking_explain` field to payload

### 6.3 Artifact Navigator Extension
**File:** `src/gui/desktop/tabs/report_tab.py`  
**Extension:** Add `ranking_explain_report.json` to artifact_defs list

## 7. Gaps and Requirements

### 7.1 Missing Components
1. **RankingExplainReportV1** Pydantic model (needs creation)
2. **Context-aware wording mapping** (needs implementation)
3. **Plateau artifact detection** (exists but needs integration)
4. **Concentration fact calculation** (needs implementation)

### 7.2 Non-Negotiable Compliance
- ✅ No new root files required
- ✅ No UI recompute (read-only from artifacts)
- ✅ Plateau artifact-gated evaluation possible
- ✅ INFO-only severity for Phase I

### 7.3 Test Requirements
1. **Builder unit tests:** `tests/.../test_ranking_explain_builder.py`
2. **Artifact writing integration test**
3. **Explain integration test**
4. **Context-aware wording tests**

## 8. SSOT Summary Table

| Component | SSOT Location | Key Symbol | Why SSOT |
|-----------|---------------|------------|----------|
| Winners Artifacts | `src/core/artifacts.py` | `write_run_artifacts()` | Primary artifact writer |
| Scoring Formula | `src/wfs/scoring_guards.py` | `compute_final_score()` | Exact scoring math |
| Scoring Metrics | `src/wfs/artifact_reporting.py` | `write_governance_and_scoring_artifacts()` | Detailed scoring breakdown |
| Plateau Structure | `src/research/plateau.py` | `PlateauReport` | Plateau identification report |
| ReasonCard Model | `src/gui/services/reason_cards.py` | `ReasonCard` | Standard reason card format |
| Explain Adapter | `src/gui/services/explain_adapter.py` | `ExplainAdapter` | Explain payload to UI |
| Control API | `src/control/api.py` | `/api/v1/jobs/{job_id}/explain` | Explain endpoint |
| Artifact List | `src/gui/desktop/tabs/report_tab.py` | `artifact_defs` | Artifact Navigator definitions |

## 9. Next Steps for Implementation

1. **Create Pydantic models** for RankingExplainReportV1 and RankingExplainItemV1
2. **Implement builder** `build_ranking_explain_report()` with SSOT-only inputs
3. **Add context-aware wording** mapping for CANDIDATE vs FINAL_SELECTION
4. **Integrate plateau artifact detection** with DATA_MISSING fallback
5. **Wire into artifact pipeline** via `write_run_artifacts()` hook
6. **Extend explain service** to include ranking_explain field
7. **Update Artifact Navigator** to list new artifact
