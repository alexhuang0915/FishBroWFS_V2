# FishBro Governance Console User Guide

## What This Is

FishBro Governance Console is the Control Tower for Live Kernel + Governance + Audit.

This is the official product interface for managing quantitative trading strategies through their full lifecycle: registration, admission, activation, and rebalancing. The console provides real-time visibility into portfolio state, audit trails, and kernel operations.

## Architecture

```
[Qt Desktop UI]
       ↓
[PortfolioService]
       ↓
[PortfolioManager]
   ↓         ↓
[Store]   [Audit]
       ↓
   [Stage2 Kernel]
```

**Components:**
- **Qt Desktop UI**: Modern desktop interface built with PySide6 (Qt)
- **PortfolioService**: Service layer that enforces governance policies
- **PortfolioManager**: Core portfolio management logic
- **Store**: Persistent storage for strategy state and artifacts
- **Audit**: Immutable audit trail of all governance decisions
- **Stage2 Kernel**: Live trading kernel for activated strategies

## Quick Start

### Launch the Governance Console

```bash
make desktop
```

The Qt Desktop UI will launch as a native window (no web browser required).

### First-Time Setup

1. Ensure dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```

2. Verify the system is healthy:
   ```bash
   make doctor
   ```

3. Start the Qt Desktop UI:
   ```bash
   make run
   ```

## Workflow

### 1. Register Strategy

From the Qt Desktop UI, click "New Strategy" to register a new strategy. Provide:
- Strategy ID (unique identifier)
- Configuration JSON (strategy parameters)

The strategy enters **INCUBATION** state.

### 2. Admit Strategy

Strategies in INCUBATION state can be admitted to the portfolio. Click "Admit" next to the strategy.

Admission runs the strategy through the live kernel for validation (not a mock). If validation passes, the strategy moves to **CANDIDATE** state.

### 3. Activate Strategy

CANDIDATE strategies can be activated for live trading. Click "Activate" to move the strategy to **ACTIVE** state.

Activated strategies are managed by the Stage2 kernel with real capital allocation.

### 4. Rebalance Portfolio

Click "Rebalance" to run portfolio rebalancing. This recalculates capital allocations across all active strategies based on current performance and risk metrics.

### 5. Monitor Audit Trail

The Qt Desktop UI shows recent audit events at the bottom. All governance decisions are recorded in an immutable audit trail.

## Where Data Lives

### Portfolio Store
```
outputs/portfolio_store/
├── strategies/          # Strategy state files
├── allocations/         # Capital allocation records
└── metadata/           # Portfolio metadata
```

### Audit Trail
```
outputs/audit/
├── events/             # Individual audit events
└── snapshots/         # Periodic audit snapshots
```

### Snapshots
```
outputs/snapshots/     # System forensic snapshots
```

## Testing & Quality Assurance

### Product Tests
Run the product test suite (excludes legacy UI):
```bash
make check
```

### Legacy UI Tests
Run legacy UI tests for historical reference:
```bash
make check-legacy
```

### Portfolio Governance Tests
Run portfolio governance unit tests:
```bash
make portfolio-gov-test
```

## Legacy System Note

### Qt Desktop UI is the Sole Product Interface
The Qt Desktop UI (`src/gui/desktop/`) is the only supported user interface. All legacy web UI components have been removed.

### Policy Enforcement
The product UI is strictly isolated from legacy code:
- Does not import `portfolio.*` modules directly
- Does not import `engine.*` modules
- Uses only the `dashboard.service.PortfolioService` API

Policy tests enforce these isolation rules.

## Troubleshooting

### Qt Desktop UI Won't Start
- Ensure Qt dependencies are installed (PySide6).
- Verify Python dependencies: `make doctor`
- If Wayland issues occur, try `make desktop-xcb` (X11 fallback).

### Tests Failing
- Ensure test database is clean: `rm -rf outputs/jobs.db outputs/portfolio_store`
- Run with more verbose output: `python -m pytest -v`

### No Strategies Appearing
- Check if portfolio store exists: `ls -la outputs/portfolio_store/`
- Register a test strategy via the UI

## Advanced Operations

### Running Research Pipeline
```bash
make run-research     # Phase 2: Backtest
make run-plateau      # Phase 3A: Plateau
make run-freeze       # Phase 3B: Freeze
make run-compile      # Phase 3C: Compile
```

### Generating System Snapshots
```bash
make snapshot        # Generate forensic system snapshot
```

### UI Forensics
```bash
make ui-forensics    # Generate UI forensics dump
```

## Support

For issues, check:
1. System logs: `make logs`
2. Audit trail in `outputs/audit/`
3. Test results: `make check`

The system is designed to be self-documenting through its tests and audit trails.