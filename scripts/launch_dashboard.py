#!/usr/bin/env python3
"""
Lifecycle Root-Cure: Identity-aware preflight for Control API (8000) and UI (8080).

Commands:
  start          Start dashboard (default behavior)
  stop           Stop FishBro services
  status         Show service status
  restart-ui     Restart UI only (keep Control if valid)
  restart-all    Restart both UI and Control

Core principles:
1. Never blindly kill - always verify identity first
2. Default safe behavior: fail-fast with actionable diagnostics
3. Operator-proof: clear decisions and recovery steps
4. Flat snapshots only (no subfolders)
5. Never kill worker by default
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

# Ensure we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lifecycle")

# Import lifecycle module
try:
    from FishBroWFS_V2.control.lifecycle import (
        PortPreflightResult,
        PortOccupancyStatus,
        preflight_port,
        detect_port_occupant,
        verify_fishbro_control_identity,
        verify_fishbro_ui_identity,
        kill_process,
        write_pidfile,
        read_pidfile,
        remove_pidfile,
        write_metadata,
    )
    LIFECYCLE_AVAILABLE = True
except ImportError as e:
    logger.error("Failed to import lifecycle module: %s", e)
    LIFECYCLE_AVAILABLE = False

# Import runtime context writer
try:
    from FishBroWFS_V2.gui.services.runtime_context import write_runtime_context
    RUNTIME_CONTEXT_AVAILABLE = True
except ImportError:
    RUNTIME_CONTEXT_AVAILABLE = False
    logger.warning("Runtime context module not available")


class ExitCode(Enum):
    """Exit codes for lifecycle commands."""
    SUCCESS = 0
    INVALID_COMBINATION = 2  # Nothing to do / invalid combination
    PORT_OCCUPIED_NOT_FISHBRO = 10  # Port occupied by non-FishBro process
    IDENTITY_VALIDATION_FAILED = 11  # Cannot validate identity / endpoints unreachable
    PROCESS_START_FAILED = 12  # Failed to start child process


class ServiceDecision(Enum):
    """Decision for a service."""
    START = "START"
    REUSE = "REUSE"
    STOP = "STOP"
    KILL = "KILL"
    FAIL_FAST = "FAIL_FAST"
    CONTINUE = "CONTINUE"  # Single-user mode: unknown occupant, continue anyway


@dataclass
class ServicePlan:
    """Plan for a service (Control or UI)."""
    service: str  # "control" or "ui"
    port: int
    host: str
    preflight: PortPreflightResult
    decision: ServiceDecision
    pid: Optional[int] = None
    will_start: bool = False
    will_stop: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class LifecyclePlan:
    """Overall plan for lifecycle operation."""
    operation: str  # "start", "stop", "restart-ui", "restart-all"
    control: ServicePlan
    ui: ServicePlan
    force_kill_ports: bool = False
    pid_dir: Path = Path("outputs/pids")
    runtime_context_path: Path = Path("outputs/snapshots/RUNTIME_CONTEXT.md")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="FishBroWFS V2 Lifecycle Manager (Root-Cure)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Subcommand
    subparsers = parser.add_subparsers(dest="command", help="Lifecycle command")
    subparsers.required = True
    
    # Common arguments for all commands
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--control-host",
        default="127.0.0.1",
        help="Host for Control API server",
    )
    common_parser.add_argument(
        "--control-port",
        type=int,
        default=8000,
        help="Port for Control API server",
    )
    common_parser.add_argument(
        "--ui-host",
        default="127.0.0.1",
        help="Host for NiceGUI UI",
    )
    common_parser.add_argument(
        "--ui-port",
        type=int,
        default=8080,
        help="Port for NiceGUI UI",
    )
    common_parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Logging level",
    )
    common_parser.add_argument(
        "--force-kill-ports",
        action="store_true",
        help="Force kill non-FishBro port occupants (dangerous)",
    )
    common_parser.add_argument(
        "--single-user",
        action="store_true",
        default=True,  # DEFAULT SINGLE-USER MODE (NON-NEGOTIABLE)
        help="Single-user mode: OCCUPIED_UNKNOWN does not fail (default: True)",
    )
    common_parser.add_argument(
        "--pid-dir",
        default="outputs/pids",
        help="Directory for PID files",
    )
    
    # start command
    start_parser = subparsers.add_parser(
        "start",
        help="Start dashboard (default behavior)",
        parents=[common_parser],
    )
    start_parser.add_argument(
        "--no-control",
        action="store_true",
        help="Skip starting Control API (assume already running)",
    )
    start_parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Skip starting UI (only start Control API)",
    )
    start_parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run preflight checks only, don't start services",
    )
    
    # stop command
    stop_parser = subparsers.add_parser(
        "stop",
        help="Stop FishBro services",
        parents=[common_parser],
    )
    
    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show service status",
        parents=[common_parser],
    )
    
    # restart-ui command
    restart_ui_parser = subparsers.add_parser(
        "restart-ui",
        help="Restart UI only (keep Control if valid)",
        parents=[common_parser],
    )
    
    # restart-all command
    restart_all_parser = subparsers.add_parser(
        "restart-all",
        help="Restart both UI and Control",
        parents=[common_parser],
    )
    
    # Backward compatibility: if no command, default to start
    if len(sys.argv) == 1:
        # No arguments, default to start
        sys.argv.append("start")
    
    return parser.parse_args()


def create_service_plan(
    service: str,
    port: int,
    host: str,
    operation: str,
    force_kill_ports: bool = False,
    no_service: bool = False,
    single_user_mode: bool = True,
) -> ServicePlan:
    """
    Create a plan for a service based on preflight and operation.
    
    Args:
        service: "control" or "ui"
        port: Port number
        host: Host address
        operation: "start", "stop", "restart-ui", "restart-all"
        force_kill_ports: Whether to force kill non-FishBro occupants
        no_service: If True, skip this service (e.g., --no-control)
        single_user_mode: If True, OCCUPIED_UNKNOWN does not fail
    
    Returns:
        ServicePlan with decision
    """
    if not LIFECYCLE_AVAILABLE:
        # Fallback without preflight
        return ServicePlan(
            service=service,
            port=port,
            host=host,
            preflight=None,
            decision=ServiceDecision.START if operation == "start" else ServiceDecision.STOP,
            will_start=operation == "start" and not no_service,
            will_stop=operation in ["stop", "restart-all", "restart-ui"] and service == "ui",
        )
    
    # Run preflight
    preflight = preflight_port(
        port=port,
        host=host,
        service_type=service,
        timeout=2.0,
        single_user_mode=single_user_mode
    )
    
    # Determine decision based on operation and preflight
    decision = ServiceDecision.START
    will_start = False
    will_stop = False
    
    if no_service:
        # Service explicitly disabled
        if preflight.status == PortOccupancyStatus.OCCUPIED_FISHBRO:
            decision = ServiceDecision.REUSE
        elif preflight.status == PortOccupancyStatus.OCCUPIED_UNKNOWN and single_user_mode:
            decision = ServiceDecision.CONTINUE
        else:
            decision = ServiceDecision.FAIL_FAST
        will_start = False
        will_stop = False
    elif operation == "start":
        if preflight.status == PortOccupancyStatus.FREE:
            decision = ServiceDecision.START
            will_start = True
        elif preflight.status == PortOccupancyStatus.OCCUPIED_FISHBRO:
            decision = ServiceDecision.REUSE
            will_start = False
        elif preflight.status == PortOccupancyStatus.OCCUPIED_UNKNOWN:
            if single_user_mode:
                decision = ServiceDecision.CONTINUE
                will_start = True  # Try to start anyway
            else:
                decision = ServiceDecision.FAIL_FAST
                will_start = False
        else:  # OCCUPIED_NOT_FISHBRO
            if force_kill_ports:
                decision = ServiceDecision.KILL
                will_start = True
                will_stop = True
            else:
                decision = ServiceDecision.FAIL_FAST
                will_start = False
    
    elif operation == "stop":
        if preflight.status == PortOccupancyStatus.OCCUPIED_FISHBRO:
            decision = ServiceDecision.STOP
            will_stop = True
        elif preflight.status == PortOccupancyStatus.OCCUPIED_UNKNOWN and single_user_mode:
            decision = ServiceDecision.CONTINUE  # Don't stop unknown process
            will_stop = False
        else:
            decision = ServiceDecision.FAIL_FAST
    
    elif operation == "restart-ui":
        if service == "ui":
            if preflight.status == PortOccupancyStatus.OCCUPIED_FISHBRO:
                decision = ServiceDecision.STOP
                will_stop = True
                will_start = True  # Will restart after stop
            elif preflight.status == PortOccupancyStatus.FREE:
                decision = ServiceDecision.START
                will_start = True
            elif preflight.status == PortOccupancyStatus.OCCUPIED_UNKNOWN:
                if single_user_mode:
                    decision = ServiceDecision.CONTINUE
                    will_start = True  # Try to start anyway
                else:
                    decision = ServiceDecision.FAIL_FAST
            else:  # OCCUPIED_NOT_FISHBRO
                if force_kill_ports:
                    decision = ServiceDecision.KILL
                    will_start = True
                    will_stop = True
                else:
                    decision = ServiceDecision.FAIL_FAST
        else:  # control in restart-ui
            if preflight.status == PortOccupancyStatus.OCCUPIED_FISHBRO:
                decision = ServiceDecision.REUSE
                will_start = False
            elif preflight.status == PortOccupancyStatus.FREE:
                decision = ServiceDecision.START
                will_start = True
            elif preflight.status == PortOccupancyStatus.OCCUPIED_UNKNOWN:
                if single_user_mode:
                    decision = ServiceDecision.CONTINUE
                    will_start = False  # Don't start control if unknown
                else:
                    decision = ServiceDecision.FAIL_FAST
            else:  # OCCUPIED_NOT_FISHBRO
                if force_kill_ports:
                    decision = ServiceDecision.KILL
                    will_start = True
                    will_stop = True
                else:
                    decision = ServiceDecision.FAIL_FAST
    
    elif operation == "restart-all":
        if preflight.status == PortOccupancyStatus.OCCUPIED_FISHBRO:
            decision = ServiceDecision.STOP
            will_stop = True
            will_start = True  # Will restart after stop
        elif preflight.status == PortOccupancyStatus.FREE:
            decision = ServiceDecision.START
            will_start = True
        elif preflight.status == PortOccupancyStatus.OCCUPIED_UNKNOWN:
            if single_user_mode:
                decision = ServiceDecision.CONTINUE
                will_start = True  # Try to start anyway
            else:
                decision = ServiceDecision.FAIL_FAST
        else:  # OCCUPIED_NOT_FISHBRO
            if force_kill_ports:
                decision = ServiceDecision.KILL
                will_start = True
                will_stop = True
            else:
                decision = ServiceDecision.FAIL_FAST
    
    return ServicePlan(
        service=service,
        port=port,
        host=host,
        preflight=preflight,
        decision=decision,
        will_start=will_start,
        will_stop=will_stop,
    )


def execute_service_plan(plan: ServicePlan, pid_dir: Path) -> bool:
    """
    Execute a service plan.
    
    Returns:
        True if successful, False otherwise
    """
    if plan.decision == ServiceDecision.FAIL_FAST:
        logger.error(
            "FAIL_FAST: Port %d occupied by non-FishBro process. "
            "Use --force-kill-ports to kill or manually free the port.",
            plan.port
        )
        if plan.preflight and plan.preflight.occupant:
            occupant = plan.preflight.occupant
            logger.error("  Occupant PID: %s", occupant.pid or "unknown")
            logger.error("  Process: %s", occupant.process_name or "unknown")
            logger.error("  Cmdline: %s", occupant.cmdline or "unknown")
        return False
    
    if plan.decision == ServiceDecision.CONTINUE:
        logger.warning(
            "CONTINUE: Port %d occupied by unknown process (single-user mode). "
            "Will attempt to start service anyway.",
            plan.port
        )
        # Don't fail, just continue
        return True
    
    if plan.decision == ServiceDecision.KILL:
        if plan.preflight and plan.preflight.occupant and plan.preflight.occupant.pid:
            pid = plan.preflight.occupant.pid
            logger.warning("Force killing PID %d (non-FishBro occupant)", pid)
            if not kill_process(pid, force=True):
                logger.error("Failed to kill PID %d", pid)
                return False
            # Wait a moment for port to free
            time.sleep(1)
        else:
            logger.error("Cannot kill: no PID identified")
            return False
    
    if plan.decision == ServiceDecision.STOP:
        # Read PID from file first
        pid = read_pidfile(plan.service, pid_dir)
        if not pid and plan.preflight and plan.preflight.occupant:
            pid = plan.preflight.occupant.pid
        
        if pid:
            logger.info("Stopping %s (PID %d)", plan.service, pid)
            if kill_process(pid, force=False):
                logger.info("Stopped %s", plan.service)
                remove_pidfile(plan.service, pid_dir)
            else:
                logger.warning("Failed to stop %s (PID %d)", plan.service, pid)
        else:
            logger.warning("No PID found for %s", plan.service)
    
    return True


def start_control_api(host: str, port: int, pid_dir: Path) -> Optional[int]:
    """
    Start Control API server with explicit child-process supervision and bind verification.
    
    Returns PID if successful, None if failed.
    """
    cmd = [
        sys.executable,
        "-m",
        "FishBroWFS_V2.control.server_main",
        "--host", host,
        "--port", str(port),
        "--log-level", "info",
    ]
    logger.info("Starting Control API: %s", " ".join(cmd))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
    
    try:
        # Start process with explicit supervision
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        pid = proc.pid
        logger.info("Control API process started with PID %d", pid)
        
        # Start bind wait loop with crash detection
        bind_timeout = 10  # seconds (Control API should start faster)
        check_interval = 0.5
        start_time = time.time()
        last_output_lines = []
        
        while time.time() - start_time < bind_timeout:
            # Check if process has crashed
            if proc.poll() is not None:
                # Process exited before binding
                out, _ = proc.communicate()
                exit_code = proc.returncode
                logger.error("Control API process crashed before binding to port %d", port)
                logger.error("Exit code: %d", exit_code)
                logger.error("Last output (last 20 lines):")
                for line in out.splitlines()[-20:]:
                    logger.error("  %s", line)
                return None
            
            # Check if port is bound
            if is_port_bound(port, host):
                logger.info("Port %d is bound - Control API started successfully", port)
                break
            
            # Read any available output for diagnostics
            try:
                line = proc.stdout.readline()
                if line:
                    line = line.rstrip()
                    last_output_lines.append(line)
                    # Keep only last 50 lines
                    if len(last_output_lines) > 50:
                        last_output_lines.pop(0)
                    # Log at debug level
                    logger.debug("Control API stdout: %s", line)
            except (IOError, ValueError):
                pass
            
            time.sleep(check_interval)
        else:
            # Timeout reached - bind failed
            logger.error("Control API failed to bind to port %d within %d seconds", port, bind_timeout)
            
            # Try to get final output
            try:
                # Non-blocking read of remaining output
                import select
                if select.select([proc.stdout], [], [], 0.1)[0]:
                    remaining = proc.stdout.read()
                    if remaining:
                        lines = remaining.splitlines()
                        last_output_lines.extend(lines[-20:])
            except Exception:
                pass
            
            # Kill the process
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            
            # Print diagnostics
            logger.error("Last output from Control API process (last %d lines):", len(last_output_lines))
            for line in last_output_lines:
                logger.error("  %s", line)
            
            return None
        
        # Success - port is bound and process is alive
        write_pidfile(pid, "control", pid_dir)
        
        # Write enhanced metadata with spawn details
        metadata = {
            "host": host,
            "port": port,
            "cmd": " ".join(cmd),
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bind_verified": True,
            "bind_time_seconds": round(time.time() - start_time, 2),
            "supervised_start": True,
            "last_output_sample": last_output_lines[-10:] if last_output_lines else [],
        }
        write_metadata(pid, "control", pid_dir, metadata)
        
        logger.info("Control API started successfully on http://%s:%d (PID %d)", host, port, pid)
        logger.info("Bind verification: port %d is listening", port)
        return pid
        
    except Exception as e:
        logger.error("Failed to start Control API: %s", e)
        import traceback
        logger.error("Traceback: %s", traceback.format_exc())
        return None


def is_port_bound(port: int, host: str = "127.0.0.1") -> bool:
    """
    Check if a port is bound (listening) using ss.
    
    Returns True if port is bound, False otherwise.
    Never raises - treats missing ss/lsof as non-error.
    """
    # Try ss first (preferred)
    ss_cmd = ["bash", "-lc", f"ss -ltnp '( sport = :{port} )'"]
    try:
        ss_output = subprocess.check_output(
            ss_cmd, stderr=subprocess.STDOUT, text=True, timeout=1
        ).strip()
        # Check if any line contains the port and LISTEN
        for line in ss_output.splitlines():
            if f":{port}" in line and "LISTEN" in line:
                return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Try lsof as fallback
    lsof_cmd = ["bash", "-lc", f"lsof -iTCP:{port} -sTCP:LISTEN -n -P"]
    try:
        lsof_output = subprocess.check_output(
            lsof_cmd, stderr=subprocess.STDOUT, text=True, timeout=1
        ).strip()
        # Check if any line contains the port and LISTEN
        for line in lsof_output.splitlines():
            if f":{port}" in line and "LISTEN" in line:
                return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return False


def wait_for_port_bind(port: int, host: str = "127.0.0.1", timeout_seconds: int = 10, check_interval: float = 0.5) -> bool:
    """
    Wait for a port to become bound within timeout.
    
    Returns True if port becomes bound, False if timeout or process crashes.
    """
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if is_port_bound(port, host):
            return True
        time.sleep(check_interval)
    return False


def start_nicegui_ui(host: str, port: int, control_host: str, control_port: int, pid_dir: Path) -> Optional[int]:
    """
    Start NiceGUI UI with explicit child-process supervision and bind verification.
    
    Returns PID if successful, None if failed.
    
    Features:
    1. Explicit child-process supervision
    2. Bind wait loop for port 8080 with crash detection
    3. If bind fails: print last diagnostics and exit non-zero
    4. Ensure "lsof missing" is NOT treated as error condition
    5. Enhanced runtime context enrichment with UI spawn details
    """
    cmd = [
        sys.executable,
        "-m",
        "FishBroWFS_V2.gui.nicegui.app",
    ]
    # Set environment variables to tell UI Bridge where Control API is
    env = os.environ.copy()
    env["CONTROL_API_HOST"] = control_host
    env["CONTROL_API_PORT"] = str(control_port)
    env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
    
    logger.info("Starting NiceGUI UI: %s", " ".join(cmd))
    
    try:
        # Start process with explicit supervision
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        pid = proc.pid
        logger.info("UI process started with PID %d", pid)
        
        # Start bind wait loop with crash detection
        bind_timeout = 15  # seconds
        check_interval = 0.5
        start_time = time.time()
        last_output_lines = []
        
        while time.time() - start_time < bind_timeout:
            # Check if process has crashed
            if proc.poll() is not None:
                # Process exited before binding
                out, _ = proc.communicate()
                exit_code = proc.returncode
                logger.error("UI process crashed before binding to port %d", port)
                logger.error("Exit code: %d", exit_code)
                logger.error("Last output (last 20 lines):")
                for line in out.splitlines()[-20:]:
                    logger.error("  %s", line)
                return None
            
            # Check if port is bound
            if is_port_bound(port, host):
                logger.info("Port %d is bound - UI started successfully", port)
                break
            
            # Read any available output for diagnostics
            try:
                line = proc.stdout.readline()
                if line:
                    line = line.rstrip()
                    last_output_lines.append(line)
                    # Keep only last 50 lines
                    if len(last_output_lines) > 50:
                        last_output_lines.pop(0)
                    # Log at debug level
                    logger.debug("UI stdout: %s", line)
            except (IOError, ValueError):
                pass
            
            time.sleep(check_interval)
        else:
            # Timeout reached - bind failed
            logger.error("UI failed to bind to port %d within %d seconds", port, bind_timeout)
            
            # Try to get final output
            try:
                # Non-blocking read of remaining output
                import select
                if select.select([proc.stdout], [], [], 0.1)[0]:
                    remaining = proc.stdout.read()
                    if remaining:
                        lines = remaining.splitlines()
                        last_output_lines.extend(lines[-20:])
            except Exception:
                pass
            
            # Kill the process
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            
            # Print diagnostics
            logger.error("Last output from UI process (last %d lines):", len(last_output_lines))
            for line in last_output_lines:
                logger.error("  %s", line)
            
            return None
        
        # Success - port is bound and process is alive
        write_pidfile(pid, "ui", pid_dir)
        
        # Write enhanced metadata with spawn details
        metadata = {
            "host": host,
            "port": port,
            "control_host": control_host,
            "control_port": control_port,
            "cmd": " ".join(cmd),
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bind_verified": True,
            "bind_time_seconds": round(time.time() - start_time, 2),
            "supervised_start": True,
            "last_output_sample": last_output_lines[-10:] if last_output_lines else [],
        }
        write_metadata(pid, "ui", pid_dir, metadata)
        
        logger.info("NiceGUI UI started successfully on http://%s:%d (PID %d)", host, port, pid)
        logger.info("Bind verification: port %d is listening", port)
        return pid
        
    except Exception as e:
        logger.error("Failed to start NiceGUI UI: %s", e)
        import traceback
        logger.error("Traceback: %s", traceback.format_exc())
        return None


def write_runtime_context_with_plan(plan: LifecyclePlan) -> Optional[Path]:
    """Write runtime context with lifecycle plan information."""
    if not RUNTIME_CONTEXT_AVAILABLE:
        return None
    
    try:
        # Create enhanced runtime context with plan details
        out_path = write_runtime_context(
            out_path=str(plan.runtime_context_path),
            entrypoint=f"scripts/launch_dashboard.py {plan.operation}",
            listen_host=plan.ui.host,
            listen_port=plan.ui.port,
        )
        
        # Append lifecycle plan details
        if out_path.exists():
            content = out_path.read_text(encoding="utf-8")
            
            plan_section = f"""
## Lifecycle Plan (Root-Cure)

### Operation
- Command: {plan.operation}
- Force kill ports: {plan.force_kill_ports}
- PID directory: {plan.pid_dir}

### Control API (port {plan.control.port})
- Status: {plan.control.preflight.status.value if plan.control.preflight else 'UNKNOWN'}
- Decision: {plan.control.decision.value}
- Will start: {plan.control.will_start}
- Will stop: {plan.control.will_stop}
- PID: {plan.control.pid or 'N/A'}

### UI (port {plan.ui.port})
- Status: {plan.ui.preflight.status.value if plan.ui.preflight else 'UNKNOWN'}
- Decision: {plan.ui.decision.value}
- Will start: {plan.ui.will_start}
- Will stop: {plan.ui.will_stop}
- PID: {plan.ui.pid or 'N/A'}

### Notes
- Worker daemon is never killed by default
- Identity-aware preflight prevents "fog loops"
- Flat snapshots only (no subfolders)
"""
            
            # Insert before the final notes section
            if "## Notes" in content:
                parts = content.split("## Notes", 1)
                new_content = parts[0] + plan_section + "\n## Notes" + parts[1]
                out_path.write_text(new_content, encoding="utf-8")
            else:
                # Append at the end
                with out_path.open("a", encoding="utf-8") as f:
                    f.write(plan_section)
        
        return out_path
        
    except Exception as e:
        logger.warning("Failed to write enhanced runtime context: %s", e)
        # Fall back to basic runtime context
        try:
            return write_runtime_context(
                out_path=str(plan.runtime_context_path),
                entrypoint=f"scripts/launch_dashboard.py {plan.operation}",
                listen_host=plan.ui.host,
                listen_port=plan.ui.port,
            )
        except Exception:
            return None


def print_status(plan: LifecyclePlan) -> None:
    """Print service status."""
    print(f"\nFishBroWFS V2 Service Status")
    print(f"Operation: {plan.operation}")
    print(f"PID directory: {plan.pid_dir}")
    print()
    
    for service_plan in [plan.control, plan.ui]:
        print(f"{service_plan.service.upper()} (port {service_plan.port}):")
        
        if service_plan.preflight:
            status = service_plan.preflight.status.value
            occupant = service_plan.preflight.occupant
            
            print(f"  Status: {status}")
            if occupant and occupant.occupied:
                print(f"  Occupied: Yes")
                print(f"  PID: {occupant.pid or 'unknown'}")
                print(f"  Process: {occupant.process_name or 'unknown'}")
                if occupant.cmdline:
                    print(f"  Cmdline: {occupant.cmdline[:80]}...")
            else:
                print(f"  Occupied: No")
            
            if service_plan.preflight.identity_verified:
                print(f"  Identity: Verified as FishBro")
            elif service_plan.preflight.identity_error:
                print(f"  Identity: Not FishBro ({service_plan.preflight.identity_error})")
        else:
            print(f"  Status: UNKNOWN (preflight not available)")
        
        print(f"  Decision: {service_plan.decision.value}")
        print(f"  Will start: {service_plan.will_start}")
        print(f"  Will stop: {service_plan.will_stop}")
        
        # Check PID file
        pid = read_pidfile(service_plan.service, plan.pid_dir)
        if pid:
            print(f"  PID file: {pid}")
            # Check if process is alive
            try:
                import psutil
                psutil.Process(pid)
                print(f"  Process alive: Yes")
            except (psutil.NoSuchProcess, ImportError):
                print(f"  Process alive: No (stale PID file)")
        else:
            print(f"  PID file: Not found")
        
        print()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    # Check for invalid combinations
    if args.command == "start" and args.no_control and args.no_ui:
        logger.error("Nothing to start (--no-control and --no-ui)")
        sys.exit(ExitCode.INVALID_COMBINATION.value)
    
    # Create PID directory
    pid_dir = Path(args.pid_dir)
    pid_dir.mkdir(parents=True, exist_ok=True)
    
    # Create service plans
    control_plan = create_service_plan(
        service="control",
        port=args.control_port,
        host=args.control_host,
        operation=args.command,
        force_kill_ports=args.force_kill_ports,
        no_service=getattr(args, "no_control", False),
        single_user_mode=args.single_user,
    )
    
    ui_plan = create_service_plan(
        service="ui",
        port=args.ui_port,
        host=args.ui_host,
        operation=args.command,
        force_kill_ports=args.force_kill_ports,
        no_service=getattr(args, "no_ui", False),
        single_user_mode=args.single_user,
    )
    
    # Create overall plan
    plan = LifecyclePlan(
        operation=args.command,
        control=control_plan,
        ui=ui_plan,
        force_kill_ports=args.force_kill_ports,
        pid_dir=pid_dir,
    )
    
    # Write runtime context
    write_runtime_context_with_plan(plan)
    
    # For status command, just print and exit
    if args.command == "status":
        print_status(plan)
        sys.exit(ExitCode.SUCCESS.value)
    
    # For preflight-only, print and exit
    if getattr(args, "preflight_only", False):
        print_status(plan)
        print("\nPreflight only - not starting services")
        sys.exit(ExitCode.SUCCESS.value)
    
    # Check for FAIL_FAST decisions (but CONTINUE is allowed in single-user mode)
    fail_fast = False
    for service_plan in [control_plan, ui_plan]:
        if service_plan.decision == ServiceDecision.FAIL_FAST:
            fail_fast = True
            logger.error(
                "Port %d occupied by non-FishBro process. Use --force-kill-ports to kill.",
                service_plan.port
            )
    
    if fail_fast and not args.force_kill_ports:
        sys.exit(ExitCode.PORT_OCCUPIED_NOT_FISHBRO.value)
    
    # Execute plans (stop phases first)
    for service_plan in [control_plan, ui_plan]:
        if service_plan.will_stop:
            if not execute_service_plan(service_plan, pid_dir):
                logger.error("Failed to execute plan for %s", service_plan.service)
                # Continue anyway
    
    # Wait a moment for ports to free
    if control_plan.will_stop or ui_plan.will_stop:
        time.sleep(2)
    
    # Start services
    control_pid = None
    ui_pid = None
    
    if control_plan.will_start:
        control_pid = start_control_api(
            host=args.control_host,
            port=args.control_port,
            pid_dir=pid_dir,
        )
        if not control_pid:
            logger.error("Failed to start Control API")
            sys.exit(ExitCode.PROCESS_START_FAILED.value)
        control_plan.pid = control_pid
    
    if ui_plan.will_start:
        # UI needs Control API to be reachable
        if control_plan.will_start and control_pid:
            # Wait a bit more for Control API to be ready
            time.sleep(1)
        
        ui_pid = start_nicegui_ui(
            host=args.ui_host,
            port=args.ui_port,
            control_host=args.control_host,
            control_port=args.control_port,
            pid_dir=pid_dir,
        )
        if not ui_pid:
            logger.error("Failed to start UI")
            # Don't exit immediately - Control API might still be useful
        ui_plan.pid = ui_pid
    
    # For stop command, we're done
    if args.command == "stop":
        logger.info("Stop command completed")
        sys.exit(ExitCode.SUCCESS.value)
    
    # For start/restart commands, keep running if we started something
    if control_pid or ui_pid:
        logger.info("Dashboard stack is running.")
        if control_pid:
            logger.info("  Control API: http://%s:%d (PID %d)", args.control_host, args.control_port, control_pid)
        if ui_pid:
            logger.info("  UI Dashboard: http://%s:%d (PID %d)", args.ui_host, args.ui_port, ui_pid)
        
        if args.command in ["start", "restart-ui", "restart-all"]:
            logger.info("Press Ctrl+C to stop")
            
            # Set up signal handlers for graceful shutdown
            def shutdown(signum=None, frame=None):
                logger.info("Shutting down...")
                # Stop services we started
                if ui_pid:
                    kill_process(ui_pid, force=False)
                    remove_pidfile("ui", pid_dir)
                if control_pid:
                    kill_process(control_pid, force=False)
                    remove_pidfile("control", pid_dir)
                logger.info("Shutdown complete")
                sys.exit(0)
            
            signal.signal(signal.SIGINT, shutdown)
            signal.signal(signal.SIGTERM, shutdown)
            
            # Keep main thread alive
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                shutdown()
    
    logger.info("Command completed successfully")
    sys.exit(ExitCode.SUCCESS.value)


if __name__ == "__main__":
    main()