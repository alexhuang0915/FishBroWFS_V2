#!/usr/bin/env python3
"""
FishBroWFS Supervisor - Safe stack management with pre-flight checks.

Provides deterministic startup/shutdown of backend+worker+GUI with comprehensive
dependency and port conflict detection.

Usage:
    python scripts/run_stack.py doctor    # Run pre-flight checks
    python scripts/run_stack.py run       # Start full stack
    python scripts/run_stack.py down      # Stop all fishbro processes
    python scripts/run_stack.py status    # Check health
    python scripts/run_stack.py ports     # Show port ownership
    python scripts/run_stack.py logs      # Tail logs

Exit codes:
    0: Success
    10: Missing dependency
    11: Port conflict
    12: Environment misconfiguration
    13: Health check failure
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Required modules with descriptive names
REQUIRED_MODULES = {
    "psutil": "Process & port inspection",
    "requests": "HTTP health checks",
    "uvicorn": "Backend server",
    "fastapi": "Backend API",
    "nicegui": "UI runtime",
}

# Default configuration
BACKEND_HOST = os.environ.get("FISHBRO_BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("FISHBRO_BACKEND_PORT", "8000"))
GUI_HOST = os.environ.get("FISHBRO_GUI_HOST", "0.0.0.0")
GUI_PORT = int(os.environ.get("FISHBRO_GUI_PORT", "8080"))

# Paths
REPO_ROOT = Path(__file__).parent.parent
PID_FILE = REPO_ROOT / "outputs" / "_dp_evidence" / "ops_pids.json"
BACKEND_LOG = Path("/tmp/fishbro_backend.log")
WORKER_LOG = Path("/tmp/fishbro_worker.log")
GUI_LOG = Path("/tmp/fishbro_gui.log")

# Global state
children = []  # List of Popen objects for cleanup


def check_dependencies() -> None:
    """Check all required modules are importable."""
    missing = []
    for module, description in REQUIRED_MODULES.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Action: pip install -r requirements.txt")
        sys.exit(10)


def get_port_owner(port: int) -> Optional[Tuple[int, str]]:
    """Return (pid, cmdline) of process listening on port, or None if free."""
    try:
        import psutil
    except ImportError:
        return None
    
    for conn in psutil.net_connections(kind='inet'):
        if conn.laddr.port == port and conn.status == 'LISTEN':
            try:
                proc = psutil.Process(conn.pid)
                cmdline = ' '.join(proc.cmdline())
                return (conn.pid, cmdline)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return (conn.pid, "unknown")
    return None


def is_fishbro_process(cmdline: str) -> bool:
    """Determine if process is owned by fishbro repo."""
    repo_indicators = [
        str(REPO_ROOT),
        "FishBroWFS_V2",
        "control.api",
        "main.py",
        "uvicorn control.api:app",
        "control.worker_main",
    ]
    return any(indicator in cmdline for indicator in repo_indicators)


def check_ports() -> None:
    """Check backend and GUI ports, fail if occupied by non-fishbro."""
    backend_owner = get_port_owner(BACKEND_PORT)
    gui_owner = get_port_owner(GUI_PORT)
    
    errors = []
    
    if backend_owner:
        pid, cmdline = backend_owner
        if not is_fishbro_process(cmdline):
            errors.append(f"Port {BACKEND_PORT} is used by PID={pid} cmd={cmdline[:100]}")
    
    if gui_owner:
        pid, cmdline = gui_owner
        if not is_fishbro_process(cmdline):
            errors.append(f"Port {GUI_PORT} is used by PID={pid} cmd={cmdline[:100]}")
    
    if errors:
        print("PORT_CONFLICT: " + "; ".join(errors))
        print("Action: Run 'make down' (if fishbro) or stop that program.")
        sys.exit(11)


def check_health() -> None:
    """Check health of already-running fishbro components."""
    try:
        import requests
    except ImportError:
        return  # Skip health checks if requests not available
    
    # Check backend
    try:
        resp = requests.get(f"http://{BACKEND_HOST}:{BACKEND_PORT}/health", timeout=2)
        if resp.status_code != 200:
            print(f"HEALTH_FAILURE: Backend unhealthy (HTTP {resp.status_code})")
            sys.exit(13)
    except requests.RequestException:
        pass  # Backend not running, that's OK
    
    # Check GUI if port is occupied by fishbro
    gui_owner = get_port_owner(GUI_PORT)
    if gui_owner and is_fishbro_process(gui_owner[1]):
        try:
            resp = requests.get(f"http://{BACKEND_HOST}:{GUI_PORT}/health", timeout=2)
            if resp.status_code != 200:
                print(f"HEALTH_FAILURE: GUI unhealthy (HTTP {resp.status_code})")
                sys.exit(13)
        except requests.RequestException:
            print("HEALTH_FAILURE: GUI running but health endpoint unreachable")
            sys.exit(13)


def doctor() -> None:
    """Run all pre-flight checks without spawning anything."""
    print("==> Running pre-flight checks (doctor)...")
    
    # Test hook for simulating missing dependencies
    force_missing = os.environ.get("FISHBRO_SUPERVISOR_FORCE_MISSING")
    if force_missing:
        print(f"TEST: Simulating missing dependency: {force_missing}")
        print(f"Missing dependencies: {force_missing}")
        print("Action: pip install -r requirements.txt")
        sys.exit(10)
    
    check_dependencies()
    check_ports()
    check_health()
    
    print("✓ All checks passed. System ready to start.")


def spawn_backend() -> subprocess.Popen:
    """Start backend server."""
    cmd = [
        sys.executable, "-m", "uvicorn", "control.api:app",
        "--host", BACKEND_HOST,
        "--port", str(BACKEND_PORT),
        "--reload"
    ]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    
    with open(BACKEND_LOG, "a") as f:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
    
    print(f"Backend started (PID: {proc.pid}, log: {BACKEND_LOG})")
    return proc


def spawn_worker() -> subprocess.Popen:
    """Start worker daemon."""
    jobs_db = REPO_ROOT / "outputs" / "jobs.db"
    cmd = [
        sys.executable, "-m", "control.worker_main",
        str(jobs_db)
    ]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    
    with open(WORKER_LOG, "a") as f:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
    
    print(f"Worker started (PID: {proc.pid}, log: {WORKER_LOG})")
    return proc


def spawn_gui() -> subprocess.Popen:
    """Start GUI."""
    cmd = [
        sys.executable, "-B", str(REPO_ROOT / "main.py")
    ]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    
    with open(GUI_LOG, "a") as f:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
    
    print(f"GUI started (PID: {proc.pid}, log: {GUI_LOG})")
    return proc


def save_pids(pids: Dict[str, int]) -> None:
    """Save child PIDs to file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, "w") as f:
        json.dump(pids, f, indent=2)


def load_pids() -> Dict[str, int]:
    """Load child PIDs from file."""
    if PID_FILE.exists():
        with open(PID_FILE, "r") as f:
            return json.load(f)
    return {}


def cleanup_children() -> None:
    """Terminate all child processes."""
    global children
    
    # First try graceful termination
    for proc in children:
        if proc.poll() is None:  # Still running
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
    
    # Wait a bit
    time.sleep(1)
    
    # Force kill any remaining
    for proc in children:
        if proc.poll() is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    
    children.clear()


def signal_handler(signum, frame) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n==> Received interrupt, shutting down...")
    cleanup_children()
    if PID_FILE.exists():
        PID_FILE.unlink()
    sys.exit(130)


def run_command(args) -> None:
    """Execute the run command."""
    global children
    
    # Run doctor first
    doctor()
    
    print("==> Starting full stack...")
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    pids = {}
    
    # Spawn components based on flags
    if not args.no_backend:
        backend_proc = spawn_backend()
        children.append(backend_proc)
        pids["backend"] = backend_proc.pid
        time.sleep(2)  # Give backend time to start
    
    if not args.no_worker:
        worker_proc = spawn_worker()
        children.append(worker_proc)
        pids["worker"] = worker_proc.pid
        time.sleep(1)
    
    if not args.no_gui:
        gui_proc = spawn_gui()
        children.append(gui_proc)
        pids["gui"] = gui_proc.pid
    
    # Save PIDs
    save_pids(pids)
    
    print(f"\n==> Stack started. PIDs saved to {PID_FILE}")
    print(f"    Backend: http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"    GUI:     http://{GUI_HOST}:{GUI_PORT}")
    print(f"    Logs:    /tmp/fishbro_*.log")
    print("\nPress Ctrl+C to stop all components.")
    
    # Wait for all children
    try:
        for proc in children:
            proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_children()
        if PID_FILE.exists():
            PID_FILE.unlink()


def down_command() -> None:
    """Stop all fishbro processes."""
    print("==> Stopping all fishbro processes...")
    
    # Try PID-based cleanup first
    pids = load_pids()
    killed_via_pid = False
    
    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to {name} (PID: {pid})")
            killed_via_pid = True
        except ProcessLookupError:
            pass
    
    if killed_via_pid:
        time.sleep(1)
    
    # Fallback to port-based cleanup
    import psutil
    
    for port in [BACKEND_PORT, GUI_PORT]:
        owner = get_port_owner(port)
        if owner and is_fishbro_process(owner[1]):
            try:
                os.kill(owner[0], signal.SIGKILL)
                print(f"Killed process on port {port} (PID: {owner[0]})")
            except ProcessLookupError:
                pass
    
    # Clean up PID file
    if PID_FILE.exists():
        PID_FILE.unlink()
    
    print("==> Done.")


def status_command() -> None:
    """Check health status."""
    try:
        import requests
    except ImportError:
        print("ERROR: requests module required for status checks")
        sys.exit(10)
    
    print("==> Checking stack health...")
    
    # Backend health
    try:
        resp = requests.get(f"http://{BACKEND_HOST}:{BACKEND_PORT}/health", timeout=2)
        if resp.status_code == 200:
            print(f"✓ Backend: healthy (HTTP 200)")
        else:
            print(f"✗ Backend: unhealthy (HTTP {resp.status_code})")
    except requests.RequestException:
        print("✗ Backend: not responding")
    
    # Worker status
    try:
        resp = requests.get(f"http://{BACKEND_HOST}:{BACKEND_PORT}/worker/status", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("alive"):
                print(f"✓ Worker: alive")
            else:
                print(f"✗ Worker: reported not alive")
        else:
            print(f"✗ Worker: status endpoint returned HTTP {resp.status_code}")
    except requests.RequestException:
        print("✗ Worker: status endpoint not available")
    
    # GUI health
    try:
        resp = requests.get(f"http://{BACKEND_HOST}:{GUI_PORT}/health", timeout=2)
        if resp.status_code == 200:
            print(f"✓ GUI: healthy (HTTP 200)")
        else:
            print(f"✗ GUI: unhealthy (HTTP {resp.status_code})")
    except requests.RequestException:
        print("✗ GUI: not responding or not running")
    
    # Port status
    backend_owner = get_port_owner(BACKEND_PORT)
    gui_owner = get_port_owner(GUI_PORT)
    
    print(f"\nPort {BACKEND_PORT}: {'occupied' if backend_owner else 'free'}")
    if backend_owner:
        print(f"  PID: {backend_owner[0]}, Cmd: {backend_owner[1][:80]}...")
    
    print(f"Port {GUI_PORT}: {'occupied' if gui_owner else 'free'}")
    if gui_owner:
        print(f"  PID: {gui_owner[0]}, Cmd: {gui_owner[1][:80]}...")


def ports_command() -> None:
    """Show port ownership."""
    print(f"==> Port ownership (backend: {BACKEND_PORT}, GUI: {GUI_PORT})")
    
    backend_owner = get_port_owner(BACKEND_PORT)
    gui_owner = get_port_owner(GUI_PORT)
    
    print(f"\nPort {BACKEND_PORT}:")
    if backend_owner:
        pid, cmdline = backend_owner
        owner_type = "fishbro" if is_fishbro_process(cmdline) else "external"
        print(f"  PID: {pid}")
        print(f"  Type: {owner_type}")
        print(f"  Cmd: {cmdline}")
    else:
        print("  Free")
    
    print(f"\nPort {GUI_PORT}:")
    if gui_owner:
        pid, cmdline = gui_owner
        owner_type = "fishbro" if is_fishbro_process(cmdline) else "external"
        print(f"  PID: {pid}")
        print(f"  Type: {owner_type}")
        print(f"  Cmd: {cmdline}")
    else:
        print("  Free")


def logs_command() -> None:
    """Show logs."""
    print("==> Showing last 20 lines of each log:")
    
    for log_path, name in [
        (BACKEND_LOG, "Backend"),
        (WORKER_LOG, "Worker"),
        (GUI_LOG, "GUI"),
    ]:
        print(f"\n--- {name} log ({log_path}) ---")
        if log_path.exists():
            try:
                with open(log_path, "r") as f:
                    lines = f.readlines()
                    for line in lines[-20:]:
                        print(line.rstrip())
            except Exception as e:
                print(f"Error reading log: {e}")
        else:
            print("Log file does not exist")


def main() -> None:
    parser = argparse.ArgumentParser(description="FishBroWFS Supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # doctor command
    subparsers.add_parser("doctor", help="Run pre-flight checks")
    
    # run command
    run_parser = subparsers.add_parser("run", help="Start full stack")
    run_parser.add_argument("--no-backend", action="store_true", help="Skip backend")
    run_parser.add_argument("--no-worker", action="store_true", help="Skip worker")
    run_parser.add_argument("--no-gui", action="store_true", help="Skip GUI")
    
    # other commands
    subparsers.add_parser("down", help="Stop all fishbro processes")
    subparsers.add_parser("status", help="Check health status")
    subparsers.add_parser("ports", help="Show port ownership")
    subparsers.add_parser("logs", help="Show logs")
    
    args = parser.parse_args()
    
    if args.command == "doctor":
        doctor()
    elif args.command == "run":
        run_command(args)
    elif args.command == "down":
        down_command()
    elif args.command == "status":
        status_command()
    elif args.command == "ports":
        ports_command()
    elif args.command == "logs":
        logs_command()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()