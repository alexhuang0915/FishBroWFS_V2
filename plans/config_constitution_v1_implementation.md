# Config Constitution v1 - Implementation Plan

## Executive Summary

Based on the forensic audit (Config Surface Audit v2), we need to implement a strict YAML-based configuration constitution across the entire codebase. This plan addresses all 7 implementation tasks with clear deliverables, dependencies, and verification steps.

## Current State Analysis (From Audit v2)

### Key Findings:
1. **28 distinct configuration points** across the system
2. **Mixed sources**: JSON, YAML, hardcoded constants, environment variables, `.get()` defaults
3. **Critical inconsistencies**: Timeframes hardcoded in 4+ places, memory limits vary, random seeds inconsistent
4. **Hidden configuration**: Environment variables as feature flags, implicit defaults

### Current Configs Directory Structure:
```
configs/
├── dimensions_registry.json          # Registry data (JSON)
├── funnel_min.json                   # Strategy/test config (JSON)
├── portfolio/
│   ├── governance_params.json        # Portfolio config (JSON)
│   ├── instruments.yaml              # Profile data (YAML - good)
│   ├── portfolio_policy_v1.json      # Legacy
│   ├── portfolio_spec_v1.yaml        # Legacy
│   └── portfolio_spec_with_policy_v1.json  # Legacy
└── profiles/
    ├── CME_MNQ_EXCHANGE_v1.yaml      # Profile (YAML - good)
    ├── CME_MNQ_TPE_v1.yaml           # Profile (YAML - good)
    ├── CME_MNQ_v2.yaml               # Profile (YAML - good)
    ├── TWF_MXF_TPE_v1.yaml           # Profile (YAML - good)
    └── TWF_MXF_v2.yaml               # Profile (YAML - good)
```

## Target Architecture (Constitution v1)

### A) CONFIGS Directory Structure (YAML-only)
```
configs/
├── registry/                         # UI menus & selectable definitions
│   ├── timeframes.yaml              # Allowed timeframes
│   ├── instruments.yaml             # Instrument definitions
│   ├── datasets.yaml                # Dataset definitions
│   └── strategy_catalog.yaml        # Strategy catalog
├── profiles/                        # Instrument specs & cost models
│   ├── CME_MNQ.yaml                # Profile with mandatory cost_model
│   ├── TWF_MXF.yaml                # Profile with mandatory cost_model
│   └── _template.yaml              # Profile template
├── strategies/                      # Strategy parameters & features
│   ├── s1_v1.yaml                  # Strategy definition
│   ├── s2_v1.yaml                  # Strategy definition
│   └── s3_v1.yaml                  # Strategy definition
└── portfolio/                      # Governance & admission rules
    ├── governance.yaml             # Governance thresholds
    └── allocation.yaml             # Risk allocation rules
```

### B) OUTPUTS Directory Structure (Strict buckets)
```
outputs/
├── jobs/                           # Job artifacts (existing)
├── seasons/                        # Season aggregates (existing)
├── deployments/                    # Deployment artifacts
├── _artifacts/                     # Generated config artifacts
├── _dp_evidence/                   # Diagnostic evidence (existing)
├── _scratch/                       # Temporary files
└── (nothing else at root)
```

## Implementation Tasks Breakdown

### Task 1: Discovery & Evidence Collection
**Objective**: Capture current state before changes
**Deliverables**:
1. `outputs/_dp_evidence/op_config_cleanup_discovery.txt` with:
   - Tree of configs/ and outputs/
   - rg evidence for hardcoded timeframes, mock data, commission defaults, random seeds, env vars
   - Current import violations

**Steps**:
1. Use `find` and `rg` commands to capture current state
2. Document all hardcoded configuration points from audit
3. Identify all mock/fake data providers in UI

### Task 2: Implement Canonical Config Loaders + Strict Validation
**Objective**: Create unified YAML loaders with validation

**Sub-tasks**:
1. **Registry Loaders**:
   - Create `src/config/registry/` module with Pydantic models
   - Implement `load_timeframes()`, `load_instruments()`, `load_datasets()`, `load_strategy_catalog()`
   - Validation: Ensure YAML schema compliance

2. **Profile Loader with Mandatory Cost Model**:
   - Extend `src/portfolio/instruments.py` or create new `src/config/profiles.py`
   - Add validation: `commission_per_side_usd` and `slippage_per_side_usd` required
   - Default to 0.0 only if explicitly set in YAML

3. **Strategy Loader with Seed Precedence**:
   - Create `src/config/strategies.py`
   - Schema: `default_seed` at strategy level
   - Seed precedence: `job.seed > strategy.default_seed`
   - Block env-based seed overrides

4. **Portfolio Loader**:
   - Migrate `governance_params.json` to YAML
   - Update `src/portfolio/governance/params.py` to load YAML

### Task 3: Migrate/Remove Legacy Config Sources
**Objective**: Move all 28 config points to target taxonomy

**Migration Map** (from audit):
1. **Registry → configs/registry/**:
   - Timeframe list: Create `timeframes.yaml`
   - Instrument list: Enhance existing `instruments.yaml`
   - Dataset list: Create `datasets.yaml` from `dimensions_registry.json`
   - Strategy list: Create `strategy_catalog.yaml`

2. **Profile → configs/profiles/**:
   - Commission/slippage: Add to profile YAMLs
   - Instrument specs: Already in `instruments.yaml`
   - Session/calendar: Add to profiles
   - Memory limits: Add to profiles

3. **Strategy → configs/strategies/**:
   - Parameter grids: Migrate from `funnel_min.json`
   - Subsample rates: Strategy-level configuration
   - Feature flags: Strategy YAML (not env vars)

4. **Portfolio → configs/portfolio/**:
   - Governance thresholds: Migrate JSON to YAML
   - Correlation policy: Migrate to YAML

5. **Code Constants**: Keep as-is (document)
6. **Environment Variables**: Audit and restrict to system-level only

### Task 4: UI Reality Enforcement
**Objective**: Remove mock data, use real configs

**Sub-tasks**:
1. **Identify Mock Data Sources**:
   - `src/gui/desktop/tabs/portfolio_admission_tab.py:238` - `random.choice()` for gate status
   - Other UI mock generators

2. **Update UI Data Providers**:
   - Create `src/ui/data_providers.py` that loads from registry YAML
   - Replace hardcoded timeframe lists with registry data
   - Replace instrument dropdowns with registry data

3. **Error State Handling**:
   - Update UI to show explicit errors when configs missing
   - Remove fallback to mock data

### Task 5: Repo Hygiene for Test Data
**Objective**: Clean test data organization

**Sub-tasks**:
1. **Audit Test Fixtures**:
   - Find all non-code fixture data outside allowed locations
   - Move to `tests/PYTEST/` or rename to `PYTEST_*`

2. **Import Hygiene**:
   - Create test to block `src/` imports from `examples/` or `tests/`
   - Fix any existing violations

### Task 6: Hygiene Tests Implementation
**Objective**: Create enforcement tests

**Test Files to Create/Update**:
1. `tests/hygiene/test_configs_hygiene.py`:
   - Fail if configs/ contains non-YAML
   - Fail if generated patterns exist in configs/
   - Validate taxonomy structure

2. `tests/hygiene/test_outputs_hygiene.py`:
   - Fail if outputs/ root contains non-allowed buckets
   - Validate bucket structure

3. `tests/hygiene/test_import_hygiene.py`:
   - Fail if src/ imports from examples/ or tests/

4. `tests/ui/test_ui_reality.py`:
   - Forbid UI modules with mock data
   - Validate UI uses registry loaders

### Task 7: Acceptance & Verification
**Objective**: Ensure all requirements met

**Verification Steps**:
1. Run full test suite: `pytest -q`
2. Run `make check` if available
3. Manual verification of:
   - Configs taxonomy enforced
   - Outputs buckets enforced
   - Mandatory cost model working
   - Seed precedence implemented
   - UI uses real data only

## Implementation Phases

### Phase 1: Foundation (Tasks 1, 2, 6)
- Create evidence logs
- Implement config loaders with validation
- Create hygiene tests

### Phase 2: Migration (Tasks 3, 5)
- Migrate legacy configs to YAML
- Clean up test data organization
- Update code references

### Phase 3: UI Cleanup (Task 4)
- Remove mock data from UI
- Implement registry-based dropdowns
- Add error handling

### Phase 4: Verification & Cleanup (Task 7)
- Run full verification
- Fix any issues
- Document final state

## Dependencies & Risks

### Dependencies:
1. **Pydantic models** must be compatible with existing code
2. **Backward compatibility** during migration
3. **Test updates** required for new config locations

### Risks:
1. **Breaking changes** to existing workflows
2. **Performance impact** of additional validation
3. **Migration complexity** for 28 config points

### Mitigations:
1. **Phase migration** with backward compatibility flags
2. **Comprehensive testing** before each phase
3. **Documentation** of changes for users

## Success Criteria

1. **Configs directory** contains only YAML files in proper taxonomy
2. **Outputs directory** follows strict bucket structure
3. **UI uses real data** only, no mock fallbacks
4. **All tests pass** including new hygiene tests
5. **Mandatory cost model** enforced (commission/slippage required)
6. **Seed precedence** implemented (job > strategy, no env override)
7. **Evidence logs** created for all steps

## Deliverables Timeline

### Day 1-2: Phase 1 Completion
- Discovery evidence collected
- Config loaders implemented
- Hygiene tests created

### Day 3-4: Phase 2 Completion
- Legacy configs migrated
- Test data organized
- Code references updated

### Day 5: Phase 3 Completion
- UI mock data removed
- Registry-based dropdowns implemented

### Day 6: Phase 4 Completion
- Full verification
- Issue resolution
- Final documentation

## Team Coordination

### Required Skills:
1. **Backend Python**: Config loaders, Pydantic models
2. **Frontend/UI**: UI data provider updates
3. **Testing**: Hygiene test implementation
4. **DevOps**: Directory structure enforcement

### Communication Points:
- Daily standup on migration progress
- Weekly demo of completed phases
- Documentation updates shared with team

## Appendix: Detailed Migration Map

### From Audit v2 to Constitution v1:

| Config Point | Current Location | Target Location | Action Required |
|--------------|------------------|-----------------|-----------------|
| Timeframe List | Hardcoded in 4+ places | `configs/registry/timeframes.yaml` | Create YAML, update all references |
| Instrument List | `configs/portfolio/instruments.yaml` | `configs/registry/instruments.yaml` | Move and enhance |
| Commission/Slippage | `configs/funnel_min.json` + defaults | `configs/profiles/*.yaml` | Add to profiles, remove defaults |
| Memory Limits | Mixed defaults | `configs/profiles/*.yaml` | Standardize in profiles |
| Random Seeds | Mixed (42 + config) | `configs/strategies/*.yaml` | Strategy-level default_seed |
| Governance Thresholds | `configs/portfolio/governance_params.json` | `configs/portfolio/governance.yaml` | JSON → YAML conversion |

This plan provides a comprehensive roadmap for implementing Config Constitution v1 across the entire codebase.