#!/usr/bin/env python3
"""
Kill stray worker processes and clean up stale pidfiles.

Phase B5 of Operation Iron Broom – Worker Spawn Governance.
"""

import os
import sys
import signal
import time
from pathlib import Path

# Add src to path to import internal modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from control.worker_spawn_policy import validate_pidfile


def find_pidfiles(root_dir: Path, pattern="*.pid"):
    """Yield all .pid files under root_dir recursively."""
    return root_dir.rglob(pattern)


def kill_process(pid: int, sig=signal.SIGTERM):
    """Send signal to process, ignoring errors if process already gone."""
    try:
        os.kill(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        print(f"  WARNING: No permission to kill PID {pid}")
        return False


def scan_and_kill_strays(root_dir: Path, dry_run=False):
    """
    Scan for pidfiles and stray worker processes, kill/clean as needed.
    Returns count of cleaned pidfiles and killed processes.
    """
    cleaned = 0
    killed = 0

    # 1. Scan pidfiles
    for pidfile in find_pidfiles(root_dir):
        print(f"Checking pidfile: {pidfile}")
        # Determine db_path: same stem, .db extension
        db_path = pidfile.with_suffix(".db")
        if not db_path.exists():
            # DB may have been deleted; we'll still validate pidfile
            db_path = None

        valid, reason = validate_pidfile(pidfile, db_path)
        if valid:
            print(f"  OK: {reason}")
            continue

        print(f"  INVALID: {reason}")
        # Read pid from file
        try:
            pid = int(pidfile.read_text().strip())
        except (ValueError, OSError):
            pid = None

        if pid is not None:
            # Kill process if alive
            if dry_run:
                print(f"  DRY RUN: Would kill PID {pid}")
            else:
                print(f"  Killing PID {pid}...")
                if kill_process(pid):
                    killed += 1
                    time.sleep(0.1)  # give it a moment to exit
                else:
                    print(f"  Process {pid} already dead")

        # Delete pidfile
        if dry_run:
            print(f"  DRY RUN: Would delete {pidfile}")
        else:
            try:
                pidfile.unlink()
                cleaned += 1
                print(f"  Deleted pidfile")
            except OSError as e:
                print(f"  Failed to delete pidfile: {e}")

    # 2. Scan for stray worker processes (no pidfile)
    # We'll parse /proc directly (Linux only)
    if sys.platform != "linux":
        print("  Skipping stray process scan (non-Linux)")
        return cleaned, killed

    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline_path = entry / "cmdline"
        if not cmdline_path.exists():
            continue
        try:
            cmdline_bytes = cmdline_path.read_bytes()
            # cmdline is null-separated
            cmdline = cmdline_bytes.decode("utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue

        if "worker_main" not in cmdline:
            continue

        # Extract db_path from cmdline (simplistic)
        # cmdline format: python -m control.worker_main /path/to/db
        parts = cmdline.split("\x00")
        db_arg = None
        for part in parts:
            if part.endswith(".db"):
                db_arg = part
                break
        if db_arg is None:
            continue

        # Check if there's a pidfile for this db
        expected_pidfile = Path(db_arg).with_suffix(".pid")
        if expected_pidfile.exists():
            # Already have a pidfile; skip (should have been handled above)
            continue

        # Stray worker with no pidfile
        print(f"Found stray worker PID {pid} for DB {db_arg}")
        if dry_run:
            print(f"  DRY RUN: Would kill stray PID {pid}")
        else:
            if kill_process(pid):
                killed += 1
                print(f"  Killed stray worker")
            else:
                print(f"  Stray worker already dead")

    return cleaned, killed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kill stray worker processes and clean stale pidfiles.")
    parser.add_argument("--root", default=".", help="Root directory to search for pidfiles (default: current)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Error: root directory {root} does not exist")
        sys.exit(1)

    print(f"Scanning for stray workers under {root}")
    cleaned, killed = scan_and_kill_strays(root, dry_run=args.dry_run)
    print(f"\nSummary:")
    print(f"  Cleaned pidfiles: {cleaned}")
    print(f"  Killed processes: {killed}")
    if args.dry_run:
        print("  (dry run, no changes made)")

    if cleaned == 0 and killed == 0:
        print("No stray workers found.")


if __name__ == "__main__":
    main()