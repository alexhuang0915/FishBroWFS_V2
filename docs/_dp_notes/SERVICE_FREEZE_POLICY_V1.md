# Service Freeze Policy V1 (Backend + Worker)

## Goal
War Room must never show false DOWN states due to missing/late pidfile/heartbeat.

## Contracts

### Backend
- `/health` returns HTTP 200 JSON `{"status":"ok"}`.
- `/worker/status` is stable and deterministic:
  - If worker is running, returns:
    - `alive: true`
    - `pid: <int>`
    - `last_heartbeat_age_sec: <float|int>`
    - `reason: "ok"` (or empty)
  - If worker not running, returns:
    - `alive: false`
    - `reason` is explicit and actionable (e.g. "pidfile missing" or "stale heartbeat")

### Worker Liveness Publication
Worker must publish liveness immediately on startup:
- PIDFILE must be created within 1 second of process start.
- HEARTBEAT must be updated at least once within 2 seconds of start and then periodically.
- PIDFILE location is governed (single source of truth), and must match backend expectations.

### Operational
- `make backend`, `make worker`, `make status`, `make war` must work deterministically.
- `make war` Ctrl+C must stop backend + worker and free port 8000 (no zombies).

## Acceptance
- `make backend` + `make worker` then 3 consecutive `make status` calls show alive:true.
- CI smoke test enforces this contract.