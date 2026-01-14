# Gate Summary v1 Contract Notes

## Current State Analysis

### 1. Existing Gate Summary Models

**A. `GateSummaryV1` in `src/core/portfolio/evidence_aggregator.py`**
- Purpose: Gatekeeper results from strategy reports
- Fields:
  - `total_permutations: Optional[int]` - count of total permutations evaluated
  - `valid_candidates: Optional[int]` - count of valid candidates passing gates
  - `plateau_check: Optional[str]` - plateau check status ("Pass", "Fail", "N/A")
- Used by: EvidenceAggregator for building job evidence index
- SSOT: Read from `strategy_report_v1.json` → `gatekeeper` section

**B. `GateSummary` in `src/gui/services/gate_summary_service.py`**
- Purpose: System health gates for UI observability
- Fields:
  - `gates: List[GateResult]` - individual gate results
  - `timestamp: str` - when summary was fetched
  - `overall_status: GateStatus` - aggregated status (PASS/WARN/FAIL)
  - `overall_message: str` - human-readable summary
- Used by: UI widgets (`GateSummaryWidget`, `AnalysisDrawerWidget`)
- SSOT: Fetched from supervisor API endpoints (health, readiness, jobs, registry)

**C. `GateResult` in same file**
- Fields:
  - `gate_id: str` - unique identifier
  - `gate_name: str` - human-readable name
  - `status: GateStatus` - PASS/WARN/FAIL
  - `message: str` - explanation
  - `details: Optional[Dict]` - additional data
  - `actions: Optional[List]` - UI actions
  - `timestamp: Optional[str]` - when gate was checked

### 2. SSOT (Single Source of Truth)

**For system health gates:** Supervisor API endpoints
- `/health` - API health
- `/api/v1/readiness` - API readiness  
- `/api/v1/jobs` - Supervisor DB SSOT
- Worker execution reality (derived from jobs)
- `/api/v1/registry/timeframes` - Registry surface

**For gatekeeper gates:** Job artifacts
- `outputs/jobs/{job_id}/strategy_report_v1.json` → `gatekeeper` section
- Read by `EvidenceAggregator.extract_gate_summary()`

### 3. Hybrid BC v1.1 Compliance Analysis

**Current compliance:**
- `GateSummaryV1` (evidence aggregator): Contains counts (`total_permutations`, `valid_candidates`) but these are **not performance metrics**. They are gate evaluation counts.
- `GateSummary` (service): Contains `details` field which may include counts (`running_count`, `queued_count`, `jobs_count`) but these are system observability metrics, not portfolio performance metrics.

**Metric keywords to exclude (per Hybrid BC v1.1 Layer1/Layer2):**
- net, pnl, profit, return, sharpe, sortino, calmar, mdd, drawdown, cagr, winrate, expectancy, alpha, beta, vol, volatility

**Current models DO NOT contain these metric keywords.**

### 4. Required Gate Summary v1 Contract

Based on task requirements, we need a consolidated GateSummaryV1 model that:

**Required fields:**
- `schema_version: str` (e.g., "v1")
- `overall_status: GateStatus` (enum: PASS/WARN/FAIL/SKIP)
- `counts: Dict[str, int]` with pass/warn/reject/skip counts
- `gates: List[GateItemV1]` where each gate has:
  - `gate_id: str` (stable identifier)
  - `status: GateStatus`
  - `title: str`
  - `reason_codes: List[str]` (optional)
  - `message: str`
  - `evidence_refs: List[str]` (artifact paths/manifest refs)

**Prohibited fields:**
- Any field with metric keywords (net, sharpe, mdd, etc.)
- Performance metrics of any kind

### 5. Implementation Strategy

**Option 1: Extend existing `GateSummary` (service model)**
- Add `schema_version`, `counts`, `evidence_refs`
- Ensure no metric fields
- Keep backward compatibility

**Option 2: Create new `GateSummaryV1` in contracts package**
- Place in existing contracts schema package discovered
- Ensure Pydantic v2 compliance
- Map from both existing models

**Recommendation:** Option 2 - Create new canonical model in `src/contracts/portfolio/gate_summary_schemas.py` (or similar location) that can be used by both UI and evidence aggregator.

### 6. Next Steps

1. Create new GateSummaryV1 model in appropriate contracts location
2. Update evidence aggregator to produce this model (or map from existing)
3. Update gate summary service to produce this model (or map from existing)
4. Add policy tests to prevent metric leakage
5. Update UI widgets to use new model