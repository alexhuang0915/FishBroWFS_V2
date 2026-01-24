# SYSTEM_MAP.md

## 1. System Philosophy
**"The Mainline"**: A single, coherent flow from Raw Data to Actionable Decision.
`RAW -> Data Prepare -> Research/WFS -> Results/Artifacts -> Decision/Export`

### Core Invariants (The Logic-Only Constitution)
1.  **Mainline Coherence**: UI/Scripts must guide the user from step 0 to N without magic jumps.
2.  **Observability**: Every action has a visible reaction (Log, UI State, or Output file). NO "Black Holes".
3.  **Clean Outputs**:
    *   `runtime/`: Ephemeral, disposable (DB, Locks, Cache).
    *   `artifacts/`: Immutable, auditable evidence.
    *   `exports/`: Derived deliverables (Reports, Code).
4.  **Evidence in Docs**: Discovery and reasoning go to `docs/`, not `outputs/`.

## 2. Architecture Layers

### Layer 0: Bedrock (Data)
*   **Source**: `FishBroData/raw` (Immutable Ticks/Min data).
*   **Gate**: `src/core/data/reader.py` (Strict Reader with Checksums).
*   **Output**: `outputs/shared/.../bars/` (Primary: `.npz`).

### Layer 1: The Factory (Feature Engineering)
*   **Source**: `src/contracts/feature.py` (Definitions).
*   **Engine**: `src/core/features/` (Declarative Calculator).
*   **Output**: Feature Matrices (DataFrame).

### Layer 2: The Lab (Research Engine)
*   **Source**: `src/contracts/strategy.py` (Hypotheses).
*   **Engine**: `src/core/backtest/` (Pure Function Kernel).
*   **Output**: `ResearchResult` (Performance Metrics + Logs).

### Layer 3: The Vault (Storage)
*   **Manager**: `src/core/artifacts/` (CAS Writer).
*   **Physical**:
    *   **Job Artifacts (Receipts/Logs)**: `outputs/artifacts/jobs/{job_id}/`.
    *   **Domain Artifacts (Shared Data)**: `outputs/shared/{season}/{dataset_id}/`.

### Layer 4: The Court (Governance & Decision)
*   **Action**: `src/core/governance/` (Gatekeeper).
*   **Logic**: Filtering `ResearchResult` based on `Policy`.
*   **Output**: `Decision` (Admit/Reject) -> `outputs/artifacts/decisions/`.

### Layer 5: The Interface (UI & Observation)
*   **Frontend**: TUI Control Station (Textual).
*   **Backend**: Supervisor Core (in-proc submit + sqlite-backed worker loop, no HTTP).

## 3. Single Source of Truth (SSOT)
> See [ARCHITECTURE_SSOT.md](./ARCHITECTURE_SSOT.md) for detailed flow.

*   **Code Contracts**: `src/contracts/` (Pydantic Models).
*   **System State**: `outputs/runtime/jobs_v2.db` (Job Lifecycle).
*   **Job Receipts**: `outputs/artifacts/jobs/.../{job_type}_manifest.json`.
*   **Domain Manifests**: `outputs/shared/...` or `outputs/artifacts/seasons/...`.
*   **Runtime Index**: `outputs/runtime/bar_prepare_index.json`.
