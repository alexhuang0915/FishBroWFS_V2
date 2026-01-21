# Runtime Reachability Map

## Canonical Entrypoints

### 1. Backend & Supervisor
**Entrypoint**: `scripts/run_stack.py`
- **Role**: Orchestrates the entire backend stack (Supervisor, DB, Workers).
- **Modules**: `control.supervisor`, `control.supervisor_db`, `control.governance`.
- **SSOT**: Writes PID to `outputs/stack.pid`, manages `outputs/_trash/stack_stdout.log`.

### 2. Desktop UI
**Entrypoint**: `scripts/desktop_launcher.py`
- **Role**: Launches the Qt Desktop Interface.
- **Modules**: `gui.desktop.control_station.ControlStation`, `gui.services`.
- **SSOT**: Uses `SupervisorClient` (HTTP) to communicate with backend. No direct DB access.

### 3. Supervisor Worker
**Entrypoint**: `src/control/supervisor/bootstrap.py`
- **Role**: Process encapsulation for executing jobs (Research, Portfolio, etc.).
- **Modules**: `control.supervisor.bootstrap`, `core.runner`.
- **SSOT**: Managed by Supervisor; communicates via `SupervisorDB`.

### 4. Portfolio Runner
**Entrypoint**: `src/portfolio/runner_v1.py`
- **Role**: Builds portfolio artifacts from research signals.
- **Modules**: `portfolio.engine_v1`, `portfolio.allocator`, `portfolio.writer`.
- **SSOT**: Outputs to `outputs/seasons/`.

### 5. Research Generation
**Entrypoint**: `scripts/generate_research.py`
- **Role**: Generates research signals (e.g., S1, S2, S3 strategies).
- **Modules**: `research.generator`, `strategy`.
- **SSOT**: Outputs to `outputs/research/`.

## SSOT Boundaries
- **Governance**: `src/control/governance.py` manages `outputs/governance/`.
- **Jobs**: `src/control/supervisor/supervisor_db.py` manages `outputs/jobs.db`.
- **Artifacts**: `outputs/jobs/{job_id}/` is the definitive source for job results.
