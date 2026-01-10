# Config Constitution v1 - Architecture Diagram

## System Architecture Overview

```mermaid
graph TB
    subgraph "Config Sources (Human-edited)"
        Registry[configs/registry/]
        Profiles[configs/profiles/]
        Strategies[configs/strategies/]
        Portfolio[configs/portfolio/]
    end

    subgraph "Config Loaders"
        RegistryLoader[Registry Loaders]
        ProfileLoader[Profile Loader]
        StrategyLoader[Strategy Loader]
        PortfolioLoader[Portfolio Loader]
    end

    subgraph "Validation & Enforcement"
        CostModel[Cost Model Validator]
        SeedPrecedence[Seed Precedence]
        HygieneTests[Hygiene Tests]
    end

    subgraph "Consumers"
        UI[UI Layer]
        Engine[Engine Layer]
        Backtest[Backtest Layer]
        PortfolioMgmt[Portfolio Management]
    end

    Registry --> RegistryLoader
    Profiles --> ProfileLoader
    Strategies --> StrategyLoader
    Portfolio --> PortfolioLoader

    RegistryLoader --> CostModel
    ProfileLoader --> CostModel
    StrategyLoader --> SeedPrecedence
    
    CostModel --> UI
    CostModel --> Engine
    SeedPrecedence --> Backtest
    PortfolioLoader --> PortfolioMgmt

    HygieneTests --> Registry
    HygieneTests --> Profiles
    HygieneTests --> Strategies
    HygieneTests --> Portfolio

    UI --> Outputs[outputs/ buckets]
    Engine --> Outputs
    Backtest --> Outputs
    PortfolioMgmt --> Outputs
```

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant User as User/UI
    participant Registry as Registry YAML
    participant Profile as Profile YAML
    participant Strategy as Strategy YAML
    participant Loader as Config Loader
    participant Validator as Validator
    participant Consumer as System Consumer

    User->>Registry: Select timeframe
    User->>Registry: Select instrument
    User->>Profile: Configure cost model
    User->>Strategy: Set parameters
    
    Registry->>Loader: Load timeframes
    Profile->>Loader: Load profile
    Strategy->>Loader: Load strategy
    
    Loader->>Validator: Validate cost model
    Note over Validator: commission/slippage required
    
    Loader->>Validator: Validate seed precedence
    Note over Validator: job.seed > strategy.default_seed
    
    Validator->>Consumer: Provide validated config
    Consumer->>Consumer: Execute with config
    Consumer->>Outputs: Write to allowed buckets
```

## Configuration Taxonomy Hierarchy

```mermaid
graph TD
    Root[Config Constitution v1]
    
    Root --> Registry[Registry Layer]
    Root --> Profiles[Profile Layer]
    Root --> Strategies[Strategy Layer]
    Root --> Portfolio[Portfolio Layer]
    Root --> Constants[Code Constants]
    Root --> Environment[Environment]
    
    Registry --> Timeframes[timeframes.yaml]
    Registry --> Instruments[instruments.yaml]
    Registry --> Datasets[datasets.yaml]
    Registry --> StrategyCatalog[strategy_catalog.yaml]
    
    Profiles --> CME_MNQ[CME_MNQ.yaml]
    Profiles --> TWF_MXF[TWF_MXF.yaml]
    Profiles --> CostModel[cost_model section]
    Profiles --> Session[session specs]
    Profiles --> Memory[memory limits]
    
    Strategies --> S1[s1_v1.yaml]
    Strategies --> S2[s2_v1.yaml]
    Strategies --> S3[s3_v1.yaml]
    Strategies --> Determinism[determinism section]
    Strategies --> Parameters[parameters section]
    
    Portfolio --> Governance[governance.yaml]
    Portfolio --> Allocation[allocation.yaml]
    
    Constants --> DataAlignment[Data alignment algorithms]
    Constants --> PathTemplates[Path templates]
    Constants --> ExecutionSemantics[Execution semantics]
    
    Environment --> OutputsRoot[FISHBRO_OUTPUTS_ROOT]
    Environment --> SystemFlags[System-level flags only]
```

## Migration Path from Current State

```mermaid
graph LR
    subgraph "Current State (Audit v2)"
        A1[Hardcoded timeframes]
        A2[dimensions_registry.json]
        A3[funnel_min.json]
        A4[governance_params.json]
        A5[instruments.yaml]
        A6[Environment variables]
    end

    subgraph "Target State (Constitution v1)"
        B1[timeframes.yaml]
        B2[datasets.yaml]
        B3[strategies/*.yaml]
        B4[governance.yaml]
        B5[instruments.yaml enhanced]
        B6[Restricted env vars]
    end

    A1 -->|Migrate| B1
    A2 -->|Convert| B2
    A3 -->|Split| B3
    A4 -->|Convert| B4
    A5 -->|Enhance| B5
    A6 -->|Restrict| B6
```

## Enforcement Mechanism

```mermaid
graph TD
    Start[Code Change] --> HygieneTest[Hygiene Tests]
    
    HygieneTest --> ConfigTest[test_configs_hygiene.py]
    HygieneTest --> OutputTest[test_outputs_hygiene.py]
    HygieneTest --> ImportTest[test_import_hygiene.py]
    HygieneTest --> UIRealityTest[test_ui_reality.py]
    
    ConfigTest --> Check1[Only YAML in configs/]
    ConfigTest --> Check2[Proper taxonomy structure]
    ConfigTest --> Check3[No generated artifacts]
    
    OutputTest --> Check4[Only allowed buckets]
    OutputTest --> Check5[No root files]
    
    ImportTest --> Check6[src/ doesn't import examples/]
    ImportTest --> Check7[src/ doesn't import tests/]
    
    UIRealityTest --> Check8[No mock data]
    UIRealityTest --> Check9[Uses registry loaders]
    
    Check1 --> Fail[Test Failure]
    Check2 --> Fail
    Check3 --> Fail
    Check4 --> Fail
    Check5 --> Fail
    Check6 --> Fail
    Check7 --> Fail
    Check8 --> Fail
    Check9 --> Fail
    
    Fail --> Block[CI/CD Pipeline Blocked]
    Block --> Fix[Developer Must Fix]
    
    Check1 --> Pass[All Tests Pass]
    Check2 --> Pass
    Check3 --> Pass
    Check4 --> Pass
    Check5 --> Pass
    Check6 --> Pass
    Check7 --> Pass
    Check8 --> Pass
    Check9 --> Pass
    
    Pass --> Merge[Code Can Be Merged]
```

## Key Architectural Decisions

### 1. Centralized vs Distributed Loaders
**Decision**: Centralized loader infrastructure in `src/config/` with specialized submodules
**Rationale**: Single source of truth for config loading patterns, consistent validation

### 2. Validation Timing
**Decision**: Validate at load time, not at runtime
**Rationale**: Fail fast principle - catch configuration errors early

### 3. Caching Strategy
**Decision**: Use `lru_cache` for registry loads
**Rationale**: Registry data changes infrequently, improves performance

### 4. Backward Compatibility
**Decision**: Phase migration with deprecation warnings
**Rationale**: Minimize disruption to existing workflows

### 5. Error Handling
**Decision**: Explicit error states in UI, no silent fallbacks
**Rationale**: Better user experience, easier debugging

## Component Responsibilities

### Registry Loaders (`src/config/registry/`)
- Load and validate YAML files from `configs/registry/`
- Provide typed access to registry data
- Cache results for performance

### Profile Loader (`src/config/profiles.py`)
- Load profile YAML with mandatory cost model validation
- Merge instrument specs with session configurations
- Provide memory limit defaults

### Strategy Loader (`src/config/strategies.py`)
- Load strategy definitions with parameter schemas
- Implement seed precedence: job > strategy default
- Block environment-based overrides

### Portfolio Loader (`src/config/portfolio.py`)
- Load governance and allocation rules
- Convert legacy JSON to YAML format
- Validate correlation thresholds

### Hygiene Tests (`tests/hygiene/`)
- Enforce configs/ directory structure
- Enforce outputs/ bucket structure
- Block illegal imports
- Validate UI reality principle

## Data Contracts

### Timeframe Registry Contract
```yaml
version: "1.0"  # Required
allowed_timeframes: [15, 30, 60, 120, 240]  # Required, list of ints
default: 60  # Required, must be in allowed_timeframes
```

### Profile Contract
```yaml
version: "2.0"  # Required
symbol: "CME.MNQ"  # Required
cost_model:  # Required section
  commission_per_side_usd: 0.0  # Required, float
  slippage_per_side_usd: 0.0    # Required, float
session:  # Optional
  exchange_tz: "America/Chicago"
  data_tz: "Asia/Taipei"
memory:  # Optional
  default_limit_mb: 2048
  allow_auto_downsample: true
```

### Strategy Contract
```yaml
version: "1.0"
strategy_id: "s1_v1"
determinism:  # Required
  default_seed: 42  # Required, int
parameters:  # Required
  fast_period: 
    type: "int"
    min: 5
    max: 20
    default: 8
features:  # Optional
  - name: "sma_20"
    timeframe: 60
```

## Performance Considerations

1. **Registry Caching**: Use `@lru_cache(maxsize=1)` on loader functions
2. **Lazy Loading**: Load configs only when needed
3. **Validation Overhead**: Pre-compile Pydantic models
4. **Memory Usage**: Clear caches on config changes

## Security Considerations

1. **YAML Safety**: Use `yaml.safe_load()` only
2. **Path Validation**: Validate all file paths to prevent directory traversal
3. **Environment Variables**: Restrict to system-level only
4. **Seed Security**: Don't expose seed generation logic

This architecture provides a robust foundation for Config Constitution v1 implementation.