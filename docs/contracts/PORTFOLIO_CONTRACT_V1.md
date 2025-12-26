# Portfolio Contract V1

## Overview

This document defines the contract for portfolio generation in Phase 11. It establishes clear separation between research portfolio specifications and execution portfolio specifications.

## Core Principle

**ResearchPortfolioSpec ≠ Execution PortfolioSpec**

## Definitions

### 1. ResearchPortfolioSpec (Phase 11)
- **Purpose**: Generated from research decisions for artifact creation
- **Source**: Research Console decisions and index data
- **Format**: Pydantic BaseModel with deterministic ID generation
- **Usage**: Research artifact generation, audit trail, portfolio preview
- **Key Fields**:
  - `portfolio_id`: Deterministic SHA1 hash (first 12 chars)
  - `season`: Research season identifier
  - `mode`: Always "MVP_MNQ_MXF"
  - `symbols_allowlist`: ["CME.MNQ", "TWF.MXF"]
  - `generated_from_decision_log`: Path to source decisions
  - `legs`: List of ResearchPortfolioLeg objects

### 2. Execution PortfolioSpec (Phase 8)
- **Purpose**: Portfolio execution and trading
- **Source**: Strategy registry and manual configuration
- **Format**: Dataclass with validation
- **Usage**: Portfolio OS execution engine
- **Key Fields**:
  - `portfolio_id`: User-defined identifier
  - `version`: Portfolio version
  - `data_tz`: Fixed to "Asia/Taipei"
  - `legs`: List of PortfolioLeg objects with execution parameters

## Import Rules

### Phase 11 Modules MUST:
```python
# ✅ CORRECT
from FishBroWFS_V2.portfolio.research_spec import ResearchPortfolioSpec, ResearchPortfolioLeg
from FishBroWFS_V2.portfolio.hash_utils import stable_json_dumps, sha1_text
from FishBroWFS_V2.portfolio.builder import build_portfolio_spec_from_research
from FishBroWFS_V2.portfolio.decisions_reader import parse_decisions_log_lines
from FishBroWFS_V2.portfolio.writer import write_portfolio_artifacts
```

### Phase 11 Modules MUST NOT:
```python
# ❌ FORBIDDEN
from FishBroWFS_V2.portfolio.spec import PortfolioSpec, PortfolioLeg
```

## Deterministic Requirements

### Portfolio ID Generation
- Must be deterministic: same inputs → same portfolio_id
- Generated from: season, mode, allowlist, keep_run_ids, legs_core_fields
- Algorithm: SHA1(stable_json_dumps(payload))[:12]
- stable_json_dumps uses: sort_keys=True, separators=(',', ':'), ensure_ascii=False

### Legs Sorting
Legs must be sorted deterministically by:
1. symbol (ascending)
2. timeframe_min (ascending)
3. strategy_id (ascending)
4. run_id (ascending)

## Pure Function Contracts

### Builder Functions
- `build_portfolio_spec_from_research()`: Pure function, no IO
- `parse_decisions_log_lines()`: Pure function, no IO
- All helper functions in builder: Pure functions, no IO

### IO Functions
- `write_portfolio_artifacts()`: Only function allowed to perform IO
- Must be called explicitly from UI layer

## Artifact Structure

```
outputs/seasons/{season}/portfolio/{portfolio_id}/
├── portfolio_spec.json      # ResearchPortfolioSpec as JSON
├── portfolio_manifest.json  # Metadata and counts
└── README.md               # Human-readable summary
```

## Testing Requirements

### Test Coverage Must Include:
1. **Deterministic behavior**: Same inputs → same outputs
2. **Decision processing**: Last decision for each run_id wins
3. **Filtering**: Only KEEP decisions, only allowlisted symbols
4. **Parsing tolerance**: Blank lines, bad lines, format variations
5. **IO isolation**: Writer tests use temp directories

## Migration Notes

When Phase 11 portfolio specs need to be converted to execution specs:
1. Create conversion function in separate module
2. Validate all required execution fields are available
3. Maintain audit trail of conversion
4. Document any assumptions or defaults applied

## Version History

- **V1 (2024)**: Initial contract for Phase 11
- Establishes clear separation between research and execution specs
- Defines deterministic requirements for auditability
- Sets import boundaries to prevent coupling