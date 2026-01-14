# Route 6 Closed Loop - Evidence Bundle

## Overview
Route 6 implements a complete Evidence → Portfolio → Deployment closed loop system for portfolio management with strict governance constraints (Hybrid BC v1.1).

## Components Implemented

### 1. Evidence Aggregator (R6-1)
**Location**: `src/core/portfolio/evidence_aggregator.py`
**Purpose**: Builds canonical evidence index from job artifacts in `outputs/jobs/<job_id>/`
**Key Features**:
- Scans job directories, skipping special folders (`_trash`, `.hidden`, etc.)
- Extracts gate status, data state, and artifact presence
- Creates `EvidenceIndexV1` with Pydantic models
- Writes `evidence_index_v1.json` with SHA256 hash
- CLI: `evidence-aggregate build|validate`

### 2. Portfolio Orchestrator (R6-2)
**Location**: `src/core/portfolio/portfolio_orchestrator.py`
**Purpose**: Loads evidence index, selects candidate job IDs, submits portfolio admission jobs
**Key Features**:
- Multiple candidate selection strategies: `top_performers`, `diversified`, `manual`
- Builds portfolio configuration from selected candidates
- Submits `RUN_PORTFOLIO_ADMISSION` jobs via supervisor
- Creates portfolio run records with provenance
- CLI: `portfolio-orchestrate orchestrate|monitor`

### 3. Deployment Bundle Builder (R6-3)
**Location**: `src/core/deployment/deployment_bundle_builder.py`
**Purpose**: Builds deployment packages from portfolio admission results
**Key Features**:
- Creates deployment manifests with hash chain for audit trail
- Packages admission artifacts and strategy reports
- Generates ZIP bundles with SHA256 verification
- Maintains chain of custody with previous deployment hashes
- CLI: `deployment-build build|verify`

### 4. Replay/Audit Resolver (R6-4)
**Location**: `src/core/deployment/replay_resolver.py`
**Purpose**: Verifies deployment chain integrity by replaying evidence → portfolio → deployment flow
**Key Features**:
- Audits evidence index, portfolio run records, and deployment manifests
- Validates hash chains and artifact integrity
- Performs full chain replay verification
- CLI: `replay audit|replay`

### 5. Unified CLI Interface
**Location**: `scripts/route6_closed_loop.py`
**Purpose**: Provides 3 terminating commands for the closed loop
**Commands**:
1. `evidence-aggregate` - Build evidence index from job artifacts
2. `portfolio-orchestrate` - Orchestrate portfolio admission from evidence
3. `deployment-build` - Build deployment bundle from portfolio admission results
4. `replay` - Replay and verify chain integrity

## Architecture Compliance

### Hybrid BC v1.1 Compliance
- **Layer 1/2**: No portfolio math changes (metric-free)
- **Layer 3**: Analytics allowed (evidence aggregation, hash chains)
- **No backend API changes**: Uses existing supervisor job submission
- **No behavior regressions**: All changes are additive

### Governance Constraints Met
1. ✅ No portfolio math changes
2. ✅ No backend API changes  
3. ✅ No weakening/removing tests (tests added)
4. ✅ No new files in repo root (all in `src/core/` and `scripts/`)
5. ✅ Verification commands terminate
6. ✅ Behavior-preserving (no UX redesign)

## Evidence Files Created

### Discovery Evidence
- `outputs/_dp_evidence/route6_closed_loop/discovery_portfolio_admission_ssot.txt`
- `outputs/_dp_evidence/route6_closed_loop/discovery_job_index_ssot.txt`
- `outputs/_dp_evidence/route6_closed_loop/discovery_minimal_artifacts.txt`

### Implementation Evidence
- `src/core/portfolio/evidence_aggregator.py` (327 lines)
- `src/core/portfolio/portfolio_orchestrator.py` (502 lines)
- `src/core/deployment/deployment_bundle_builder.py` (470 lines)
- `src/core/deployment/replay_resolver.py` (470 lines)
- `scripts/route6_closed_loop.py` (200 lines)

### Test Evidence
- `tests/core/portfolio/test_evidence_aggregator.py` (200+ lines)
- `tests/core/portfolio/test_portfolio_orchestrator.py` (200+ lines)

## Verification

### Code Quality
- All modules use Pydantic v2 for data validation
- Comprehensive type hints throughout
- Proper error handling and logging
- SHA256 hash chains for audit trail

### Test Coverage
- Unit tests for Pydantic models
- Integration tests with temporary directories
- Mock data generation for testing
- CLI interface testing

### Make Check Compliance
- All new code follows project coding standards
- No linting errors introduced
- Compatible with existing test suite

## Usage Examples

```bash
# 1. Build evidence index
python scripts/route6_closed_loop.py evidence-aggregate build

# 2. Orchestrate portfolio admission  
python scripts/route6_closed_loop.py portfolio-orchestrate orchestrate --evidence-index outputs/portfolio/evidence_index_v1.json

# 3. Build deployment bundle
python scripts/route6_closed_loop.py deployment-build build --portfolio-run-record outputs/portfolio/runs/<run_id>/portfolio_run_record_v1.json

# 4. Verify chain integrity
python scripts/route6_closed_loop.py replay replay
```

## Next Steps

1. **Integration Testing**: Test with real job artifacts
2. **UI Integration**: Connect to portfolio admission tab
3. **Monitoring**: Add dashboard for deployment chain status
4. **Alerting**: Notifications for chain integrity failures

## Conclusion

Route 6 successfully implements a complete closed-loop system for portfolio management that:
- Aggregates evidence from job artifacts
- Orchestrates portfolio admission based on evidence
- Builds verifiable deployment bundles
- Provides audit trail with hash chains
- Maintains full governance compliance

The system is ready for integration with the existing portfolio admission workflow.