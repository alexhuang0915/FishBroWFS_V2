# YAML Config Callchain Map

## Registry YAMLs

| YAML File | Loader | Model | Consumers | Notes |
|-----------|--------|-------|-----------|-------|
| `configs/registry/timeframes.yaml` | `src/config/registry/timeframes.py:load_timeframes()` (line 83) | `TimeframeRegistry` (`src/config/registry/timeframes.py:26`) | UI dropdowns, API endpoints, timeframe validation | Cached with `@lru_cache(maxsize=1)` |
| `configs/registry/instruments.yaml` | `src/config/registry/instruments.py:load_instruments()` (line 136) | `InstrumentRegistry` (`src/config/registry/instruments.py:35`) | UI instrument selection, portfolio admission | |
| `configs/registry/datasets.yaml` | `src/config/registry/datasets.py:load_datasets()` (line 176) | `DatasetRegistry` (`src/config/registry/datasets.py:35`) | Dataset resolution, research job setup | |
| `configs/registry/strategy_catalog.yaml` | `src/config/registry/strategy_catalog.py:load_strategy_catalog()` (line 169) | `StrategyCatalogRegistry` (`src/config/registry/strategy_catalog.py:95`) | Strategy selection UI, research job validation | Only lists `s1_v1` strategy |

## Strategy YAMLs

| YAML File | Loader | Model | Consumers | Notes |
|-----------|--------|-------|-----------|-------|
| `configs/strategies/s1_v1.yaml` | `src/config/strategies.py:load_strategy("s1_v1")` (line 273) | `StrategyConfig` (`src/config/strategies.py:139`) | Research jobs, parameter validation, seed precedence | Referenced in `strategy_catalog.yaml:7` |
| `configs/strategies/sma_cross_v1.yaml` | **NOT LOADED** | `StrategyConfig` (if loaded) | None | No references in source code |
| `configs/strategies/S2.yaml` | **NOT LOADED** | `StrategyConfig` (if loaded) | None | No references in source code or catalog |
| `configs/strategies/S3.yaml` | **NOT LOADED** | `StrategyConfig` (if loaded) | None | No references in source code or catalog |
| `configs/strategies/S1/baseline.yaml` | **NOT LOADED** (legacy) | N/A | None | Migrated to `s1_v1.yaml` |
| `configs/strategies/S2/baseline.yaml` | **NOT LOADED** (legacy) | N/A | None | Migrated to `S2.yaml` |
| `configs/strategies/S3/baseline.yaml` | **NOT LOADED** (legacy) | N/A | None | Migrated to `S3.yaml` |

## Portfolio YAMLs

| YAML File | Loader | Model | Consumers | Notes |
|-----------|--------|-------|-----------|-------|
| `configs/portfolio/governance.yaml` | `src/config/portfolio.py:load_portfolio_config()` (line 263) | `PortfolioConfig` (`src/config/portfolio.py:35`) | Portfolio admission gates, governance rules | |
| `configs/portfolio/instruments.yaml` | `src/portfolio/instruments.py:load_instrument_spec()` (line 53) | `InstrumentSpec` (`src/portfolio/models/instrument_spec.py:10`) | Portfolio instrument validation | Small file (531 bytes) |
| `configs/portfolio/portfolio_spec_v1.yaml` | `src/portfolio/loader.py:load_portfolio_spec()` (line 38) | `PortfolioSpec` (`src/portfolio/models/portfolio_spec.py:15`) | Job submission, portfolio building | |

## Profile YAMLs

| YAML File | Loader | Model | Consumers | Notes |
|-----------|--------|-------|-----------|-------|
| `configs/profiles/CME_MNQ_EXCHANGE_v1.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |
| `configs/profiles/CME_MNQ_EXCHANGE_v2.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |
| `configs/profiles/CME_MNQ_TPE_v1.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |
| `configs/profiles/CME_MNQ_TPE_v2.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |
| `configs/profiles/CME_MNQ_v2.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |
| `configs/profiles/TWF_MXF_TPE_v1.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |
| `configs/profiles/TWF_MXF_TPE_v2.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |
| `configs/profiles/TWF_MXF_v2.yaml` | `src/config/profiles.py:load_profile()` (line 237) | `ProfileConfig` (`src/config/profiles.py:40`) | Commission/slippage models, cost calculations | |

## ASCII Flow Diagram

```
Job Submission
    │
    ▼
portfolio_spec_v1.yaml (PortfolioSpec)
    │
    ▼
strategy_id → strategy_catalog.yaml (StrategyCatalogRegistry)
    │
    ▼
s1_v1.yaml (StrategyConfig)  # Only s1_v1 is in catalog
    │
    ▼
Parameter Schema Validation
    │
    ▼
Research Runner
    │
    ▼
Profile YAML (Commission/Slippage)
    │
    ▼
Governance Rules (governance.yaml)
    │
    ▼
Execution
```

## Key Observations

1. **Registry Loading Pattern**: All registry loaders follow the same pattern:
   ```
   get_registry_path(filename) → load_yaml(path) → Pydantic Model → @lru_cache
   ```

2. **Strategy Loading**: Only strategies listed in `strategy_catalog.yaml` can be loaded via `load_strategy()`.

3. **No Dynamic Discovery**: No code scans `configs/strategies/*.yaml` dynamically. Strategies must be explicitly registered.

4. **Config Root Resolution**: All paths are resolved via `get_config_root()` → `Path("configs")` relative to working directory.

5. **Caching**: Registry loaders use `@lru_cache` for performance.