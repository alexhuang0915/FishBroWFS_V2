#!/usr/bin/env python3
"""
Integration Test Harness for FishBroWFS_V2

Starts dashboard, runs integration tests, kills dashboard.
Outputs pytest summary directly.
"""

import os
import sys
import subprocess
import time
import signal
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def wait_for_dashboard(timeout=20):
    """Wait for dashboard to become healthy."""
    base_url = "http://localhost:8080"
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{base_url}/health", timeout=2)
            if resp.status_code == 200:
                print(f"[INFO] Dashboard healthy at {base_url}")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    print(f"[WARN] Dashboard not ready after {timeout}s")
    return False


def main():
    print("=" * 80)
    print("FishBroWFS_V2 Integration Test Harness")
    print("=" * 80)
    print(f"Project root: {project_root}")
    print()

    # Step 1: Start dashboard
    print("[1] Starting dashboard...")
    dashboard_proc = subprocess.Popen(
        ["make", "dashboard"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,  # Create process group for cleanup
    )
    
    # Give it a moment to start
    time.sleep(3)
    
    # Step 2: Wait for health
    print("[2] Waiting for dashboard health...")
    if not wait_for_dashboard():
        print("[ERROR] Dashboard failed to start")
        os.killpg(os.getpgid(dashboard_proc.pid), signal.SIGTERM)
        sys.exit(1)
    
    # Step 3: Set environment
    env = os.environ.copy()
    env["FISHBRO_RUN_INTEGRATION"] = "1"
    env["FISHBRO_BASE_URL"] = "http://localhost:8080"
    
    # Step 4: Run pytest
    print("[3] Running integration tests...")
    print("-" * 80)
    
    rc = subprocess.call(
        [sys.executable, "-m", "pytest", "-q", "tests/legacy"],
        cwd=project_root,
        env=env,
    )
    
    print("-" * 80)
    
    # Step 5: Kill dashboard
    print("[4] Stopping dashboard...")
    try:
        os.killpg(os.getpgid(dashboard_proc.pid), signal.SIGTERM)
        dashboard_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(dashboard_proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    
    print(f"[5] Exit code: {rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()