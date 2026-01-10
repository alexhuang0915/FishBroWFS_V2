# Config Constitution v1 - Implementation Todo List

## Phase 1: Discovery & Foundation (Days 1-2)

### Task 1.1: Capture Current State Evidence
- [ ] Create `outputs/_dp_evidence/op_config_cleanup_discovery.txt`
- [ ] Run `find configs/ -type f | sort` and append to evidence
- [ ] Run `find outputs/ -maxdepth 1 -type d | sort` and append
- [ ] Search for hardcoded timeframes: `rg -n "\[.*\].*timeframe|timeframe.*\[.*\]" src/`
- [ ] Search for mock/fake data: `rg -n "mock|fake|demo|sample.*data" src/`
- [ ] Search for commission defaults: `rg -n "commission.*default|default.*commission" src/`
- [ ] Search for random seeds: `rg -n "random\.seed|np\.random\.seed|default_rng.*42" src/`
- [ ] Search for env var feature flags: `rg -n "FISHBRO_" src/ | grep -v "FISHBRO_OUTPUTS_ROOT"`

### Task 1.2: Create Config Loader Infrastructure
- [ ] Create directory structure: `src/config/` with subdirectories
- [ ] Create `src/config/registry/__init__.py` with base models
- [ ] Create `src/config/registry/timeframes.py` with Pydantic model:
  ```python
  class TimeframeRegistry(BaseModel):
      version: str = "1.0"
      allowed_timeframes: List[int]
      default: int
  ```
- [ ] Create `src/config/registry/instruments.py` with model
- [ ] Create `src/config/registry/datasets.py` with model  
- [ ] Create `src/config/registry/strategy_catalog.py` with model
- [ ] Create `src/config/profiles.py` with mandatory cost_model validation
- [ ] Create `src/config/strategies.py` with seed precedence logic

### Task 1.3: Create Hygiene Tests
- [ ] Create `tests/hygiene/__init__.py`
- [ ] Create `tests/hygiene/test_configs_hygiene.py`:
  - Test 1: configs/ contains only allowed subdirectories
  - Test 2: Only YAML files in configs/ (allowlist exceptions)
  - Test 3: No generated patterns in configs/
- [ ] Create `tests/hygiene/test_outputs_hygiene.py`:
  - Test 1: outputs/ root contains only allowed buckets
  - Test 2: No floating files in outputs/ root
- [ ] Create `tests/hygiene/test_import_hygiene.py`:
  - Test 1: src/ doesn't import from examples/
  - Test 2: src/ doesn't import from tests/
- [ ] Create `tests/ui/test_ui_reality.py`:
  - Test 1: No mock data generators in UI modules
  - Test 2: UI uses registry loaders for dropdowns

## Phase 2: Migration & Cleanup (Days 3-4)

### Task 2.1: Create Canonical YAML Files
- [ ] Create `configs/registry/timeframes.yaml`:
  ```yaml
  version: "1.0"
  allowed_timeframes: [15, 30, 60, 120, 240]
  default: 60
  ```
- [ ] Create `configs/registry/instruments.yaml` (enhance existing):
  ```yaml
  version: "1.0"
  instruments:
    - id: "CME.MNQ"
      display_name: "E-mini Nasdaq-100"
      profile: "CME_MNQ"
      type: "future"
      default_timeframe: 60
    - id: "TWF.MXF"
      display_name: "Taiwan Index Futures"
      profile: "TWF_MXF"
      type: "future"
      default_timeframe: 60
  default: "CME.MNQ"
  ```
- [ ] Create `configs/registry/datasets.yaml` from `dimensions_registry.json`:
  ```yaml
  version: "1.0"
  datasets:
    - id: "CME.MNQ.60m.2020-2024"
      storage_type: "npz"
      uri: "outputs/shared/{season}/CME.MNQ/bars/resampled_60m.npz"
      timezone: "Asia/Taipei"
      calendar: "CME_ELECTRONIC"
  default: "CME.MNQ.60m.2020-2024"
  ```
- [ ] Create `configs/registry/strategy_catalog.yaml`:
  ```yaml
  version: "1.0"
  strategies:
    - id: "s1_v1"
      display_name: "Stage 1 Strategy"
      family: "trend_following"
      config_file: "strategies/s1_v1.yaml"
      supported_instruments: ["CME.MNQ", "TWF.MXF"]
  ```

### Task 2.2: Update Profiles with Cost Model
- [ ] Update `configs/profiles/CME_MNQ.yaml` (from existing):
  ```yaml
  version: "2.0"
  symbol: "CME.MNQ"
  cost_model:
    commission_per_side_usd: 0.0  # REQUIRED
    slippage_per_side_usd: 0.0    # REQUIRED
  session:
    exchange_tz: "America/Chicago"
    data_tz: "Asia/Taipei"
  memory:
    default_limit_mb: 2048
    allow_auto_downsample: true
  ```
- [ ] Update all other profile YAMLs similarly
- [ ] Create `configs/profiles/_template.yaml` for new profiles

### Task 2.3: Create Strategy YAML Definitions
- [ ] Create `configs/strategies/s1_v1.yaml` from `funnel_min.json`:
  ```yaml
  version: "1.0"
  strategy_id: "s1_v1"
  determinism:
    default_seed: 42
  parameters:
    fast_period: {type: "int", min: 5, max: 20, default: 8}
    slow_period: {type: "int", min: 20, max: 50, default: 21}
  features:
    - name: "sma_20"
      timeframe: 60
    - name: "atr_14"
      timeframe: 60
  ```
- [ ] Create other strategy YAMLs as needed

### Task 2.4: Migrate Portfolio Configs
- [ ] Convert `configs/portfolio/governance_params.json` to `configs/portfolio/governance.yaml`
- [ ] Update `src/portfolio/governance/params.py` to load YAML
- [ ] Clean up legacy JSON files: `portfolio_policy_v1.json`, `portfolio_spec_v1.yaml`, etc.

### Task 2.5: Organize Test Data
- [ ] Find all test fixtures: `find tests/ -name "*.json" -o -name "*.yaml" -o -name "*.csv"`
- [ ] Move to `tests/PYTEST/` directory or rename with `PYTEST_` prefix
- [ ] Update test references to new locations

## Phase 3: UI & Code Updates (Day 5)

### Task 3.1: Update UI Data Providers
- [ ] Create `src/ui/data_providers.py`:
  ```python
  def get_timeframe_options():
      from config.registry.timeframes import load_timeframes
      return load_timeframes().allowed_timeframes
  
  def get_instrument_options():
      from config.registry.instruments import load_instruments
      return [(i.id, i.display_name) for i in load_instruments().instruments]
  ```
- [ ] Update `src/gui/desktop/tabs/op_tab.py:580` to use data providers
- [ ] Update `src/gui/desktop/tabs/portfolio_admission_tab.py` to remove mock data
- [ ] Update `src/control/supervisor/admission.py:100` to use registry timeframes

### Task 3.2: Remove Mock/Fake Data
- [ ] Remove `random.choice()` mock in `src/gui/desktop/tabs/portfolio_admission_tab.py:238`
- [ ] Remove any other mock data generators in UI
- [ ] Add proper error states for missing configs

### Task 3.3: Update Config References
- [ ] Update `src/contracts/features.py:90` to use registry timeframes
- [ ] Update `src/features/seed_default.py:29` to use registry timeframes
- [ ] Update `src/core/resampler.py` to use profile session specs
- [ ] Update `src/pipeline/runner_adapter.py` to use strategy configs
- [ ] Update `src/core/oom_gate.py` to use profile memory limits

### Task 3.4: Implement Seed Precedence
- [ ] Update `src/strategy/kernel.py` to use strategy default_seed
- [ ] Update `src/pipeline/runner_grid.py` to respect seed precedence
- [ ] Remove env-based seed overrides: `FISHBRO_PERF_PARAM_SUBSAMPLE_SEED`
- [ ] Add validation to block env seed overrides

## Phase 4: Verification & Finalization (Day 6)

### Task 4.1: Run Comprehensive Tests
- [ ] Run `pytest tests/hygiene/ -v` to verify hygiene tests pass
- [ ] Run `pytest tests/ -q` to ensure no regressions
- [ ] Run `make check` if available
- [ ] Create test coverage report

### Task 4.2: Manual Verification
- [ ] Verify configs/ directory structure matches taxonomy
- [ ] Verify outputs/ directory follows bucket structure
- [ ] Verify UI dropdowns use real registry data
- [ ] Verify mandatory cost model enforcement
- [ ] Verify seed precedence (job > strategy, no env)

### Task 4.3: Create Verification Evidence
- [ ] Create `outputs/_dp_evidence/op_config_cleanup_verification.txt`
- [ ] Document final configs/ structure
- [ ] Document final outputs/ structure
- [ ] Document all fixed issues
- [ ] Include test results

### Task 4.4: Cleanup & Documentation
- [ ] Remove legacy config files (backup if needed)
- [ ] Update README with new config structure
- [ ] Create migration guide for users
- [ ] Document new YAML schemas

## Critical Path Dependencies

1. **Pydantic Models First**: Cannot migrate configs without loader infrastructure
2. **Hygiene Tests Early**: Need tests to validate migration
3. **UI Updates Last**: UI depends on registry loaders being complete
4. **Verification Final**: All changes must be verified together

## Risk Mitigation

### Risk: Breaking Existing Workflows
- **Mitigation**: Phase migration with compatibility shims
- **Fallback**: Keep legacy loaders during transition with deprecation warnings

### Risk: Performance Impact
- **Mitigation**: Cache registry loads with `lru_cache`
- **Testing**: Profile config loading performance

### Risk: Test Failures
- **Mitigation**: Update tests incrementally
- **Backup**: Keep old test data during migration

## Success Metrics

1. **100% YAML**: All human-edited configs in YAML format
2. **0 Mock Data**: No mock/fake data in UI
3. **100% Test Pass**: All tests including hygiene tests pass
4. **Mandatory Fields**: Cost model required in profiles
5. **Seed Control**: No env-based seed overrides

## Rollback Plan

If critical issues arise:
1. Revert to using legacy config loaders
2. Keep new YAML files but don't enforce
3. Gradually re-implement with better testing

## Team Assignments (Suggested)

- **Backend Lead**: Config loaders, Pydantic models, migration
- **Frontend Lead**: UI updates, data providers, error states  
- **Testing Lead**: Hygiene tests, verification, test data cleanup
- **DevOps**: Directory structure, enforcement scripts

## Daily Checkpoints

### Day 1 End:
- Discovery evidence complete
- Config loader infrastructure created
- Hygiene tests skeleton created

### Day 2 End:
- All config loaders implemented
- Hygiene tests passing
- Canonical YAML templates created

### Day 3 End:
- All legacy configs migrated
- Test data organized
- Code references updated

### Day 4 End:
- UI mock data removed
- Registry-based dropdowns working
- Seed precedence implemented

### Day 5 End:
- All tests passing
- Manual verification complete
- Documentation updated

This todo list provides actionable steps for implementing Config Constitution v1 across the entire codebase.