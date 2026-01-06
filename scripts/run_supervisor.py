#!/usr/bin/env python3
"""
Launch the FishBroWFS Supervisor (FastAPI backend) with minimal configuration.

This script is the ONLY subprocess call allowed from the desktop UI.
It starts the backend server (uvicorn) with the given host/port.

Usage:
    python scripts/run_supervisor.py [--host HOST] [--port PORT]

If no arguments are provided, defaults to 127.0.0.1:8000.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch Supervisor backend")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port to bind (default: 8000)")
    args = parser.parse_args()

    # Ensure PYTHONPATH includes src
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    # Build uvicorn command
    cmd = [
        sys.executable, "-m", "uvicorn", "control.api:app",
        "--host", args.host,
        "--port", str(args.port),
        "--reload",
    ]

    # Run supervisor in foreground (blocking)
    # The UI expects this script to block until the supervisor exits.
    try:
        subprocess.run(cmd, env=env, check=True)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Supervisor exited with error: {e}", file=sys.stderr)
        return e.returncode
    except KeyboardInterrupt:
        print("\nSupervisor stopped by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())