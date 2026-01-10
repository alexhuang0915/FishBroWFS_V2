"""Worker spawn policy - enforce governance to stop uncontrolled worker spawning.

Contract:
Worker can only be started when all are true:
- Not in pytest context (PYTEST_CURRENT_TEST absent) OR explicit override FISHBRO_ALLOW_SPAWN_IN_TESTS=1
- DB path is not under /tmp unless explicit override FISHBRO_ALLOW_TMP_DB=1
- pidfile locking ensures no duplicate spawn for same db_path (handled elsewhere)
- pidfile must be validated: process exists AND cmdline matches worker_main and db_path
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def can_spawn_worker(db_path: Path) -> tuple[bool, str]:
    """Return (allowed, reason).

    Rules:
    1. If PYTEST_CURRENT_TEST is set and FISHBRO_ALLOW_SPAWN_IN_TESTS != "1":
        deny with message about pytest.
    2. If db_path is under system temporary directory and FISHBRO_ALLOW_TMP_DB != "1":
        deny with message about temporary directory.
    3. Otherwise allow.
    """
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("FISHBRO_ALLOW_SPAWN_IN_TESTS") != "1":
        return False, "Worker spawn disabled under pytest (set FISHBRO_ALLOW_SPAWN_IN_TESTS=1 to override)"

    rp = db_path.expanduser().resolve()
    tmp_dir = tempfile.gettempdir()
    if str(rp).startswith(tmp_dir + "/") and os.getenv("FISHBRO_ALLOW_TMP_DB") != "1":
        return False, f"Refusing to spawn worker for {tmp_dir} db_path (set FISHBRO_ALLOW_TMP_DB=1 to override)"

    return True, "ok"


def validate_pidfile(pidfile: Path, expected_db_path: Path) -> tuple[bool, str]:
    """Validate pidfile points to a live worker process with matching db_path.

    Returns (is_valid, reason).
    If valid, the worker is considered alive and no new spawn needed.
    If invalid (stale or mismatched), caller should remove pidfile and spawn.
    """
    if not pidfile.exists():
        return False, "pidfile missing"

    try:
        pid = int(pidfile.read_text().strip())
    except (ValueError, OSError):
        return False, "pidfile corrupted"

    # Check if process exists
    try:
        os.kill(pid, 0)
    except OSError:
        return False, "process dead"

    # On Linux, read cmdline from /proc/{pid}/cmdline
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if cmdline_path.exists():
        try:
            cmdline_bytes = cmdline_path.read_bytes()
            # Split by null bytes, decode
            parts = [p.decode("utf-8", errors="replace") for p in cmdline_bytes.split(b"\x00") if p]
            cmdline = " ".join(parts)
        except Exception:
            # If we cannot read cmdline, treat as unverifiable but assume alive
            return True, "process alive (cmdline unverifiable)"
    else:
        # Fallback for non-Linux (or permission issues)
        # We'll assume it's okay but log warning
        return True, "process alive (cmdline unverifiable)"

    # Verify cmdline contains worker_main and db_path
    if "control.worker_main" not in cmdline:
        return False, "process is not a worker_main"
    if str(expected_db_path) not in cmdline:
        return False, "process db_path mismatch"

    return True, "worker alive and matching"