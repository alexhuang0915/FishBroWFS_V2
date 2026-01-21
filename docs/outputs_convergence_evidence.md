# Outputs Structure Convergence Evidence

## 1. Path Authority
All backend and frontend components now resolve `outputs/` paths via `src/core/paths.py`.
The new `ThreeRoots` logic is enforced:
*   `runtime/`: `get_runtime_root()`
*   `artifacts/`: `get_artifacts_root()`
*   `exports/`: `get_exports_root()`

Legacy paths are sequestered in `outputs/legacy/` via `get_legacy_root()`.

## 2. Wiring Validation
Verified that `src/control/supervisor/db.py` uses the centralized `get_db_path()`, ensuring the database location `outputs/runtime/jobs_v2.db` is consistent across the system.
Frontend services (`JobLifecycleService`) have been updated to look for jobs in `artifacts/jobs/` and runtime state in `runtime/`.

Script output:
```
--- Wiring Verification ---
Path Authority (DB): /home/fishbro/FishBroWFS_V2/outputs/runtime/jobs_v2.db
Supervisor DB Path:  /home/fishbro/FishBroWFS_V2/outputs/runtime/jobs_v2.db
Artifacts Root:      /home/fishbro/FishBroWFS_V2/outputs/artifacts
Runtime Root:        /home/fishbro/FishBroWFS_V2/outputs/runtime
SUCCESS: Wiring and structure verified.
```

## 3. Directory Structure
`outputs/` contains only semantic roots:
```
outputs/
├── artifacts/  (Immutable runs, logs)
├── exports/    (User deliverables)
├── legacy/     (Historical data: deployment, research, strategies)
└── runtime/    (Ephemeral state: jobs_v2.db, snapshots)
```

## 4. Verdict
**WIRING OK**
Observability is preserved (DB moved but path updated). Runtime state is separated from artifacts.
