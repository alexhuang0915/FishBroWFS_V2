# JOB_SSOT_UI_CONTRACT_V1

## Meta
- **Status**: ACTIVE
- **Version**: 1.0
- **Scope**: FishBro WFS Desktop UI (PySide6)

## Objective
To eliminate "silent failures" and "observable-gap" bugs by ensuring every user action that triggers backend work is registered as a **Job** and visible in the **Ops Tab** within 1 second.

## 1. Minimal Job Definition
Every UI job must be represented by a `JobRecord` with these fields:

| Field | Type | Description |
| :--- | :--- | :--- |
| `job_id` | `str` | Unique identifier (as returned by supervisor). |
| `job_type` | `str` | e.g., `prepare`, `backtest`, `export`, `portfolio`. |
| `created_at` | `datetime` | Local instantiation time. |
| `status` | `enum` | `queued`, `running`, `done`, `failed`, `canceled`. |
| `progress_stage` | `str` | Human-readable current activity (e.g., "Calculating variance"). |
| `error_digest` | `str?` | Concise error snippet for quick debugging. |
| `artifact_dir` | `str?` | Path to job outputs if `done`. |

## 2. Global Invariant
- **Source of Truth**: The `JobStore` singleton is the only source of truth for job lifecycle state.
- **Mirroring**: Any other tab (Research, Portfolio, etc.) displaying job status must use a **read-only mirror** of the `JobStore` data. They must NOT manage their own lifecycle state independently.

## 3. Interaction Contract (The "1-Second Rule")
1. User clicks a "Run" or "Prepare" button.
2. The UI calls the backend Service.
3. Upon success/acknowledgment from backend, the UI **must** call `job_store.upsert()`.
4. The **Ops Tab** must refresh automatically to show the new entry.

---

# UI_TABS_FINAL_SET_V1

## Tab Architecture
The UI is converged to exactly **5 visible tabs**.

1. **Data Prepare** (`BarPrepareTab`): Input configuration and raw data builds.
2. **Registry** (`RegistryTab`): Review of registered assets/strategies.
3. **Research / Backtest** (`OpTab`): Launching and tuning backtests.
4. **Portfolio / Decision / Export** (`AllocationTab`+`DecisionGate`): Merged portfolio management.
5. **Ops / Jobs & Logs**: Central monitor for ALL jobs and system logs.
