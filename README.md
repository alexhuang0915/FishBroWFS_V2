# FishBroWFS_V2 — GOVERNANCE READY

FishBro Governance Console = Control Tower for Live Kernel + Governance + Audit

**Status**: Phase 10 (RELEASE HYGIENE) — Product Ready

## Quick Start

```bash
make dashboard
# or
python scripts/start_dashboard.py
```

The Governance Console provides:
- Portfolio strategy registration & admission
- Live kernel activation
- Audit trail visualization
- Rebalancing controls

## Architecture

```
[NiceGUI UI]
       ↓
[PortfolioService]
       ↓
[PortfolioManager]
   ↓         ↓
[Store]   [Audit]
       ↓
   [Stage2 Kernel]
```

## Legacy Note

The legacy `gui/nicegui` UI is deprecated and exists only for historical reference.
The product path uses `src/dashboard/ui.py` via `scripts/start_dashboard.py`.

For full documentation, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

---
*Original documentation continues below*
---

# FishBroWFS_V2

Speed-first quantitative backtesting engine.

This repository uses tests as the primary specification.

## Testing tiers

- **`make check`**: Fast, CI-safe tests (excludes slow research-grade tests)
- **`make research`**: Slow, manual research-grade tests (full backtest + correlation validation)

## Performance tiers

- **`make perf`**: Baseline (20000×1000) - Fast, suitable for commit-to-commit comparison (hot_runs=5, timeout=600s)
- **`make perf-mid`**: Mid-tier (20000×10000) - Medium-scale performance testing (hot_runs=3, timeout=1200s)
- **`make perf-heavy`**: Heavy-tier (200000×10000) - Full-scale validation (hot_runs=1, timeout=3600s, expensive, use intentionally)

**Note**: Mid-tier and heavy-tier are not for daily use. Baseline is recommended for regular performance checks.

See `docs/PERF_HARNESS.md` for detailed usage.

## Funnel Architecture (WFS at scale)

This project uses a multi-stage funnel:

- **Stage 0**: vector/proxy ranking (no matcher, no orders) — see `docs/STAGE0_FUNNEL.md`
- Stage 1: light backtest (planned)
- Stage 2: full semantics (matcher + fills) for final candidates

Stage 0 v0 implementation:

- `FishBroWFS_V2.stage0.stage0_score_ma_proxy()`

## GUI (Mission Control + Viewer)

Start full GUI stack:

```bash
make gui
```

**Services:**

- **Control API**: <http://localhost:8000>
- **Mission Control (NiceGUI)**: <http://localhost:8080>
- **Viewer / Audit Console (Streamlit)**: <http://localhost:8502>

Press `Ctrl+C` to stop all services.

## Viewer (Audit Console)

Start Viewer:

```bash
PYTHONPATH=src streamlit run src/FishBroWFS_V2/gui/viewer/app.py
```

**Viewer Pages:**

- **Overview**: Run overview and summary
- **KPI**: Key Performance Indicators with evidence drill-down
- **Winners**: Winners list and details
- **Governance**: Governance decisions and evidence
- **Artifacts**: Raw artifacts JSON viewer

**Usage:**

Viewer requires `season` and `run_id` query parameters:

```text
http://localhost:8502/?season=2026Q1&run_id=demo_20250101T000000Z
```

## Snapshot System (Local-Strict Filesystem Truth)

The snapshot system provides deterministic, auditable repository snapshots using Local-Strict filesystem scanning (not Git-based).

### Commands

- **Primary command**: `make snapshot` - Generate full repository forensic snapshot
- **Alias maintained**: `make full-snapshot` - Backward compatibility alias for `make snapshot`

### Output Artifacts

- **Raw snapshot artifacts**: `outputs/snapshots/full/` - Contains 12 forensic artifacts including `LOCAL_SCAN_RULES.json`, `REPO_TREE.txt`, `MANIFEST.json`, etc.
- **Compiled snapshot**: `outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md` - Single-file compiled snapshot with all artifacts embedded verbatim
- **Runtime truth**: `outputs/snapshots/runtime/RUNTIME_CONTEXT.md` - Auto-generated on dashboard startup with PID, git commit, port occupancy, governance state

### Local-Strict Scanning

- **Purpose**: Eliminate "UI fog / recursion" by making the system self-auditing with filesystem truth
- **Includes**: Untracked files within allowed roots (`src/`, `tests/`, `scripts/`, `docs/`)
- **Excludes**: `.gitignore` is ignored (`gitignore_respected=false`)
- **Policy**: Defined in `LOCAL_SCAN_RULES.json` with allowlist/denylist rules
- **Deterministic**: Same inputs produce identical output bytes

### UI Build Fingerprint

The dashboard displays a build fingerprint banner at the top:
```
BUILD: <commit> (dirty=<yes/no>) | ENTRY: <module> | SNAPSHOT: <timestamp or UNKNOWN>
```

This allows instant verification of the running build, entrypoint, and snapshot.

## 驗收流程（Phase 6.1）

1. `make gui` - 啟動所有服務
2. 瀏覽器打開 `http://localhost:8080` - Mission Control
3. 點擊 **Create Demo Job** - 建立 demo job
4. DONE job 出現 → 點擊 **Open Report** - 打開 Viewer
5. Viewer（8502）顯示 KPI 表 + 🔍 Evidence 正常顯示

👉 **Phase 6.1 驗收完成**
