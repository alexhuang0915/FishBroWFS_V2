# ENGINEERING_SPEC.md

Status: **Engineering rules** (normative).  
If a rule here conflicts with SSOT execution semantics, prefer:
- `docs/SPEC_ENGINE_V1.md`

## 1. System Components & Flow
The system follows a strict isolation pattern: `TUI -> Supervisor Core -> Worker -> Artifacts` (no HTTP/API).

### 1.1 The Supervisor Engine
*   **File**: `src/control/supervisor/__init__.py` (submit + handler registry), `src/control/supervisor/worker.py` (worker loop)
*   **Heartbeat**: Workers must update `last_heartbeat` in `jobs_v2.db` every 30s.
*   **Isolation**: Every job runs in a separate process spawned via `subprocess` or `multiprocessing`.

### 1.2 Job Handlers
Handlers are the bridge between the Supervisor and the core logic.

| Job Type | Handler File | Core Script / Logic |
| :--- | :--- | :--- |
| **BUILD_BARS** | `src/control/supervisor/handlers/build_data.py` | `python3 -m control.shared_cli build --build-bars ...` |
| **BUILD_FEATURES** | `src/control/supervisor/handlers/build_data.py` | `python3 -m control.shared_cli build --build-features ...` |
| **BUILD_DATA** (legacy) | `src/control/supervisor/handlers/build_data.py` | same as above, combined |
| **RUN_RESEARCH_WFS** | `src/control/supervisor/handlers/run_research_wfs.py` | WFS pipeline (result schema v1.0) |
| **BUILD_PORTFOLIO_V2** | `src/control/supervisor/handlers/build_portfolio.py` | Portfolio orchestrator |

---

## 2. Core Execution Mechanics

### 2.1 The Research Kernel
*   **File**: `src/core/backtest/kernel.py`
*   **Constraint**: Must be a "Pure Function". No side effects (IO, Global state).
*   **Input**: strategy + arrays/bars + config.
*   **Output**: deterministic metrics/series (JSON-serializable at artifact boundary).

### 2.2 Feature Computation
*   **Manager**: `src/core/features/compute.py`
*   **Performance**: deterministic numpy + optional numba kernels (where appropriate).
*   **Rule**: no pandas rolling in production compute; avoid hidden state; be explicit about warmup/NaNs.

---

## 3. Storage & Artifacts

### 3.1 Immutable Artifacts
Once a job finishes, its output folder in `outputs/artifacts/jobs/` is considered immutable.
*   **Naming**: `manifest.json` is the entry point.
*   **Cleanliness**: No temp files (`.tmp`, `.bak`) should persist in completion folders.

### 3.2 Runtime State
*   **Database**: `outputs/runtime/jobs_v2.db`.
*   **Index**: `outputs/runtime/bar_prepare_index.json` provides a materialized view of data readiness for the UI.

---

## 4. Development Standards
1.  **Strict Typing**: All new functions should have type hints (`from __future__ import annotations`).
2.  **Logic-Only Core**: `src/core` should never import from `src/control` or `src/gui`.
3.  **Explicit IO**: All file IO must go through `core.paths` helpers.
4.  **SSOT Guards (Fail-Closed)**: if configs violate SSOT (e.g., costs), fail fast before heavy compute.
5.  **JSON Safety**: artifacts must not contain `NaN`/`inf`; serialize as `null` + warnings if needed.
