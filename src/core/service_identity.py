"""Service Identity Contract - SSOT for topology observability.

Provides a single canonical identity payload that any running service can return.
This payload uniquely proves:
- Who is serving the request (NiceGUI vs FastAPI)
- Which git commit / version it is
- Which DB path it uses (and why)
- Which PID / process commandline is serving
"""

from __future__ import annotations

import os
import sys
import platform
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel


class ServiceIdentity(BaseModel):
    """Pydantic model for service identity payload."""
    service_name: str
    pid: int
    ppid: int
    cmdline: str
    cwd: str
    python: str
    python_version: str
    platform: str
    repo_root: str
    git_commit: str
    build_time_utc: str
    env: Dict[str, Optional[str]]
    jobs_db_path: str
    jobs_db_parent: str
    worker_pidfile_path: str
    worker_log_path: str


_ALLOWED_ENV_KEYS = {
    "PYTHONPATH",
    "JOBS_DB_PATH",
    "FISHBRO_TESTING",
    "PYTEST_CURRENT_TEST",
    "TMPDIR",
    "TMP",
    "TEMP",
}


def _safe_cmdline() -> str:
    """Return process commandline as string, best-effort."""
    try:
        if Path("/proc/self/cmdline").exists():
            cmdline_bytes = Path("/proc/self/cmdline").read_bytes()
            # Split by null bytes, decode, filter empty
            parts = [p.decode("utf-8", errors="replace") for p in cmdline_bytes.split(b"\x00") if p]
            return " ".join(parts)
    except Exception:
        pass
    # Fallback for non-Linux or permission issues
    try:
        # Use psutil if available? Not required; keep simple.
        return " ".join(sys.argv)
    except Exception:
        return ""


def _safe_git_commit(repo_root: Path) -> str:
    """Extract git commit hash, best-effort, never raises."""
    try:
        head = repo_root / ".git" / "HEAD"
        if not head.exists():
            return "unknown"
        ref = head.read_text().strip()
        if ref.startswith("ref:"):
            ref_path = repo_root / ".git" / ref.split(" ", 1)[1].strip()
            if ref_path.exists():
                return ref_path.read_text().strip()
        # Already a commit hash
        return ref
    except Exception:
        return "unknown"


def _find_repo_root(start: Path) -> Path:
    """Climb up to find .git directory, else return start."""
    current = start.resolve()
    for _ in range(6):  # reasonable depth
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return start  # fallback


def get_service_identity(
    *, service_name: str, db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Return JSON-safe identity dict.

    Fields:
      - service_name: str (caller-defined, e.g. "nicegui", "control_api")
      - pid: int
      - ppid: int
      - cmdline: str (best-effort; if unavailable return "")
      - cwd: str
      - python: str (sys.executable)
      - python_version: str
      - platform: str
      - repo_root: str (best-effort)
      - git_commit: str ("unknown" allowed)
      - build_time_utc: str (ISO8601, generated at import time or on demand)
      - env: dict (filtered keys only)
      - jobs_db_path: str (resolved absolute if db_path provided; else "")
      - jobs_db_parent: str
      - worker_pidfile_path: str (db_path.parent/"worker.pid" if db_path provided else "")
      - worker_log_path: str (db_path.parent/"worker_process.log" if db_path provided else "")
    """
    now = datetime.now(timezone.utc).isoformat()
    cwd = Path.cwd()
    repo_root = _find_repo_root(cwd)

    env = {k: os.getenv(k) for k in _ALLOWED_ENV_KEYS if os.getenv(k) is not None}

    jobs_db_path = ""
    jobs_db_parent = ""
    pidfile = ""
    wlog = ""
    if db_path is not None:
        rp = db_path.expanduser().resolve()
        jobs_db_path = str(rp)
        jobs_db_parent = str(rp.parent)
        pidfile = str(rp.parent / "worker.pid")
        wlog = str(rp.parent / "worker_process.log")

    return {
        "service_name": service_name,
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "cmdline": _safe_cmdline(),
        "cwd": str(cwd),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "repo_root": str(repo_root),
        "git_commit": _safe_git_commit(repo_root),
        "build_time_utc": now,
        "env": env,
        "jobs_db_path": jobs_db_path,
        "jobs_db_parent": jobs_db_parent,
        "worker_pidfile_path": pidfile,
        "worker_log_path": wlog,
    }


if __name__ == "__main__":
    # Quick test when run directly
    ident = get_service_identity(service_name="test", db_path=None)
    print(json.dumps(ident, indent=2, sort_keys=True))