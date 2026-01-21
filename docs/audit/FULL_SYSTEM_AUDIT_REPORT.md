# Full System Audit Report

## Executive Summary
(high-level health assessment)

## Layer A – Configuration
- Findings: ✅ OK
- Notes:
  - Configuration is strictly typed using Pydantic models (Schema v1).
  - All configs (Registry, Profiles, Strategies) are loaded via a central `src/config` module which acts as the SSOT.
  - Governance policies (Correlation, Drawdown, Breaker) are defined as strict Pydantic models in `PortfolioConfig` (`src/config/portfolio.py`) and include validation logic (`validate_strategy_admission`).
  - SHA256 hashes are computed on load for provenance consistency.
  - No hardcoded fallbacks found that would shadow config files; defaults are explicit in the schema.


## Layer B – Engine & Workers
- Findings: ⚠️ RISK (Dead Code), ✅ OK (Architecture)
- Notes:
  - Architecture follows a strictly supervised pattern: `Supervisor` -> `bootstrap.py` -> `JobHandler`.
  - `SupervisorDB` (`jobs_v2.db`) is the SSOT for job lifecycle.
  - Workers self-register and heartbeat; Supervisor kills stragglers.
  - **Dead Code Risk**: `src/control/worker_main.py` appears to be a vestigial/simplified worker implementation that is not used by the `Supervisor` (which calls `bootstrap.py`). It is misleading and should be removed to avoid confusion.
  - Execution contracts are strong: `bootstrap.py` re-validates job state before running.


## Layer C – State & SSOT
- Findings: ✅ OK
- Notes:
  - `SupervisorDB` is the definitive SSOT for job state.
  - UI State (`JobStore` in `src/gui/desktop/state/job_store.py`) is an in-memory cache that mirrors the SSOT; it does not persist data independently.
  - `ResearchSelectionState` is a minimal pointer (ID only), preventing state duplication.
  - No hidden state containers found that rival the DB.


## Layer D – Research & Portfolio
- Findings: ⚠️ RISK (Determinism), ✅ OK (Gatekeeping)
- Notes:
  - `AdmissionController` (`src/control/supervisor/admission.py`) serves as a strict "Gatekeeper", preventing invalid jobs from entering the queue.
  - Artifact consumption is direct (`load_signal_series` loads parquet files), adhering to "Artifact-driven UI".
  - **Determinism Risk**: `PortfolioSpecV1` only specifies `strategy_ids`, not specific execution/run IDs. `runner_v1.py` uses glob patterns (`list(outputs_root.glob(pattern))[0]`) to find artifacts. If multiple runs exist for a strategy, the selection is implicit and potentially non-deterministic.


## Layer E – UI
- Findings: ✅ OK
- Notes:
  - UI strictly uses `SupervisorClient` (`src/gui/desktop/services/supervisor_client.py`) to communicate with the engine via HTTP.
  - No evidence of "shadow" execution paths (direct subprocess calls or DB writes) in the UI code.
  - `OpTab` uses an adapter pattern to safely wrap new refactored components, degrading gracefully if they are missing (though this fallback path is technically "dead" in a correct install).


## Layer F – Governance & Policy
- Findings: ✅ OK
- Notes:
  - `BatchGovernanceStore` (`src/control/governance.py`) enforces strict immutability rules for frozen batches.
  - `policy_enforcement.py` provides standardized `evaluate_preflight` and `evaluate_postflight` hooks used by the Supervisor.
  - Policy logic is separated from execution logic, allowing for independent auditing.


## Layer G – Tests
- Findings: ✅ OK
- Notes:
  - High coverage (343 tests).
  - `tests/test_phase14_governance.py` rigorously tests batch immutability/freezing logic.
  - `tests/test_portfolio_validate.py` covers schema validation.
  - Test suite matches the "Separation of Concerns" principle (e.g., `tests/control`, `tests/portfolio`).

## Layer H – Build & CI
- Findings: ✅ OK
- Notes:
  - `Makefile` provides standardized entrypoints (`up`, `down`, `check`, `doctor`).
  - `make up` correctly sequences the backend start (wait for health) before launching the UI.
  - `make down` includes aggressive cleanup (kill PID, port check) to prevent zombie processes.
  - `scripts/run_stack.py` encapsulates the complexity of process management.

## Cross-Cutting Risks
(things that span multiple layers)

## Safe Zones
(areas explicitly safe to ignore)

# Audit Conclusion
The codebase is in **Excellent** structural shape with high adherence to the "Golden Path" architecture.
- **Governance** is enforced by code (`AdmissionController`, `GovernanceStore`).
- **SSOT** is respected (`SupervisorDB`).
- **UI** is properly decoupled (`SupervisorClient`).

**Identified Risks to Remediate:**
1.  **Dead Code**: Remove `src/control/worker_main.py`.
2.  **Determinism**: `runner_v1.py` artifact loading needs to be pinned to specific Run IDs, not just Strategy IDs, to ensure 100% reproducible portfolio builds.

