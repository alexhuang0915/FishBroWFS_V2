# PROOF: Dead Code Analysis for worker_main.py

## Objective
Determine whether `src/control/worker_main.py` is active or dead code within the FishBroWFS_V2 system.

## Findings

### 1. Primary Entrypoint Analysis
The main system entrypoint `scripts/run_stack.py` orchestrates the backend and UI.
- At line 197, it spawns the worker manager using:
  `sys.executable, "-m", "control.supervisor.supervisor"`
- It does **not** reference `control.worker_main`.

### 2. Supervisor Spawn Logic
The `Supervisor` class in `src/control/supervisor/supervisor.py` is responsible for spawning individual worker processes.
- At lines 46-47, it explicitly uses:
  `sys.executable, "-m", "control.supervisor.bootstrap"`
- The `bootstrap.py` module is the actual entrypoint that reads job specs, validates handlers, and maintains heartbeats via `SupervisorDB`.

### 3. Worker Bootstrap Evaluation
`src/control/supervisor/bootstrap.py` is a comprehensive worker implementation.
- It does not import or delegate to `worker_main.py`.
- It handles the full lifecycle of a job within the `Supervisor` ecosystem.

### 4. String References in Maintenance Scripts
A global search revealed string references to "worker_main" in:
- `src/control/worker_spawn_policy.py`: Used in `validate_pidfile` to check `cmdline`.
- `scripts/kill_stray_workers.py`: Used to identify processes for cleanup.
These scripts use the string literal "control.worker_main" as a legacy or vestigial marker, but no part of the system actually spawns a process with this module path anymore.

### 5. Internal Self-Admission
The docstring in `src/control/worker_main.py` (lines 48-52) explicitly states:
> "This is a simplified implementation that periodically checks for jobs and processes them. In a real implementation, this would integrate with the supervisor job system."

Since the system **has** a real implementation (`control.supervisor.bootstrap`) that integrates with the supervisor job system, `worker_main.py` is confirmed to be an obsolete or example-only file.

## Conclusion: DEAD CODE
`src/control/worker_main.py` is unreachable in all supported execution paths of the FishBroWFS_V2 stack. It should be removed to prevent confusion and reduce maintenance overhead.
