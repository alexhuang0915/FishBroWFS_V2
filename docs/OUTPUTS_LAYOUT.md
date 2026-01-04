# Outputs Directory Layout

This document describes the canonical layout for the `outputs/` directory in FishBroWFS_V2.

## Overview

The outputs directory is organized to separate different types of data and ensure clean, maintainable structure. The layout follows these principles:

1. **Season-based organization** - All research runs and shared data are organized by trading season
2. **Separation of concerns** - Different types of data (runs, shared caches, system state) are in separate directories
3. **Evidence preservation** - Critical debugging and diagnostic data is preserved during cleanup operations
4. **Trash system** - Items removed during cleanup are moved to timestamped trash directories

## Canonical Structure

```
outputs/
├── _dp_evidence/              # Debugging and evidence files (PRESERVED)
│   ├── run_logs/              # Execution logs
│   ├── screenshots/           # UI screenshots
│   └── test_evidence/         # Test execution evidence
├── _trash/                    # Items moved during cleanup (timestamped)
│   ├── diagnostics.20250104_120000/
│   └── fingerprints.20250104_120000/
├── seasons/                   # Season-based organization
│   └── 2026Q1/                # Current season
│       ├── runs/              # Research runs (canonical location)
│       │   └── run_<hash>/    # Individual run directories
│       │       ├── manifest.json
│       │       ├── metrics.json
│       │       ├── run_record.json
│       │       ├── trades.parquet    # Required for READY status
│       │       ├── equity.parquet    # Required for READY status
│       │       └── report.json       # Required for READY status
│       ├── portfolios/        # Portfolio artifacts
│       └── shared/           # Shared caches (bars, features)
│           └── <market>/
│               ├── 15m.npz
│               ├── 30m.npz
│               ├── 60m.npz
│               ├── 120m.npz
│               ├── 240m.npz
│               └── features/
│                   └── <strategy>/
├── shared/                   # Cross-season shared data
│   └── <market>/            # Market-specific shared data
├── system/                  # System state and configuration
│   ├── state/              # UI state persistence
│   │   └── active_run.json # Active run state (singleton)
│   └── logs/               # System logs
├── diagnostics/             # Diagnostic data (PRESERVED)
├── forensics/              # Forensic analysis data (PRESERVED)
└── fingerprints/           # Data fingerprints (PRESERVED)
```

## Legacy Directories

The following directories may exist but are considered legacy and should not be used for new data:

- `research_runs/` - Old location for research runs (migrate to `seasons/<SEASON>/runs/`)
- `test_season/` - Test data (consider moving to `_dp_evidence/`)
- `strategy_governance/` - Legacy governance data
- `portfolio_store/` - Legacy portfolio storage
- `autopass/` - Legacy auto-pass artifacts

## Active Run State

The system maintains a singleton active run state at:
```
outputs/system/state/active_run.json
```

Schema:
```json
{
  "season": "2026Q1",
  "run_id": "run_ac8a71aa",
  "run_dir": "outputs/seasons/2026Q1/runs/run_ac8a71aa",
  "status": "NONE|PARTIAL|READY|VERIFIED",
  "updated_at": "2026-01-04T07:14:17.053Z"
}
```

## Run Status Classification

- **NONE**: No run selected or run directory missing
- **PARTIAL**: `metrics.json` exists (even if trades/equity missing)
- **READY**: `metrics.json` + at least one of (`equity.parquet` / `trades.parquet` / `report.json`) exists
- **VERIFIED**: READY + passes promotable artifact validation (Phase18 strict)

## Safe Reset Utility

Use the safe reset utility to clean up outputs while preserving critical data:

```bash
# Dry run (show what would be done)
python scripts/ops/reset_outputs_safe.py --dry-run

# Actual reset (preserves default items)
python scripts/ops/reset_outputs_safe.py --yes

# Custom reset (preserve only specific items)
python scripts/ops/reset_outputs_safe.py --yes --keep _dp_evidence diagnostics

# Drop optional items (like jobsdb)
python scripts/ops/reset_outputs_safe.py --yes --drop jobsdb
```

## File Requirements for Research Runs

A complete research run should include:

### Required for PARTIAL status:
- `metrics.json` - Performance metrics (net_profit, max_dd, trades, etc.)

### Required for READY status (at least one):
- `equity.parquet` - Equity curve time series
- `trades.parquet` - Individual trade records  
- `report.json` - Comprehensive analysis report

### Always generated:
- `manifest.json` - Run configuration and metadata
- `run_record.json` - Execution timeline and logs

### Recommended for complete artifacts:
- All of the above files for full analytics capability

## Path Mapping

For consistency, use these path patterns:

| Purpose | Pattern | Example |
|---------|---------|---------|
| Run directory | `outputs/seasons/{season}/runs/{run_id}` | `outputs/seasons/2026Q1/runs/run_ac8a71aa` |
| Bars cache | `outputs/seasons/{season}/shared/{market}/{timeframe}m.npz` | `outputs/seasons/2026Q1/shared/CME.MNQ/60m.npz` |
| Features cache | `outputs/seasons/{season}/shared/{market}/features/{strategy}/` | `outputs/seasons/2026Q1/shared/CME.MNQ/features/S1/` |
| Active run state | `outputs/system/state/active_run.json` | `outputs/system/state/active_run.json` |

## Maintenance

1. **Regular cleanup**: Use the safe reset utility to maintain clean outputs
2. **Evidence preservation**: Critical debugging data in `_dp_evidence/` is always preserved
3. **Season migration**: When a new season starts, create new directory under `seasons/`
4. **Legacy cleanup**: Gradually migrate data from legacy directories to canonical locations