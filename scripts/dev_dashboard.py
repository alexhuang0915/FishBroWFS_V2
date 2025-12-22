
#!/usr/bin/env python3
"""
Local Dev Launcher for FishBroWFS V2

One‑terminal launcher that starts three processes:
1. Control API server
2. Worker daemon
3. NiceGUI dashboard

Usage:
    python scripts/dev_dashboard.py
    # or
    make dashboard  (after TASK 7)

Constitutional principles:
- UI must be honest: no fake data, no fallback mocks
- UI only renders artifacts from Control API
- All three processes must be running for full functionality
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path
from typing import List, Optional

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

# Process handles
processes: List[subprocess.Popen] = []


def start_control_api() -> subprocess.Popen:
    """Start Control API server using uvicorn."""
    print("🚀 Starting Control API server (uvicorn)...")
    cmd = [
        sys.executable, "-m", "uvicorn",
        "FishBroWFS_V2.control.api:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["JOBS_DB_PATH"] = str(PROJECT_ROOT / "outputs/jobs.db")
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    # Start a thread to stream output
    threading.Thread(
        target=stream_output,
        args=(proc, "Control API"),
        daemon=True
    ).start()
    return proc


def start_worker_daemon() -> subprocess.Popen:
    """Start Worker daemon."""
    print("👷 Starting Worker daemon...")
    cmd = [
        sys.executable, "-m", "FishBroWFS_V2.control.worker_main",
        "--outputs-root", "outputs",
        "--poll-interval", "5",
        "--verbose"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    threading.Thread(
        target=stream_output,
        args=(proc, "Worker"),
        daemon=True
    ).start()
    return proc


def start_nicegui_dashboard() -> subprocess.Popen:
    """Start NiceGUI dashboard."""
    print("📊 Starting NiceGUI dashboard...")
    # 使用 module 執行，不要傳遞參數（參數已在 app.py 中設定）
    cmd = [
        sys.executable, "-m", "FishBroWFS_V2.gui.nicegui.app"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["CONTROL_API_BASE"] = "http://127.0.0.1:8000"
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    threading.Thread(
        target=stream_output,
        args=(proc, "NiceGUI"),
        daemon=True
    ).start()
    return proc


def stream_output(proc: subprocess.Popen, label: str) -> None:
    """Stream process output to console with label prefix."""
    if proc.stdout is None:
        return
    for line in iter(proc.stdout.readline, ''):
        if line:
            print(f"[{label}] {line.rstrip()}")
        else:
            break


def wait_for_url(url: str, timeout: int = 30) -> bool:
    """Wait for a URL to become reachable."""
    import socket
    import urllib.parse
    from urllib.request import urlopen
    from urllib.error import URLError
    
    parsed = urllib.parse.urlparse(url)
    host, port = parsed.hostname, parsed.port or (80 if parsed.scheme == "http" else 443)
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            # First check TCP connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                # Then check HTTP response
                try:
                    resp = urlopen(f"{url}/health", timeout=2)
                    if resp.getcode() == 200:
                        return True
                except (URLError, ConnectionError):
                    pass
        except (socket.error, ConnectionError):
            pass
        time.sleep(1)
    return False


def ensure_registries_primed(api_base: str = "http://127.0.0.1:8000", timeout: int = 10) -> bool:
    """
    Ensure registries are primed (loaded into cache).
    
    Checks /meta/datasets endpoint:
    - If 200: registries are already primed
    - If 503: registries not primed, call /meta/prime to load them
    - Returns True if primed successfully, False otherwise
    """
    import json
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    
    datasets_url = f"{api_base}/meta/datasets"
    prime_url = f"{api_base}/meta/prime"
    
    print("🔍 Checking registry status...")
    
    # First check if datasets endpoint returns 200
    try:
        req = Request(datasets_url)
        resp = urlopen(req, timeout=5)
        if resp.getcode() == 200:
            print("✅ Registries already primed")
            return True
    except HTTPError as e:
        if e.code == 503:
            print("⚠️  Registries not primed (503), attempting to prime...")
        else:
            print(f"⚠️  Unexpected error checking registries: {e.code} {e.reason}")
            return False
    except (URLError, ConnectionError) as e:
        print(f"⚠️  Cannot connect to Control API: {e}")
        return False
    
    # Try to prime registries
    try:
        print("🔄 Priming registries via POST /meta/prime...")
        prime_req = Request(
            prime_url,
            method="POST",
            headers={"Content-Type": "application/json"}
        )
        resp = urlopen(prime_req, timeout=10)
        if resp.getcode() == 200:
            result = json.loads(resp.read().decode())
            if result.get("success"):
                print("✅ Registries primed successfully")
                return True
            else:
                print(f"⚠️  Registry priming partially failed: {result}")
                # Even if partial, we might have some registries loaded
                return True
        else:
            print(f"⚠️  Prime endpoint returned {resp.getcode()}")
            return False
    except HTTPError as e:
        print(f"⚠️  Failed to prime registries: {e.code} {e.reason}")
        return False
    except (URLError, ConnectionError) as e:
        print(f"⚠️  Cannot connect to Control API for priming: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Unexpected error during priming: {e}")
        return False


def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully shutdown all processes."""
    print("\n🛑 Shutting down all processes...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    # Wait a bit then kill if still alive
    time.sleep(2)
    for proc in processes:
        if proc.poll() is None:
            proc.kill()
    print("✅ All processes stopped.")
    sys.exit(0)


def main():
    """Main launcher function."""
    print("=" * 60)
    print("FishBroWFS V2 - Local Dev Launcher")
    print("=" * 60)
    print("Constitutional principles:")
    print("• UI must be honest (no fake data, no fallback mocks)")
    print("• UI only renders artifacts from Control API")
    print("• All three processes must be running for full functionality")
    print("=" * 60)
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start processes
    try:
        # 1. Control API
        api_proc = start_control_api()
        processes.append(api_proc)
        
        # Wait for Control API to be ready
        print("⏳ Waiting for Control API to start...")
        if wait_for_url("http://127.0.0.1:8000"):
            print("✅ Control API is ready at http://127.0.0.1:8000")
        else:
            print("⚠️  Control API may not be fully ready, continuing anyway...")
        
        # Ensure registries are primed before starting NiceGUI
        print("🔍 Ensuring registries are primed...")
        if ensure_registries_primed():
            print("✅ Registries ready for UI")
        else:
            print("⚠️  Registry priming failed - UI may show 503 errors")
            print("   You can manually prime via: curl -X POST http://127.0.0.1:8000/meta/prime")
        
        # 2. Worker daemon
        worker_proc = start_worker_daemon()
        processes.append(worker_proc)
        time.sleep(2)  # Give worker a moment to initialize
        
        # 3. NiceGUI dashboard
        gui_proc = start_nicegui_dashboard()
        processes.append(gui_proc)
        
        # Wait for NiceGUI to be ready
        print("⏳ Waiting for NiceGUI dashboard to start...")
        if wait_for_url("http://127.0.0.1:8080"):
            print("✅ NiceGUI dashboard is ready at http://127.0.0.1:8080")
        else:
            print("⚠️  NiceGUI may not be fully ready, continuing anyway...")
        
        print("\n" + "=" * 60)
        print("🎉 All services started!")
        print("\nAccess points:")
        print("• NiceGUI Dashboard: http://127.0.0.1:8080")
        print("• Control API:       http://127.0.0.1:8000")
        print("• API Documentation: http://127.0.0.1:8000/docs")
        print("\nPress Ctrl+C to stop all services.")
        print("=" * 60)
        
        # Monitor processes
        while True:
            time.sleep(1)
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    labels = ["Control API", "Worker", "NiceGUI"]
                    print(f"❌ {labels[i]} process died with exit code {proc.returncode}")
                    # Restart logic could be added here
                    # For now, just exit
                    print("Exiting due to process failure...")
                    signal_handler(None, None)
                    return
    
    except Exception as e:
        print(f"❌ Launcher error: {e}")
        signal_handler(None, None)
        sys.exit(1)


if __name__ == "__main__":
    main()


