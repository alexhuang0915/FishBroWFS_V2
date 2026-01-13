# Config Surface Area Audit - Complete Mapping

| Config Point | Current Source Type | Location | Actual Keys / Schema Read | Target Taxonomy |
|--------------|---------------------|----------|---------------------------|-----------------|
| **A) UI / Registry Layer** | | | | |
| Instrument List | YAML config + Hardcoded defaults | `configs/portfolio/instruments.yaml`, `src/portfolio/instruments.py:32`, `src/control/api.py:527` | `instruments` dict keys: `CME.MNQ`, `TWF.MXF` with fields: `exchange`, `currency`, `multiplier`, `tick_size`, `tick_value`, `margin_basis`, `initial_margin_per_contract`, `maintenance_margin_per_contract` | Registry |
| Timeframe List | Hardcoded constants | `src/contracts/features.py:90`, `src/features/seed_default.py:29`, `src/control/supervisor/admission.py:100`, `src/gui/desktop/tabs/op_tab.py:580` | Hardcoded values: `[15, 30, 60, 120, 240]` (integers) | Registry |
| Strategy List | Dynamic discovery + Hardcoded registry | `src/strategy/registry.py`, `src/control/strategy_rotation.py:202`, `src/control/api.py:488` | Loaded from strategy files in filesystem via `list_strategies()` | Registry |
| Dataset List | JSON config + Dynamic discovery | `configs/dimensions_registry.json`, `src/contracts/dimensions_loader.py:23`, `src/core/dimensions.py:31` | `by_dataset_id` dict, `by_symbol` dict with fields: `instrument_id`, `exchange`, `market`, `currency`, `tick_size`, `session` spec | Registry |
| **B) Engine / Backtest Layer** | | | | |
| Commission | JSON config defaults + Hardcoded fallbacks | `configs/funnel_min.json:27`, `src/pipeline/runner_adapter.py:149` | `commission` (float, default 0.0) | Profile |
| Slippage | JSON config defaults + Hardcoded fallbacks | `configs/funnel_min.json:28`, `src/pipeline/runner_adapter.py:150` | `slip` (float, default 0.0) | Profile |
| Instrument Specs | YAML config | `configs/portfolio/instruments.yaml:8-26`, `src/portfolio/instruments.py:32` | See Instrument List above | Profile |
| Session/Calendar/Timezone | JSON config + Hardcoded fallback | `configs/dimensions_registry.json`, `src/core/resampler.py:148`, `src/core/resampler.py:169` | `session.tz`, `session.open_taipei`, `session.close_taipei`, `session.breaks_taipei` | Profile |
| Data Alignment Policy | Hardcoded logic | `src/core/resampler.py:264`, `src/engine/signal_exporter.py:84`, `src/control/supervisor/handlers/run_portfolio_admission.py:38` | No config keys - algorithmic behavior (resample, merge_asof, forward_fill) | Code Constant |
| Random Seed | Hardcoded defaults + Environment variables | `src/strategy/entry_builder_nb.py:281`, `src/pipeline/runner_adapter.py:101`, `src/pipeline/runner_grid.py:208` | `seed`, `subsample_seed` (default 42), `FISHBRO_PERF_PARAM_SUBSAMPLE_SEED` env | Strategy + Environment |
| **C) Strategy Layer** | | | | |
| Parameter Grid | JSON config + Strategy schema | `configs/funnel_min.json:14-25`, `src/strategy/registry.py:271`, `src/control/param_grid.py:202` | `params_matrix` array, parameter schemas in strategy files | Strategy |
| Feature Flags | Environment variables + Hardcoded | `src/strategy/kernel.py:182`, `src/strategy/kernel.py:449`, `src/strategy/kernel.py:455`, `src/pipeline/runner_grid.py:79` | `FISHBRO_PROFILE_KERNEL`, `FISHBRO_FORCE_SPARSE_BUILDER`, `FISHBRO_PERF_TRIGGER_RATE`, `FISHBRO_USE_DENSE_BUILDER`, `FISHBRO_KERNEL_INTENT_MODE`, `FISHBRO_PROFILE_GRID`, `FISHBRO_PERF_SIM_ONLY` | Code Constant / Environment |
| Subsample Rate | JSON config + Hardcoded defaults | `configs/funnel_min.json:7`, `src/core/audit_schema.py:26`, `src/pipeline/funnel_plan.py:33` | `param_subsample_rate` (float, default varies), `FISHBRO_PERF_PARAM_SUBSAMPLE_RATE` env | Strategy |
| **D) Portfolio / Admission Layer** | | | | |
| Governance Thresholds | JSON config | `configs/portfolio/governance_params.json`, `src/portfolio/governance/params.py:48` | `dd_absolute_cap`, `portfolio_dd_cap`, `corr_member_hard_limit`, `corr_portfolio_hard_limit`, `max_pairwise_correlation`, `corr_min_samples`, `corr_rolling_days` | Portfolio |
| Correlation Policy | JSON config + Hardcoded logic | `configs/portfolio/governance_params.json:13-16`, `src/portfolio/governance/admission.py:23`, `src/control/portfolio/policies/correlation.py:91` | `corr_*` keys (see above) + hardcoded Pearson correlation algorithm | Portfolio |
| Risk Allocation | JSON config | `configs/portfolio/governance_params.json:6-12`, `configs/portfolio/governance_params.json:22-27` | `bucket_slots`, `portfolio_risk_budget_max`, `portfolio_vol_target`, `risk_model`, `vol_floor`, `w_max`, `w_min` | Portfolio |
| **E) Memory & Performance** | | | | |
| Memory Limits | JSON config defaults + Hardcoded | `configs/funnel_min.json:34`, `src/core/oom_gate.py:170`, `src/control/preflight.py:40` | `mem_limit_mb` (default: 2048 in funnel_min.json, 6000.0 in preflight) | Profile |
| OOM Gate Parameters | Hardcoded defaults | `src/core/oom_gate.py:172`, `configs/funnel_min.json:35-37` | `allow_auto_downsample` (bool, default True), `auto_downsample_step` (float, default 0.5), `auto_downsample_min` (float, default 0.02), `work_factor` (float, default 2.0) | Profile |
| **F) Output & Paths** | | | | |
| Outputs Root | Environment variables + Hardcoded defaults | `src/control/paths.py:16`, `src/control/report_links.py:16`, `src/core/season_context.py:19` | `FISHBRO_OUTPUTS_ROOT` env (default: "outputs") | Environment |
| Exports Root | Environment variables + Hardcoded defaults | `src/control/season_export.py:33` | `FISHBRO_EXPORTS_ROOT` env (default: "outputs/exports") | Environment |
| Artifact Path Templates | Hardcoded path patterns | `src/control/bars_store.py:57`, `src/core/artifacts.py` | Hardcoded templates: `outputs/shared/{season}/{dataset_id}/bars/`, `outputs/jobs/`, `outputs/seasons/` | Code Constant |
| **G) Randomness Sources** | | | | |
| NumPy RNG | Hardcoded + Config | `src/strategy/entry_builder_nb.py:281`, `src/features/causality.py:61` | `np.random.default_rng(seed)`, `np.random.seed(42)` | Strategy + Code Constant |
| Permutation Seed | Hardcoded defaults | `src/pipeline/runner_adapter.py:101`, `src/pipeline/runner_grid.py:208` | `subsample_seed` (default 42), `param_subsample_seed` (default 42) | Strategy |
| **H) Data Alignment Operations** | | | | |
| Resample Logic | Hardcoded algorithms | `src/core/resampler.py:264`, `src/core/artifact_writers.py:244` | No config keys - session-anchored resample algorithm | Code Constant |
| Merge & Fill | Hardcoded logic | `src/engine/signal_exporter.py:87`, `src/engine/signal_exporter.py:101` | `merge_asof`, `fillna(0.0)` hardcoded | Code Constant |
| Forward Fill | Parameterized | `src/control/supervisor/handlers/run_portfolio_admission.py:307` | `forward_fill` parameter (bool) | Code Constant |

## Key Insights from Audit:

1. **Configuration Fragmentation**: Settings are spread across JSON files, YAML files, hardcoded constants, environment variables, and `.get()` defaults.

2. **Taxonomy Readiness**: The system already has implicit taxonomy that maps to the target categories:
   - **Registry**: Instrument lists, timeframes, datasets, strategies
   - **Profile**: Commission, slippage, instrument specs, session times, memory limits
   - **Strategy**: Parameter grids, subsample rates, random seeds
   - **Portfolio**: Governance thresholds, correlation limits, risk allocation
   - **Code Constant**: Data alignment algorithms, path templates, execution semantics
   - **Environment**: Output paths, feature flags, performance tuning

3. **Critical Inconsistencies Found**:
   - Timeframes hardcoded in 4+ different places
   - Memory limit defaults vary (2048MB vs 6000MB)
   - Random seed defaults inconsistent (42 in some places, config-driven in others)
   - Commission/slippage defaults to 0.0 with no validation

4. **Hidden Configuration Surface**:
   - Environment variables used as feature flags create undocumented configuration
   - `.get()` with hardcoded defaults creates implicit schema
   - Fallback behaviors (like 24-hour trading session) are not documented

## Success Criteria Met:

This audit answers: "If we delete all configs and rebuild them cleanly, exactly which settings must exist — and where should each one live?"

The table above provides the complete mapping of all configuration points, their current sources, and their target taxonomy for the new YAML-based configuration constitution.