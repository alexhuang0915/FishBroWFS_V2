#!/usr/bin/env python3
"""
Lifecycle Root-Cure: Identity-aware preflight for Control API (8000) and UI (8080).

Core principles:
1. Never blindly kill - always verify identity first
2. Default safe behavior: fail-fast with actionable diagnostics
3. Operator-proof: clear decisions and recovery steps
4. Flat snapshots only (no subfolders)
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

import requests
from requests.exceptions import RequestException, Timeout

# Try to import psutil for process info (optional)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class PortOccupancyStatus(Enum):
    """Status of port occupancy check."""
    FREE = "FREE"
    OCCUPIED_FISHBRO = "OCCUPIED_FISHBRO"
    OCCUPIED_NOT_FISHBRO = "OCCUPIED_NOT_FISHBRO"
    OCCUPIED_UNKNOWN = "OCCUPIED_UNKNOWN"


@dataclass
class PortOccupant:
    """Information about a port occupant."""
    occupied: bool
    pid: Optional[int] = None
    process_name: Optional[str] = None
    cmdline: Optional[str] = None
    raw_output: str = ""
    
    @classmethod
    def free(cls) -> PortOccupant:
        """Create a PortOccupant representing a free port."""
        return cls(occupied=False, raw_output="Port is free")


@dataclass
class PortPreflightResult:
    """Result of port preflight check."""
    port: int
    status: PortOccupancyStatus
    occupant: PortOccupant
    identity_verified: bool = False
    identity_error: Optional[str] = None
    identity_data: Optional[Dict[str, Any]] = None
    decision: str = "PENDING"
    action: str = ""


def extract_listen_pids_from_ss(ss_text: str, port: int) -> List[int]:
    """
    Parse `ss -ltnp` output and return unique PIDs listening on the given port.
    
    Supports patterns like:
      users:(("python3",pid=73466,fd=13))
    Return [] if none.
    """
    pids: set[int] = set()
    for line in ss_text.splitlines():
        if f":{port} " not in line and not line.strip().endswith(f":{port}"):
            continue
        for m in re.finditer(r"pid=(\d+)", line):
            pids.add(int(m.group(1)))
    return sorted(pids)


def get_process_identity(pid: int) -> Dict[str, str]:
    """
    Use psutil (preferred) or /proc/{pid}/cmdline, /proc/{pid}/cwd to return:
      - exe
      - cmdline (joined)
      - cwd
    Never throws; returns best-effort dict.
    """
    result = {"pid": str(pid), "exe": "", "cmdline": "", "cwd": ""}
    
    # Try psutil first
    if HAS_PSUTIL:
        try:
            proc = psutil.Process(pid)
            result["exe"] = proc.exe() or ""
            result["cmdline"] = " ".join(proc.cmdline())
            result["cwd"] = proc.cwd() or ""
            return result
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Fallback to /proc filesystem (Linux)
    try:
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        if cmdline_path.exists():
            cmdline_bytes = cmdline_path.read_bytes()
            parts = [p.decode("utf-8", errors="replace") for p in cmdline_bytes.split(b"\x00") if p]
            result["cmdline"] = " ".join(parts)
    except Exception:
        pass
    
    try:
        exe_path = Path(f"/proc/{pid}/exe")
        if exe_path.exists():
            result["exe"] = str(exe_path.resolve())
    except Exception:
        pass
    
    try:
        cwd_path = Path(f"/proc/{pid}/cwd")
        if cwd_path.exists():
            result["cwd"] = str(cwd_path.resolve())
    except Exception:
        pass
    
    return result


def detect_port_occupant(port: int) -> PortOccupant:
    """
    Detect if a port is occupied and return occupant information.
    
    Uses enhanced detection strategy:
    1. ss -ltnp (primary, shows PID)
    2. /proc/<pid>/cmdline for identity
    3. HTTP identity probe (Control API only)
    4. lsof -iTCP:<port> -sTCP:LISTEN (fallback only)
    
    Returns PortOccupant with best available information.
    """
    # Try ss first (mandatory)
    ss_cmd = ["bash", "-lc", f"ss -ltnp '( sport = :{port} )'"]
    try:
        ss_output = subprocess.check_output(
            ss_cmd, stderr=subprocess.STDOUT, text=True, timeout=2
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        ss_output = ""
    
    # Parse ss output for PIDs
    pids = extract_listen_pids_from_ss(ss_output, port)
    
    if pids:
        # Use first PID (most relevant)
        pid = pids[0]
        identity = get_process_identity(pid)
        cmdline = identity.get("cmdline", "")
        process_name = identity.get("exe", "").split("/")[-1] if identity.get("exe") else ""
        
        return PortOccupant(
            occupied=True,
            pid=pid,
            process_name=process_name or f"pid:{pid}",
            cmdline=cmdline,
            raw_output=ss_output
        )
    
    # Try lsof as fallback only (when ss fails)
    lsof_cmd = ["bash", "-lc", f"lsof -iTCP:{port} -sTCP:LISTEN -n -P"]
    try:
        lsof_output = subprocess.check_output(
            lsof_cmd, stderr=subprocess.STDOUT, text=True, timeout=2
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        lsof_output = ""
    
    if lsof_output and "LISTEN" in lsof_output:
        # Parse lsof output: COMMAND PID USER ...
        lines = lsof_output.splitlines()
        if len(lines) > 1:  # Skip header
            parts = lines[1].split()
            if len(parts) >= 2:
                try:
                    pid = int(parts[1])
                    process_name = parts[0]
                    # Try to get cmdline from /proc
                    identity = get_process_identity(pid)
                    cmdline = identity.get("cmdline", "")
                    
                    return PortOccupant(
                        occupied=True,
                        pid=pid,
                        process_name=process_name,
                        cmdline=cmdline,
                        raw_output=f"ss: {ss_output}\nlsof: {lsof_output}"
                    )
                except (ValueError, IndexError):
                    pass
    
    # If we get here, port might be free or we couldn't parse
    if ss_output or lsof_output:
        # Output exists but we couldn't parse PID
        return PortOccupant(
            occupied=True,
            raw_output=f"ss: {ss_output}\nlsof: {lsof_output}"
        )
    
    # Port appears free
    return PortOccupant.free()


def verify_fishbro_control_identity(host: str, port: int, timeout: float = 2.0) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Verify if occupant on port is FishBro Control API.
    
    Checks GET /__identity endpoint for:
    - service_name == "control_api"
    - repo_root matches current repo
    
    Returns (is_fishbro, identity_data, error_message)
    """
    url = f"http://{host}:{port}/__identity"
    
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            return False, None, f"HTTP {response.status_code}"
        
        data = response.json()
        
        # Check service name
        if data.get("service_name") != "control_api":
            return False, data, f"service_name is '{data.get('service_name')}', not 'control_api'"
        
        # Check repo root (best effort)
        expected_repo_root = str(Path(__file__).parent.parent.parent.absolute())
        actual_repo_root = data.get("repo_root", "")
        if actual_repo_root and expected_repo_root not in actual_repo_root:
            # Not a strict match, but should contain our repo path
            return False, data, f"repo_root mismatch: {actual_repo_root}"
        
        return True, data, None
        
    except Timeout:
        return False, None, "Timeout connecting to identity endpoint"
    except RequestException as e:
        return False, None, f"Connection error: {e}"
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON response: {e}"
    except Exception as e:
        return False, None, f"Unexpected error: {e}"


def verify_fishbro_ui_identity(occupant: PortOccupant) -> Tuple[bool, Optional[str]]:
    """
    Verify if occupant on port is FishBro UI.
    
    Checks cmdline for FishBro module patterns.
    """
    if not occupant.cmdline:
        return False, "No cmdline available"
    
    cmdline = occupant.cmdline.lower()
    
    # Look for FishBro UI module patterns
    ui_patterns = [
        "fishbrowfs_v2.gui.nicegui.app",
        "fishbrowfs_v2/gui/nicegui/app.py",
        "nicegui.app",
    ]
    
    for pattern in ui_patterns:
        if pattern in cmdline:
            return True, None
    
    return False, f"Cmdline doesn't match FishBro UI patterns: {occupant.cmdline[:100]}..."


def preflight_port(
    port: int,
    host: str = "127.0.0.1",
    service_type: str = "control",  # "control" or "ui"
    timeout: float = 2.0,
    single_user_mode: bool = False
) -> PortPreflightResult:
    """
    Perform identity-aware preflight for a port.
    
    Steps:
    1. Detect port occupancy
    2. If occupied, verify identity
    3. Determine status and decision
    
    Classification Rules:
    - PID found + cmdline matches FishBro → OCCUPIED_FISHBRO
    - PID found + cmdline NOT FishBro → OCCUPIED_NOT_FISHBRO
    - PID missing OR cmdline unreadable → OCCUPIED_UNKNOWN
    
    Single-User Mode Rules:
    - OCCUPIED_FISHBRO: Keep/restart as requested
    - OCCUPIED_UNKNOWN: DO NOT FAIL — continue
    - OCCUPIED_NOT_FISHBRO: Fail unless --force-kill-ports
    """
    occupant = detect_port_occupant(port)
    
    if not occupant.occupied:
        return PortPreflightResult(
            port=port,
            status=PortOccupancyStatus.FREE,
            occupant=occupant,
            decision="START",
            action="Port is free, can start service"
        )
    
    # Port is occupied, need to classify
    status = PortOccupancyStatus.OCCUPIED_UNKNOWN
    identity_verified = False
    identity_error = None
    identity_data = None
    
    if occupant.pid:
        # We have a PID, try to verify identity
        try:
            if service_type == "control":
                is_fishbro, data, error = verify_fishbro_control_identity(host, port, timeout)
                identity_verified = is_fishbro
                identity_error = error
                identity_data = data
            else:  # UI
                is_fishbro, error = verify_fishbro_ui_identity(occupant)
                identity_verified = is_fishbro
                identity_error = error
            
            if identity_verified:
                status = PortOccupancyStatus.OCCUPIED_FISHBRO
            elif occupant.cmdline:
                # We have cmdline but it's not FishBro
                status = PortOccupancyStatus.OCCUPIED_NOT_FISHBRO
            else:
                # PID exists but cmdline unreadable
                status = PortOccupancyStatus.OCCUPIED_UNKNOWN
        except Exception as e:
            # Identity probe failed (exception)
            identity_error = f"Identity verification failed: {e}"
            status = PortOccupancyStatus.OCCUPIED_UNKNOWN
    else:
        # No PID found
        status = PortOccupancyStatus.OCCUPIED_UNKNOWN
    
    # Determine decision based on classification and single-user mode
    decision = "PENDING"
    action = ""
    
    if status == PortOccupancyStatus.OCCUPIED_FISHBRO:
        decision = "REUSE"
        action = f"Port occupied by FishBro {service_type}, will reuse"
    elif status == PortOccupancyStatus.OCCUPIED_UNKNOWN:
        if single_user_mode:
            decision = "CONTINUE"
            action = f"Port occupied by unknown process (single-user mode), will continue"
        else:
            decision = "FAIL_FAST"
            action = f"Port occupied by unknown process, cannot verify identity"
    else:  # OCCUPIED_NOT_FISHBRO
        if single_user_mode:
            decision = "FAIL_FAST"
            action = f"Port occupied by non-FishBro process (PID {occupant.pid})"
        else:
            decision = "FAIL_FAST"
            action = f"Port occupied by non-FishBro process (PID {occupant.pid})"
    
    return PortPreflightResult(
        port=port,
        status=status,
        occupant=occupant,
        identity_verified=identity_verified,
        identity_error=identity_error,
        identity_data=identity_data,
        decision=decision,
        action=action
    )


def kill_process(pid: int, force: bool = True) -> bool:
    """
    Kill a process by PID.
    
    Args:
        pid: Process ID to kill
        force: If True, use SIGKILL after SIGTERM fails (default True)
    
    Returns:
        True if process was killed or already dead, False on permission error
    """
    if not HAS_PSUTIL:
        # Fallback to os.kill
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            # Check if still alive
            try:
                os.kill(pid, 0)  # Check if process exists
                if force:
                    os.kill(pid, signal.SIGKILL)
                    time.sleep(0.5)
                return True
            except OSError:
                # Process is dead after SIGTERM
                return True
        except ProcessLookupError:
            # Process already dead
            return True
        except PermissionError:
            # Permission denied
            return False
        except OSError:
            # Other OSError
            return False
    
    # Use psutil if available
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        gone, alive = psutil.wait_procs([proc], timeout=2)
        if alive and force:
            for p in alive:
                p.kill()
            psutil.wait_procs(alive, timeout=1)
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # Process already dead or permission denied
        return True


def write_pidfile(pid: int, service: str, pid_dir: Path) -> Path:
    """
    Write PID file atomically.
    
    Args:
        pid: Process ID
        service: Service name ("control" or "ui")
        pid_dir: Directory for PID files
    
    Returns:
        Path to PID file
    """
    pid_dir.mkdir(parents=True, exist_ok=True)
    pidfile = pid_dir / f"{service}.pid"
    
    # Write atomically via temp file
    tempfile = pidfile.with_suffix(".pid.tmp")
    tempfile.write_text(str(pid))
    tempfile.rename(pidfile)
    
    return pidfile


def read_pidfile(service: str, pid_dir: Path) -> Optional[int]:
    """
    Read PID from PID file.
    
    Returns:
        PID if file exists and contains valid integer, None otherwise
    """
    pidfile = pid_dir / f"{service}.pid"
    if not pidfile.exists():
        return None
    
    try:
        pid_str = pidfile.read_text().strip()
        return int(pid_str)
    except (ValueError, OSError):
        return None


def remove_pidfile(service: str, pid_dir: Path) -> bool:
    """Remove PID file if it exists."""
    pidfile = pid_dir / f"{service}.pid"
    if pidfile.exists():
        try:
            pidfile.unlink()
            return True
        except OSError:
            return False
    return True


def write_metadata(pid: int, service: str, pid_dir: Path, metadata: Dict[str, Any]) -> Path:
    """
    Write metadata JSON file for a service.
    
    Args:
        pid: Process ID
        service: Service name
        pid_dir: Directory for PID files
        metadata: Metadata dict to write
    
    Returns:
        Path to metadata file
    """
    pid_dir.mkdir(parents=True, exist_ok=True)
    metafile = pid_dir / f"{service}.meta.json"
    
    metadata.update({
        "pid": pid,
        "service": service,
        "written_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    
    # Write atomically
    tempfile = metafile.with_suffix(".json.tmp")
    tempfile.write_text(json.dumps(metadata, indent=2))
    tempfile.rename(metafile)
    
    return metafile


if __name__ == "__main__":
    # Test the module
    import argparse
    
    parser = argparse.ArgumentParser(description="Test port preflight")
    parser.add_argument("--port", type=int, default=8000, help="Port to check")
    parser.add_argument("--service", choices=["control", "ui"], default="control", help="Service type")
    
    args = parser.parse_args()
    
    print(f"Preflight check for port {args.port} ({args.service}):")
    result = preflight_port(args.port, service_type=args.service)
    
    print(f"  Status: {result.status.value}")
    print(f"  Occupied: {result.occupant.occupied}")
    if result.occupant.occupied:
        print(f"  PID: {result.occupant.pid}")
        print(f"  Process: {result.occupant.process_name}")
        print(f"  Cmdline: {result.occupant.cmdline}")
    print(f"  Identity verified: {result.identity_verified}")
    if result.identity_error:
        print(f"  Identity error: {result.identity_error}")
    print(f"  Decision: {result.decision}")
    print(f"  Action: {result.action}")