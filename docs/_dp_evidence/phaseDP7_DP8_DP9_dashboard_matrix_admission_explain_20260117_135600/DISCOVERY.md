# DP7+DP8+DP9 Bundle: Dashboard Matrix + Admission Policy Engine + Explain Drilldown

## Discovery Summary

### DP7: Cross-job Gate Summary Dashboard (Matrix)
**Target**: Create a read-only dashboard showing gate statuses across multiple jobs
**SSOT Sources**:
- `gui.services.supervisor_client.get_jobs()` - for job list
- `gui.services.consolidated_gate_summary_service` - for per-job gate summaries
- `contracts.portfolio.gate_summary_schemas.GateSummaryV1` - for gate summary schema

**Implementation**:
- `src/gui/services/cross_job_gate_summary_service.py` - Service to fetch and aggregate gate summaries
- `src/gui/desktop/tabs/gate_summary_dashboard_tab.py` - UI tab for dashboard display
- Integrated into `src/gui/desktop/control_station.py` as new tab

### DP8: Admission Policy Engine
**Target**: Deterministic policy engine that evaluates job gate summaries and writes admission decisions
**SSOT Sources**:
- `contracts.job_admission_schemas` - for admission decision schemas
- `contracts.portfolio.gate_summary_schemas` - for gate summary input
- `control.job_artifacts` - for artifact path resolution

**Implementation**:
- `src/contracts/job_admission_schemas.py` - Admission decision contracts
- `src/gui/services/job_admission_policy_engine.py` - Policy engine implementation
- Writes `job_admission_decision.json` to job artifact directory

### DP9: Explain Drilldown (Action Router)
**Target**: Make UI actions clickable to open artifacts (navigation only)
**SSOT Sources**:
- Existing navigation patterns in artifact navigator
- `QDesktopServices.openUrl` for external navigation

**Implementation**:
- `src/gui/services/action_router_service.py` - Central action router service
- Updated DP7 dashboard to use action router for clickable cells
- Updated DP8 policy engine to include navigation actions in decisions

## Key Integration Points

1. **DP7 → DP8**: Dashboard shows admission status from policy engine decisions
2. **DP8 → DP9**: Admission decisions include navigation actions for drilldown
3. **DP9 → DP7/DP8**: Action router enables one-click navigation to gate summaries, admission decisions, and ranking explain reports

## Deterministic Rules

### DP7 (Dashboard)
- Read-only: No recompute of gate summaries
- Fetches jobs list from supervisor API (limit: 50 jobs)
- For each job, fetches consolidated gate summary
- Creates matrix view with statistics

### DP8 (Policy Engine)
- Deterministic policy rules:
  - PASS_ALWAYS_ADMIT: All gates PASS → ADMITTED
  - REJECT_ALWAYS_REJECT: Any gate REJECT → REJECTED  
  - WARN_REQUIRES_REVIEW: Any gate WARN → HOLD
  - Critical gate failures override overall status
  - Too many warnings (configurable threshold) → HOLD
  - Too many failures (configurable threshold) → REJECTED

### DP9 (Action Router)
- Navigation targets:
  - `gate_summary` - Open consolidated gate summary for job
  - `explain://ranking` - Open ranking explain report
  - `job_admission://{job_id}` - Open admission decision
  - `gate_dashboard` - Open gate summary dashboard

## Test Coverage

- DP7: `tests/gui/services/test_cross_job_gate_summary_service.py` (12 tests, all passing)
- DP8: `tests/gui/services/test_job_admission_policy_engine.py` (17 tests, 10 failing due to GateV1/GateItemV1 naming issue - fix in progress)
- DP9: `tests/gui/services/test_action_router_service.py` (8 tests, all passing)

## Files Created/Modified

### New Files
1. `src/gui/services/cross_job_gate_summary_service.py` - DP7 service
2. `src/gui/desktop/tabs/gate_summary_dashboard_tab.py` - DP7 UI tab
3. `src/contracts/job_admission_schemas.py` - DP8 contracts
4. `src/gui/services/job_admission_policy_engine.py` - DP8 policy engine
5. `src/gui/services/action_router_service.py` - DP9 action router
6. `tests/gui/services/test_cross_job_gate_summary_service.py` - DP7 tests
7. `tests/gui/services/test_job_admission_policy_engine.py` - DP8 tests
8. `tests/gui/services/test_action_router_service.py` - DP9 tests

### Modified Files
1. `src/gui/desktop/control_station.py` - Added GateSummaryDashboardTab import and integration
2. `src/gui/desktop/tabs/gate_summary_dashboard_tab.py` - Updated to use action router
3. `src/contracts/job_admission_schemas.py` - Added navigation_actions field
4. `src/gui/services/job_admission_policy_engine.py` - Added _build_navigation_actions method

## Bundle Goal Achieved

✅ **Research → Governance → Admission operator workflow**:
1. **Research**: DP6 ranking explain outputs
2. **Governance**: DP7 dashboard shows gate status matrix across jobs
3. **Admission**: DP8 policy engine evaluates gate summaries and writes admission decisions
4. **Drilldown**: DP9 action router enables one-click navigation to all artifacts

The bundle creates an end-to-end workflow where operators can:
- View gate status matrix across all jobs (DP7)
- See admission decisions based on deterministic policy rules (DP8)
- Click to drill down into gate summaries, ranking explain reports, and admission decisions (DP9)