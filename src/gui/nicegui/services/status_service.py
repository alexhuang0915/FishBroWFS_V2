"""Status service - centralized backend polling with caching and rate‑limited logging.

Invariants:
- Only this module performs periodic backend probes.
- Status is cached; other services must read the cache, not call backend directly.
- Logging is rate‑limited to avoid spam when backend is down.
- Polling starts exactly once per process.
"""

import logging
import os
import time
from typing import Dict, Any, Optional, NamedTuple
import requests

from nicegui import ui

logger = logging.getLogger(__name__)

# Configurable API base via environment variable
# Default to empty string (relative path) for same-origin requests
API_BASE = os.environ.get("FISHBRO_API_BASE", "").rstrip("/")

# -----------------------------------------------------------------------------
# Status snapshot
# -----------------------------------------------------------------------------

class StatusSnapshot(NamedTuple):
    """Immutable snapshot of backend/worker status."""
    backend_up: bool
    backend_error: Optional[str]
    backend_last_ok_ts: Optional[float]
    worker_up: bool
    worker_error: Optional[str]
    worker_last_ok_ts: Optional[float]
    last_check_ts: float


# -----------------------------------------------------------------------------
# System state classification
# -----------------------------------------------------------------------------

def _compute_state(snap: StatusSnapshot) -> str:
    """Return ONLINE, DEGRADED, or OFFLINE based on snapshot."""
    if not snap.backend_up:
        return "OFFLINE"
    if not snap.worker_up:
        return "DEGRADED"
    return "ONLINE"


def get_state() -> str:
    """Return current system state (ONLINE/DEGRADED/OFFLINE)."""
    snap = get_status()
    return _compute_state(snap)


def get_summary() -> str:
    """Return a short human-readable summary of the system state."""
    snap = get_status()
    state = _compute_state(snap)
    if state == "ONLINE":
        return "System fully operational"
    elif state == "DEGRADED":
        return f"Backend up, worker down: {snap.worker_error or 'unknown error'}"
    else:  # OFFLINE
        hint = "Start backend via 'make war' (port 8000)"
        return f"Backend unreachable: {snap.backend_error or 'connection failed'} | Hint: {hint}"
# -----------------------------------------------------------------------------
# Module‑global state
# -----------------------------------------------------------------------------

# Cache of the latest status
_status_cache: Optional[StatusSnapshot] = None

# Polling control
_polling_started: bool = False
_polling_timer: Optional[Any] = None

# Rate‑limiting state
_last_warning_ts: Dict[str, float] = {}  # key: "backend", "worker"
_last_backend_up: Optional[bool] = None
_last_worker_up: Optional[bool] = None

# Polling interval (seconds)
POLL_INTERVAL = 10.0

# Cooldown for warning logs (seconds)
WARNING_COOLDOWN = 60.0


# -----------------------------------------------------------------------------
# Low‑level probes (private)
# -----------------------------------------------------------------------------

def _check_backend() -> Dict[str, Any]:
    """Raw backend health check (no caching, no rate limiting)."""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=2)
        resp.raise_for_status()
        # Also fetch identity for extra info
        ident_resp = requests.get(f"{API_BASE}/__identity", timeout=2)
        identity = ident_resp.json() if ident_resp.status_code == 200 else {}
        return {"online": True, "identity": identity}
    except Exception as e:
        return {"online": False, "error": str(e)}


def _check_worker() -> Dict[str, Any]:
    """Raw worker status check (no caching, no rate limiting)."""
    try:
        resp = requests.get(f"{API_BASE}/worker/status", timeout=2)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"alive": False, "error": str(e)}


# -----------------------------------------------------------------------------
# Rate‑limited logging
# -----------------------------------------------------------------------------

def _should_log_warning(probe: str, now: float) -> bool:
    """Return True if a warning log is allowed (cooldown not active)."""
    last = _last_warning_ts.get(probe, 0.0)
    return now - last >= WARNING_COOLDOWN


def _update_warning_ts(probe: str, now: float) -> None:
    """Record that a warning was just logged."""
    _last_warning_ts[probe] = now


def _log_status_transition(
    probe: str,
    old_up: Optional[bool],
    new_up: bool,
    error: Optional[str],
    now: float,
) -> None:
    """Log UP→DOWN, DOWN→UP transitions appropriately."""
    if old_up is None:
        # First poll
        if new_up:
            logger.info(f"{probe.capitalize()} is UP")
        else:
            hint = "Start backend via 'make war' (port 8000)" if probe == "backend" else "Start worker via 'make worker'"
            logger.warning(f"{probe.capitalize()} is DOWN: {error} | Hint: {hint}")
            _update_warning_ts(probe, now)
        return

    if old_up and not new_up:
        if _should_log_warning(probe, now):
            hint = "Start backend via 'make war' (port 8000)" if probe == "backend" else "Start worker via 'make worker'"
            logger.warning(f"{probe.capitalize()} DOWN: {error} | Hint: {hint}")
            _update_warning_ts(probe, now)
        else:
            logger.debug(f"{probe.capitalize()} still down: {error}")
    elif not old_up and new_up:
        logger.info(f"{probe.capitalize()} recovered, now UP")
        # Reset cooldown so next DOWN will log
        _last_warning_ts.pop(probe, None)
    # UP→UP or DOWN→DOWN: no log


# -----------------------------------------------------------------------------
# Core status update
# -----------------------------------------------------------------------------

def _update_status() -> None:
    """Perform a fresh probe, update cache, and log transitions."""
    global _status_cache, _last_backend_up, _last_worker_up
    now = time.time()

    backend_result = _check_backend()
    worker_result = _check_worker()

    backend_up = backend_result["online"]
    backend_error = backend_result.get("error")
    worker_up = worker_result.get("alive", False)
    worker_error = worker_result.get("error")

    # Log transitions
    _log_status_transition("backend", _last_backend_up, backend_up, backend_error, now)
    _log_status_transition("worker", _last_worker_up, worker_up, worker_error, now)

    # Update cache
    _status_cache = StatusSnapshot(
        backend_up=backend_up,
        backend_error=backend_error,
        backend_last_ok_ts=now if backend_up else None,
        worker_up=worker_up,
        worker_error=worker_error,
        worker_last_ok_ts=now if worker_up else None,
        last_check_ts=now,
    )
    _last_backend_up = backend_up
    _last_worker_up = worker_up


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def get_status() -> StatusSnapshot:
    """Return the latest cached status snapshot.
    
    If no status has been fetched yet, perform a synchronous probe.
    """
    if _status_cache is None:
        _update_status()
    return _status_cache


def get_system_status() -> Dict[str, Any]:
    """Legacy adapter: return dict compatible with previous dashboard."""
    snap = get_status()
    backend_hint = "Start backend via 'make war' (port 8000)" if not snap.backend_up else None
    worker_hint = "Start worker via 'make worker'" if not snap.worker_up else None
    return {
        "backend": {
            "online": snap.backend_up,
            "error": snap.backend_error,
            "hint": backend_hint,
        },
        "worker": {
            "alive": snap.worker_up,
            "error": snap.worker_error,
            "hint": worker_hint,
        },
        "overall": snap.backend_up and snap.worker_up,
    }


def get_forensics_snapshot() -> dict:
    """
    Forensics‑safe, stable snapshot of status service.
    Must not raise; must always return the same keys.
    """
    state = get_state()  # "ONLINE"|"DEGRADED"|"OFFLINE"
    summary = get_summary()
    snap = get_status()
    return {
        "state": state,
        "summary": summary,
        "backend_up": bool(snap.backend_up),
        "worker_up": bool(snap.worker_up),
        "backend_error": snap.backend_error,
        "worker_error": snap.worker_error,
        "last_checked_ts": snap.last_check_ts,
        "polling_started": bool(_polling_started),
        "poll_interval_s": float(POLL_INTERVAL),
    }


def start_polling(interval: float = POLL_INTERVAL) -> None:
    """Start periodic status polling (idempotent).
    
    Must be called after NiceGUI UI is ready (ui.run() context).
    """
    global _polling_started, _polling_timer
    logger.debug(f"start_polling called, _polling_started={_polling_started}")
    if _polling_started:
        logger.debug("Polling already started, skipping")
        return

    logger.info(f"Starting status polling (pid={os.getpid()}, interval {interval}s)")
    _polling_started = True
    logger.debug(f"Set _polling_started=True")
    # Initial update immediately
    _update_status()
    # Periodic updates via NiceGUI timer
    _polling_timer = ui.timer(
        interval=interval,
        callback=lambda: _update_status(),
    )


def stop_polling() -> None:
    """Stop polling (mainly for tests)."""
    global _polling_started, _polling_timer
    if _polling_timer is not None:
        _polling_timer.deactivate()
        _polling_timer = None
    _polling_started = False
    logger.debug("Polling stopped")


def force_refresh() -> None:
    """Force an immediate status update, bypassing rate‑limited logging cooldown."""
    global _last_backend_up, _last_worker_up
    # Temporarily reset transition state to ensure logs appear
    _last_backend_up = None
    _last_worker_up = None
    _update_status()


# -----------------------------------------------------------------------------
# Backward compatibility (deprecated)
# -----------------------------------------------------------------------------

def check_backend_status() -> Dict[str, Any]:
    """Deprecated: raw backend check; use get_status() instead."""
    return _check_backend()


def check_worker_status() -> Dict[str, Any]:
    """Deprecated: raw worker check; use get_status() instead."""
    return _check_worker()