# YAML Config Callchain Audit Report

## Executive Summary

This audit examines how YAML configuration files are actually loaded and used at runtime in the FishBroWFS_V2 system. The key findings are:

1. **SSOT (Single Source of Truth)**: The `src/config/__init__.py` module provides a unified config loader infrastructure with `get_config_root()` returning `Path("configs")` relative to the working directory.

2. **Registry YAMLs are actively used**: All registry files (`timeframes.yaml`, `instruments.yaml`, `datasets.yaml`, `strategy_catalog.yaml`) are loaded via their respective registry loaders and consumed by UI dropdowns and API endpoints.

3. **Strategy YAMLs show mixed usage**:
   - `s1_v1.yaml`: **LOADED** - Referenced in `strategy_catalog.yaml` and used by research runs
   - `sma_cross_v1.yaml`: **NOT LOADED** - No references in source code, appears to be a placeholder
   - `S2.yaml`: **NOT LOADED** - Has content but not referenced in `strategy_catalog.yaml` or source code
   - `S3.yaml`: **NOT LOADED** - Has content but not referenced in `strategy_catalog.yaml` or source code

4. **Portfolio YAMLs are actively used**: `governance.yaml`, `instruments.yaml`, and `portfolio_spec_v1.yaml` are loaded by portfolio config loaders.

5. **Profile YAMLs are actively used**: All profile YAMLs are loaded via `load_profile()` for commission/slippage models.

## The "True Control Plane"

The actual YAMLs that drive a research run today are:

1. **Registry Control**:
   - `configs/registry/timeframes.yaml` → `TimeframeRegistry` → UI timeframe dropdowns
   - `configs/registry/instruments.yaml` → `InstrumentRegistry` → UI instrument selection
   - `configs/registry/datasets.yaml` → `DatasetRegistry` → dataset resolution
   - `configs/registry/strategy_catalog.yaml` → `StrategyCatalogRegistry` → strategy selection UI

2. **Strategy Control**:
   - `configs/strategies/s1_v1.yaml` → `StrategyConfig` → research job parameter validation

3. **Portfolio Control**:
   - `configs/portfolio/governance.yaml` → `PortfolioConfig` → admission gates and governance rules
   - `configs/portfolio/portfolio_spec_v1.yaml` → portfolio specification for job submission

4. **Profile Control**:
   - Profile YAMLs (e.g., `CME_MNQ_v2.yaml`) → `ProfileConfig` → commission/slippage models

## Biggest Confusion Points

### 1. S2/S3 Strategy YAMLs Are Orphaned
The `S2.yaml` and `S3.yaml` files contain complete strategy configurations but are **not referenced anywhere** in:
- `strategy_catalog.yaml` (only lists `s1_v1`)
- Source code (no `load_strategy("S2")` or `load_strategy("S3")` calls)
- UI dropdowns (catalog only shows `s1_v1`)

**Evidence**: `rg -n "S2\\.yaml|S3\\.yaml" src tests scripts` returns no matches except in the configs directory itself.

### 2. sma_cross_v1.yaml Is a Placeholder
The `sma_cross_v1.yaml` file exists but has no references in source code. It appears to be a legacy or example file.

### 3. Dynamic Loading Absent
No dynamic scanning of `configs/strategies/*.yaml` occurs. Strategies are only loaded when explicitly referenced via `load_strategy(strategy_id)`.

### 4. Baseline YAMLs in Subdirectories Are Legacy
The `S1/baseline.yaml`, `S2/baseline.yaml`, `S3/baseline.yaml` files appear to be migrated from an older structure. The new structure uses top-level `S2.yaml` and `S3.yaml` (though unused).

## Recommendations

### SSOT Set (Minimal Working Set)
For research runs today, these YAMLs matter:
- `configs/registry/*.yaml` (all 4 files)
- `configs/strategies/s1_v1.yaml`
- `configs/portfolio/governance.yaml`
- `configs/portfolio/portfolio_spec_v1.yaml`
- Profile YAMLs for instruments being traded

### Cleanup Candidates
1. **Delete**: `sma_cross_v1.yaml` (unused placeholder)
2. **Archive or Delete**: `S2.yaml`, `S3.yaml` (orphaned, though complete)
3. **Delete**: `S1/baseline.yaml`, `S2/baseline.yaml`, `S3/baseline.yaml` (migrated legacy)
4. **Review**: `configs/portfolio/instruments.yaml` (small file, check if used)

### Future Improvements
1. Add `S2` and `S3` to `strategy_catalog.yaml` if they're intended for use
2. Implement validation to detect orphaned YAMLs
3. Consider dynamic strategy discovery if appropriate

## Audit Methodology

1. **Inventory**: Listed all YAML files with `find configs -type f -name "*.yaml" -print0 | xargs -0 ls -la`
2. **Load Site Detection**: Used `ripgrep` to find all YAML loading patterns (`yaml.safe_load`, `load_yaml`, etc.)
3. **Callchain Tracing**: Examined loader modules, Pydantic models, and consumer sites
4. **Reference Analysis**: Searched for each YAML filename in source code to determine usage
5. **Dynamic Loading Check**: Searched for glob/scan patterns that might load YAMLs dynamically

All evidence files are in `EVIDENCE/` directory.