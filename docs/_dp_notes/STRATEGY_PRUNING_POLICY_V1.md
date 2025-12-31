# Strategy Pruning Policy V1

## Executive Summary

Based on automated strategy usage analysis conducted on 2025-12-30, **6 out of 6 registered strategies** have been marked for potential removal (KILL status). This document outlines the pruning policy, evidence-based recommendations, and safe removal procedures to maintain system health while reducing technical debt.

## Analysis Results

### Governance Decisions (2025-12-30)
| Strategy ID | Status | Reason | Evidence |
|-------------|--------|--------|----------|
| S1 | KILL | Failing tests | test_status: failing |
| S2 | KILL | Failing tests | test_status: failing |
| S3 | KILL | Failing tests | test_status: failing |
| breakout_channel | KILL | Failing tests | test_status: failing |
| mean_revert_zscore | KILL | Failing tests | test_status: failing |
| sma_cross | KILL | Failing tests | test_status: failing |

### Key Findings
1. **All strategies marked KILL**: The governance system identified all 6 registered strategies as candidates for removal
2. **Primary reason**: "Failing tests" according to automated test analysis
3. **Usage patterns**: No recent research usage detected for any strategy
4. **Configuration status**: Mixed configuration presence (some have configs, others don't)
5. **Documentation status**: Limited documentation coverage

## Pruning Criteria

### Safe Removal Criteria (Must meet ALL)
1. **No active research dependencies**: Strategy not referenced in recent research logs (>90 days)
2. **No production dependencies**: Not referenced in production deployment manifests
3. **No active configuration files**: No baseline.yaml or features.json in configs/strategies/{id}/
4. **Failing or missing tests**: Test suite either fails or doesn't exist
5. **No documentation**: No strategy-specific documentation in docs/strategies/

### High-Risk Indicators (Require manual review)
1. **Referenced in other strategies**: Cross-strategy dependencies
2. **Used in portfolio specifications**: Referenced in configs/portfolio/
3. **Has recent research artifacts**: Outputs in outputs/research/{strategy_id}/
4. **Active feature requirements**: Required features still in registry

## Evidence Verification

### Test Status Analysis
The automated analysis uses simplified test detection that may produce false positives. Manual verification required:

1. **S1 Strategy**: Has passing tests (`test_strategy_registry_contains_s1.py`)
2. **S2/S3 Strategies**: Have comprehensive test suites in `tests/strategy/`
3. **Legacy strategies**: `breakout_channel`, `mean_revert_zscore`, `sma_cross` may have limited test coverage

### Research Usage Analysis
Research logs directory (`outputs/research/`) was analyzed for strategy references. No recent usage found, but this could be due to:
- Analysis timeframe limitations
- Different log formats
- Missing research data

### Configuration Analysis
Configuration files checked in `configs/strategies/{id}/`:
- S1: Has `baseline.yaml` and `features.json`
- S2: Has `baseline.yaml`
- S3: Has `baseline.yaml`
- Legacy strategies: Limited or no configuration

## Pruning Implementation Plan

### Phase 1: Verification (Safe Mode)
1. **Manual test verification**: Run strategy-specific tests to confirm actual status
2. **Dependency analysis**: Check for cross-references in codebase
3. **Research artifact audit**: Verify no valuable research outputs exist
4. **Configuration backup**: Archive existing configuration files

### Phase 2: Gradual Removal (Risk-Mitigated)
1. **Mark as deprecated**: Add `@deprecated` decorator to strategy functions
2. **Update registry**: Add deprecation flags to strategy registry entries
3. **Notify consumers**: Update documentation with deprecation notices
4. **Monitor usage**: Track any attempts to use deprecated strategies

### Phase 3: Actual Removal (After Validation Period)
1. **Code removal**: Delete strategy implementation files
2. **Registry cleanup**: Remove from strategy registry
3. **Configuration removal**: Archive or delete configuration files
4. **Test cleanup**: Remove or update strategy-specific tests
5. **Documentation update**: Mark strategies as removed in docs

## Risk Assessment

### High Risk
- **S1 Strategy**: Core strategy with existing tests and configuration
- **S2/S3 Strategies**: Recently developed with comprehensive test suites

### Medium Risk
- **Legacy strategies**: Limited usage but may have historical research value

### Low Risk
- Strategies with no configuration, no tests, and no recent usage

## Mitigation Strategies

### Rollback Procedures
1. **Git-based rollback**: All changes committed with descriptive messages
2. **Configuration backup**: Archived configurations in `configs/strategies/_archive/`
3. **Code snapshot**: Tag repository before major removals
4. **Test preservation**: Keep test files for reference even if strategies removed

### Validation Steps
1. **Pytest lockdown**: All tests must pass after each removal
2. **Import validation**: Verify no import errors in dependent modules
3. **Registry consistency**: Strategy registry must remain functional
4. **Research runner**: Ensure research pipeline still works

## Implementation Timeline

### Week 1: Verification & Planning
- Complete manual test verification
- Document all dependencies
- Create backup of all configurations
- Update this policy with verified findings

### Week 2: Deprecation Phase
- Mark strategies as deprecated in code
- Update registry with deprecation flags
- Notify team via documentation
- Monitor for any usage

### Week 3: Removal (Conditional)
- Remove low-risk strategies first
- Validate system stability
- Proceed with medium/high risk if no issues

### Week 4: Finalization & Documentation
- Complete removal of all KILL strategies
- Update all documentation
- Archive evidence and decisions
- Generate final report

## Evidence Files

The following evidence files support this policy:

1. **Governance decisions**: `outputs/_dp_evidence/20251230_1727_phase_next/strategy_pruning_analysis/governance_decisions_20251230_181424.json`
2. **Governance report**: `outputs/_dp_evidence/20251230_1727_phase_next/strategy_pruning_analysis/governance_report_20251230_181424.json`
3. **Analysis script**: `scripts/_dev/analyze_strategy_usage.py`
4. **Governance implementation**: `src/control/strategy_rotation.py`

## Recommendations

### Immediate Actions (High Priority)
1. **Verify test status manually**: The automated analysis may have false positives
2. **Check research usage more thoroughly**: Expand analysis timeframe
3. **Review S1/S2/S3 strategy importance**: These may be core strategies despite analysis results

### Medium-Term Actions
1. **Improve test detection logic**: Enhance `StrategyGovernance._analyze_test_results()`
2. **Add usage tracking**: Implement better research usage logging
3. **Create strategy lifecycle documentation**: Document promotion/demotion criteria

### Long-Term Actions
1. **Implement automated pruning**: Safe, automated removal of truly unused strategies
2. **Create strategy retirement ceremony**: Formal process for strategy removal
3. **Establish strategy library**: Archive removed strategies for historical reference

## Approval & Sign-off

This policy requires approval from:
- [ ] Technical Lead
- [ ] Research Team Lead  
- [ ] System Architect
- [ ] Quality Assurance Lead

**Approval Date**: ____________________

**Next Review Date**: 2026-03-30 (90 days from creation)

---

*Document generated by automated strategy governance system on 2025-12-30*  
*Analysis timestamp: 2025-12-30T18:14:24.103804+00:00*  
*Policy version: V1*