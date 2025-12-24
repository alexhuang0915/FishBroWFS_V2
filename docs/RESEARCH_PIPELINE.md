# Research Pipeline Documentation

## Overview

The FishBroWFS_V2 research pipeline is a multi-stage process for systematic strategy research and validation. This document describes the pipeline architecture, data flow, and key components.

## Pipeline Stages

### Stage 0: Coarse Screening
- **Purpose**: Initial parameter space exploration
- **Input**: Raw strategy parameters, dataset
- **Output**: Top-K candidates based on coarse metrics
- **Key Files**:
  - `outputs/seasons/{season}/stage0_coarse-{timestamp}/manifest.json`
  - `outputs/seasons/{season}/stage0_coarse-{timestamp}/candidates.parquet`

### Stage 1: Top-K Refinement
- **Purpose**: Detailed evaluation of Stage 0 winners
- **Input**: Stage 0 candidates
- **Output**: Refined top candidates with full metrics
- **Key Files**:
  - `outputs/seasons/{season}/stage1_topk-{timestamp}/manifest.json`
  - `outputs/seasons/{season}/stage1_topk-{timestamp}/metrics.parquet`

### Stage 2: Confirmation & Governance
- **Purpose**: Final validation and governance checks
- **Input**: Stage 1 winners
- **Output**: Governance-approved candidates
- **Key Files**:
  - `outputs/seasons/{season}/stage2_confirm-{timestamp}/manifest.json`
  - `outputs/seasons/{season}/stage2_confirm-{timestamp}/governance_report.json`

## Canonical Results Consolidation

### outputs/research/ Directory
The official consolidated results are stored in `outputs/research/`:

1. **canonical_results.json**
   - Contains final performance metrics for all research runs
   - Schema: List of objects with fields:
     - `run_id`: Unique identifier for the run
     - `strategy_id`: Strategy identifier
     - `symbol`: Trading symbol
     - `bars`: Number of bars processed
     - `net_profit`: Net profit in base currency
     - `max_drawdown`: Maximum drawdown
     - `score_final`: Final composite score
     - `score_net_mdd`: Net profit / max drawdown ratio
     - `trades`: Number of trades
     - `start_date`, `end_date`: Time range
     - Additional optional fields: `sharpe`, `profit_factor`, etc.

2. **research_index.json**
   - Metadata index of all research runs
   - Schema: List of objects with fields:
     - `run_id`: Unique identifier
     - `season`: Season identifier (e.g., "2026Q1")
     - `stage`: Pipeline stage ("stage0_coarse", "stage1_topk", "stage2_confirm")
     - `mode`: Research mode ("smoke", "lite", "full")
     - `strategy_id`: Strategy identifier
     - `dataset_id`: Dataset identifier
     - `created_at`: ISO timestamp
     - `status`: Run status ("completed", "failed", "running")
     - `manifest_path`: Optional path to manifest.json

## UI Integration

### Candidates Page
The GUI provides a dedicated Candidates page (`/candidates`) that displays:
- Canonical results from `outputs/research/canonical_results.json`
- Research index from `outputs/research/research_index.json`
- Filtering by strategy, season, and stage
- Refresh functionality to reload from disk

### Path Contract
- **UI Contract**: All UI components must read from `outputs/research/` as the single source of truth
- **Service Layer**: `src/FishBroWFS_V2/gui/services/candidates_reader.py` provides the reading interface
- **Data Flow**: Research pipeline → `outputs/research/` → Candidates Reader → UI

## Service Components

### Candidates Reader (`candidates_reader.py`)
```python
# Core functions
load_canonical_results() -> List[CanonicalResult]
load_research_index() -> List[ResearchIndexEntry]
get_canonical_results_by_strategy(strategy_id: str) -> List[CanonicalResult]
get_canonical_results_by_run_id(run_id: str) -> Optional[CanonicalResult]
refresh_canonical_results() -> bool
refresh_research_index() -> bool
```

### Data Classes
```python
@dataclass
class CanonicalResult:
    run_id: str
    strategy_id: str
    symbol: str
    bars: int
    net_profit: float
    max_drawdown: float
    score_final: float
    score_net_mdd: float
    trades: int
    start_date: str
    end_date: str
    # ... optional fields

@dataclass
class ResearchIndexEntry:
    run_id: str
    season: str
    stage: str
    mode: str
    strategy_id: str
    dataset_id: str
    created_at: str
    status: str
    manifest_path: Optional[str]
```

## Makefile Integration

### Official GUI Entry Point
```bash
make gui  # Starts the official GUI: src/FishBroWFS_V2/gui/nicegui/app.py
```

### Legacy Mode (for backward compatibility)
```bash
make gui-legacy  # Starts Control API + Mission Control (legacy)
```

## Testing Considerations

### Test File Organization
- All test files are now organized under `tests/` directory
- Root directory test files have been moved to `tests/root_moved/`
- Pytest automatically discovers tests in `tests/` directory

### Key Test Categories
1. **Unit Tests**: Individual component testing
2. **Integration Tests**: Component interaction testing
3. **Contract Tests**: API and schema contract validation
4. **Performance Tests**: Pipeline performance benchmarking

## Maintenance Guidelines

### Adding New Research Stages
1. Update pipeline to write to `outputs/research/`
2. Extend `canonical_results.json` schema if needed
3. Update `research_index.json` with new stage metadata
4. Update UI components to handle new stage

### Refreshing Data
- UI provides "Refresh Data" button to reload from disk
- Service layer caches data for performance
- Manual refresh available via API or direct file modification

### Debugging Pipeline Issues
1. Check `outputs/research/` files exist and are valid JSON
2. Verify pipeline writes correct data format
3. Check UI service layer for parsing errors
4. Review logs for any file system permissions issues

## Related Documentation

- [GUI Architecture](docs/GUI_ARCHITECTURE.md) - GUI component design
- [Research CLI](docs/RESEARCH_CLI.md) - Command-line research tools
- [Portfolio Integration](docs/PORTFOLIO_INTEGRATION.md) - Research to portfolio pipeline
- [API Documentation](docs/API.md) - Control API endpoints

## Version History

- **2025-12-24**: Initial documentation (P0.5-4)
- **Key Changes**:
  - Unified canonical results path to `outputs/research/`
  - Created Candidates Reader service
  - Added Candidates page to GUI
  - Organized test files under `tests/` directory
  - Defined official GUI entry point