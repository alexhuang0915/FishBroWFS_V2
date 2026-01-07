# Makefile Audit Summary

**Date:** 2026-01-07  
**Auditor:** Qwen3 Coder  
**Repo:** FishBroWFS_V2  
**Makefile Version:** V3 War Room Edition

## Target Categories

### Product Targets (User-facing)
- `desktop`, `desktop-wayland`, `desktop-offscreen` – Launch Desktop UI (PySide6)
- `doctor` – Pre‑flight checks
- `down` – Stop all fishbro processes (now enhanced with supervisor PID cleanup)
- `status` – Check backend/worker health
- `logs` – Show logs
- `supervisor` – Start supervisor (backend API) in foreground
- `up` – Ensure supervisor healthy, then launch desktop UI
- `up-status` – Show supervisor PID and health status

### Stack/Control Plane Targets (Canonical Supervisor)
- `down-canonical` – Stop all fishbro processes via `scripts/run_stack.py down`
- `status-canonical` – Health check via `scripts/run_stack.py status`
- `ports-canonical` – Port ownership via `scripts/run_stack.py ports`
- `logs` – Uses `scripts/run_stack.py logs`
- `doctor` – Uses `scripts/run_stack.py doctor`

### Legacy/Dev Targets (Gated)
- `clean-cache`, `clean-caches`, `clean-caches-dry` – Supervisor job submission (CLEAN_CACHE)
- `generate-reports` – Supervisor job submission (GENERATE_REPORTS)
- `build-data` – Parameter‑required, fails with guidance
- `snapshot`, `api-snapshot` – Context/API snapshot generation
- `forensics`, `ui-forensics`, `autopass`, `render-probe`, `ui-contract` – UI testing/forensics
- `check`, `check-legacy`, `test`, `portfolio-gov-test`, `portfolio-gov-smoke` – Test suites

### Clean Targets
- `clean-all` – Remove Python caches and build artifacts
- `clean-snapshot` – Remove SNAPSHOT directory

## Bypass Analysis

- **No legacy `run_*.py` bypasses detected.** All stack management goes through `scripts/run_stack.py` (canonical supervisor control plane).
- **No direct calls to `scripts/run_phase*.py` or other legacy wrappers.**
- **Supervisor lifecycle:** New targets `supervisor`, `up`, `down`, `up-status` reuse `scripts/run_stack.py run --no-worker` for starting backend, ensuring consistency with existing control plane.
- **Desktop UI launch:** `desktop` target calls `scripts/desktop_launcher.py` directly (as per product architecture).

## Safety Gates

- **Phase Z guard:** Outputs top‑level allowlist (`_trash` allowed) used for supervisor PID/log files.
- **Idempotent health checks:** `make up` checks `http://127.0.0.1:8000/health` before spawning.
- **Graceful termination:** `make down` stops supervisor PID (if exists) before calling canonical down.
- **No weakening of existing gates:** All existing safety checks (doctor, port conflict, worker spawn policy) remain intact.

## Verdict: PASS

All mandatory patterns satisfied:
- `.rooignore` guard present (previous task)
- No unauthorized bypass of supervisor
- New targets integrate with canonical control plane
- Evidence directory created (`outputs/_dp_evidence/make_up/`)
- Hard gates (`make check`, `scripts/acceptance/run_final_acceptance.sh`) pending validation

**Next Steps:** Run `make check` and final acceptance script to confirm zero regressions.