# ENGINEERING_SPEC.md

## 1. System Components & Flow
The system follows a strict isolation pattern: `TUI -> Supervisor Core -> Worker -> Artifacts` (no HTTP/API).

### 1.1 The Supervisor Engine
*   **File**: `src/control/supervisor/supervisor.py`
*   **Heartbeat**: Workers must update `last_heartbeat` in `jobs_v2.db` every 30s.
*   **Isolation**: Every job runs in a separate process spawned via `subprocess` or `multiprocessing`.

### 1.2 Job Handlers
Handlers are the bridge between the Supervisor and the core logic.

| Job Type | Handler File | Core Script / Logic |
| :--- | :--- | :--- |
| **BUILD_DATA** | `handlers/build_data.py` | `src.control.shared_cli` |
| (removed) RUN_RESEARCH_V2 | (removed) | (removed) |
| **BUILD_PORTFOLIO** | `handlers/build_portfolio.py` | `src/core/portfolio/manager.py` |

---

## 2. Core Execution Mechanics

### 2.1 The Research Kernel
*   **File**: `src/core/backtest/kernel.py`
*   **Constraint**: Must be a "Pure Function". No side effects (IO, Global state).
*   **Input**: `Strategy` object + `DataFrame`.
*   **Output**: `ResearchResult` dataclass.

### 2.2 Feature Computation
*   **Manager**: `src/core/features/compute.py`
*   **Performance**: Uses `Numba` for high-performance vectorized operations.
*   **Alignment**: Features are automatically aligned to the nearest minute/hour bar during generation.

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
