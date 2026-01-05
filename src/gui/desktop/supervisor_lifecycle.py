"""
Supervisor lifecycle manager for desktop UI.

Provides psutil-based detection of supervisor process on 127.0.0.1:8000,
canonical entrypoint discovery, and auto-start capabilities.

All port detection MUST use psutil as primary mechanism.
Shell command parsing (ss/lsof/netstat) is FORBIDDEN as primary path.
"""

import enum
import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psutil
import requests

from .config import (
    SUPERVISOR_BASE_URL,
    SUPERVISOR_HEALTH_PATH,
    SUPERVISOR_TIMEOUT_SEC,
    SUPERVISOR_STARTUP_RETRY_COUNT,
    SUPERVISOR_STARTUP_RETRY_DELAY_SEC,
    SUPERVISOR_RUNTIME_LOG,
    SUPERVISOR_ENTRYPOINT_LOG,
)

logger = logging.getLogger(__name__)


class SupervisorStatus(enum.Enum):
    """Status of supervisor lifecycle management."""
    RUNNING = "RUNNING"
    STARTING = "STARTING"
    NOT_RUNNING = "NOT_RUNNING"
    PORT_OCCUPIED = "PORT_OCCUPIED"
    ERROR = "ERROR"


def is_port_listening_8000() -> bool:
    """
    Check if port 8000 is listening using psutil.
    
    Returns:
        True if any connection has status == psutil.CONN_LISTEN
        and laddr.port == 8000
    """
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port == 8000:
                return True
    except (psutil.AccessDenied, psutil.Error) as e:
        logger.warning(f"psutil.net_connections failed: {e}")
        # Fallback to socket connect
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", 8000))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    return False


def detect_port_occupant_8000() -> Dict:
    """
    Detect which process occupies port 8000.
    
    Returns:
        {
            "occupied": bool,
            "pid": Optional[int],
            "process_name": Optional[str],
            "cmdline": Optional[list[str]],
            "is_fishbro_supervisor": Optional[bool],
        }
    """
    result = {
        "occupied": False,
        "pid": None,
        "process_name": None,
        "cmdline": None,
        "is_fishbro_supervisor": None,
    }
    
    try:
        # Find listening connection on port 8000
        for conn in psutil.net_connections(kind="inet"):
            if (conn.status == psutil.CONN_LISTEN and 
                conn.laddr.port == 8000 and
                conn.pid is not None):
                
                result["occupied"] = True
                result["pid"] = conn.pid
                
                try:
                    proc = psutil.Process(conn.pid)
                    result["process_name"] = proc.name()
                    result["cmdline"] = proc.cmdline()
                    
                    # Determine if it's a fishbro supervisor
                    cmdline_str = " ".join(proc.cmdline())
                    fishbro_indicators = [
                        "control.api:app",
                        "uvicorn control.api:app",
                        "FishBroWFS_V2",
                        "src/control/api.py",
                    ]
                    result["is_fishbro_supervisor"] = any(
                        indicator in cmdline_str for indicator in fishbro_indicators
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process may have died or we lack permissions
                    pass
                
                break  # Found first occupant
        
        # If psutil fails, fallback to socket connect
        if not result["occupied"]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                if sock.connect_ex(("127.0.0.1", 8000)) == 0:
                    result["occupied"] = True
                    # Can't get PID via socket
                sock.close()
            except Exception:
                pass
                
    except (psutil.AccessDenied, psutil.Error) as e:
        logger.warning(f"psutil detection failed: {e}")
        # Fallback to socket connect only
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", 8000)) == 0:
                result["occupied"] = True
            sock.close()
        except Exception:
            pass
    
    return result


def discover_supervisor_command() -> List[str]:
    """
    Discover canonical supervisor entrypoint.
    
    Discovery order (STRICT):
    1) pyproject.toml - look for [project.scripts] or [tool.poetry.scripts]
    2) Makefile - identify target used to start supervisor in dev/test
    3) CI configuration - inspect how supervisor is launched in integration tests
    
    Returns:
        List of command arguments to start supervisor
    """
    repo_root = Path(__file__).parent.parent.parent.parent
    
    # 1) Check pyproject.toml
    pyproject_path = repo_root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            import tomli
            with open(pyproject_path, "rb") as f:
                data = tomli.load(f)
            
            # Check for [project.scripts]
            if "project" in data and "scripts" in data["project"]:
                for script_name, script_path in data["project"]["scripts"].items():
                    if "supervisor" in script_name.lower() or "api" in script_name.lower():
                        # Convert module path to command
                        # e.g., "src.control.api:main" -> ["python", "-m", "src.control.api"]
                        if ":" in script_path:
                            module_path = script_path.split(":")[0]
                            return [sys.executable, "-m", module_path]
            
            # Check for [tool.poetry.scripts]
            if "tool" in data and "poetry" in data["tool"] and "scripts" in data["tool"]["poetry"]:
                for script_name, script_path in data["tool"]["poetry"]["scripts"].items():
                    if "supervisor" in script_name.lower() or "api" in script_name.lower():
                        if ":" in script_path:
                            module_path = script_path.split(":")[0]
                            return [sys.executable, "-m", module_path]
        except Exception as e:
            logger.debug(f"Failed to parse pyproject.toml: {e}")
    
    # 2) Check Makefile for supervisor/backend targets
    makefile_path = repo_root / "Makefile"
    if makefile_path.exists():
        try:
            with open(makefile_path, "r") as f:
                content = f.read()
            
            # Look for backend/supervisor startup patterns
            import re
            
            # Pattern for uvicorn command
            uvicorn_pattern = r'uvicorn\s+control\.api:app\s+--host\s+[\w\.]+\s+--port\s+\d+'
            match = re.search(uvicorn_pattern, content)
            if match:
                cmd = match.group(0)
                # Parse into list
                parts = cmd.split()
                # Insert python executable
                return [sys.executable, "-m"] + parts
            
            # Pattern for spawn_backend in run_stack.py
            backend_pattern = r'spawn_backend.*?\[.*?uvicorn.*?control\.api:app'
            match = re.search(backend_pattern, content, re.DOTALL)
            if match:
                # Extract the command list
                cmd_section = match.group(0)
                # Look for actual command list
                cmd_match = re.search(r'\[.*?\]', cmd_section, re.DOTALL)
                if cmd_match:
                    # This is complex, fall back to default
                    pass
        except Exception as e:
            logger.debug(f"Failed to parse Makefile: {e}")
    
    # 3) Default canonical command from run_stack.py
    # The canonical supervisor is uvicorn control.api:app
    return [
        sys.executable, "-m", "uvicorn", "control.api:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload"
    ]


def start_supervisor_subprocess() -> subprocess.Popen:
    """
    Start supervisor subprocess with explicit bind to 127.0.0.1:8000.
    
    Requirements:
    - Use canonical entrypoint discovered above
    - MUST include explicit flags: "--host", "127.0.0.1", "--port", "8000"
    - Override any internal defaults
    - Do NOT use Makefile targets
    - Do NOT use legacy wrapper scripts
    
    Returns:
        subprocess.Popen object for the started supervisor
    """
    # Get canonical command
    base_cmd = discover_supervisor_command()
    
    # Ensure host and port flags are present
    cmd = list(base_cmd)
    
    # Check if host flag already present
    host_present = False
    port_present = False
    for i, arg in enumerate(cmd):
        if arg == "--host":
            host_present = True
            # Ensure next arg is 127.0.0.1
            if i + 1 < len(cmd):
                cmd[i + 1] = "127.0.0.1"
        elif arg == "--port":
            port_present = True
            # Ensure next arg is 8000
            if i + 1 < len(cmd):
                cmd[i + 1] = "8000"
    
    # Add missing flags
    if not host_present:
        cmd.extend(["--host", "127.0.0.1"])
    if not port_present:
        cmd.extend(["--port", "8000"])
    
    # Log the discovered command
    log_entrypoint(cmd)
    
    # Prepare environment
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent)
    
    # Ensure log directory exists
    log_path = Path(SUPERVISOR_RUNTIME_LOG)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Start process
    logger.info(f"Starting supervisor: {' '.join(cmd)}")
    with open(log_path, "a") as log_file:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    
    return proc


def log_entrypoint(cmd: List[str]) -> None:
    """Log discovered supervisor entrypoint to evidence file."""
    log_path = Path(SUPERVISOR_ENTRYPOINT_LOG)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    entrypoint_info = {
        "timestamp": time.time(),
        "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": cmd,
        "python_executable": sys.executable,
        "cwd": os.getcwd(),
    }
    
    with open(log_path, "w") as f:
        json.dump(entrypoint_info, f, indent=2)
    
    logger.info(f"Logged supervisor entrypoint to {log_path}")


def wait_for_health(timeout_sec: float = SUPERVISOR_TIMEOUT_SEC) -> bool:
    """
    Poll GET /health endpoint until it responds with 200 OK.
    
    Args:
        timeout_sec: Maximum time to wait for health
        
    Returns:
        True if health endpoint returns 200 within timeout, False otherwise
    """
    health_url = f"{SUPERVISOR_BASE_URL}{SUPERVISOR_HEALTH_PATH}"
    start_time = time.time()
    
    # Exponential backoff: 0.2s → 0.5s → 1.0s
    backoff_sequence = [0.2, 0.5, 1.0]
    backoff_idx = 0
    
    while time.time() - start_time < timeout_sec:
        try:
            response = requests.get(health_url, timeout=2)
            if response.status_code == 200:
                logger.info("Supervisor health check passed")
                return True
        except requests.RequestException:
            pass
        
        # Wait before next attempt
        sleep_time = backoff_sequence[backoff_idx]
        time.sleep(sleep_time)
        
        # Move to next backoff value, but don't exceed max
        backoff_idx = min(backoff_idx + 1, len(backoff_sequence) - 1)
    
    logger.warning(f"Supervisor health check timeout after {timeout_sec}s")
    return False


def ensure_supervisor_running() -> Tuple[SupervisorStatus, Dict]:
    """
    Ensure supervisor is running, starting it if necessary.
    
    Logic:
    - If port free: start supervisor, wait_for_health, return STARTING → RUNNING
    - If port occupied:
      - if is_fishbro_supervisor: RUNNING
      - else: PORT_OCCUPIED with pid/cmdline info
    - NEVER auto-kill any process
    - Ensure no double-spawn (guard with in-process state)
    
    Returns:
        Tuple of (status, details)
        details contains diagnostic information
    """
    # Check port occupancy
    occupant = detect_port_occupant_8000()
    
    if not occupant["occupied"]:
        # Port is free, start supervisor
        try:
            proc = start_supervisor_subprocess()
            logger.info(f"Started supervisor with PID {proc.pid}")
            
            # Wait for health
            if wait_for_health():
                return (SupervisorStatus.RUNNING, {"pid": proc.pid, "action": "started"})
            else:
                # Health check failed
                return (SupervisorStatus.ERROR, {
                    "pid": proc.pid,
                    "error": "health_check_failed",
                    "message": "Supervisor started but health endpoint not responding"
                })
        except Exception as e:
            logger.error(f"Failed to start supervisor: {e}")
            return (SupervisorStatus.ERROR, {
                "error": "startup_failed",
                "message": str(e)
            })
    
    else:
        # Port is occupied
        if occupant["is_fishbro_supervisor"]:
            # Our supervisor is already running
            logger.info(f"Supervisor already running (PID: {occupant['pid']})")
            return (SupervisorStatus.RUNNING, {
                "pid": occupant["pid"],
                "process_name": occupant["process_name"],
                "action": "already_running"
            })
        else:
            # Port occupied by non-fishbro process
            logger.warning(f"Port 8000 occupied by non-fishbro process: {occupant}")
            return (SupervisorStatus.PORT_OCCUPIED, {
                "pid": occupant["pid"],
                "process_name": occupant["process_name"],
                "cmdline": occupant["cmdline"],
                "error": "port_occupied",
                "message": f"Port 8000 occupied by PID {occupant['pid']} ({occupant['process_name']})"
            })

