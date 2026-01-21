#!/usr/bin/env python3
"""
Runtime context generation for auditability.

Generates a markdown file documenting the runtime environment:
- Timestamp
- Process information
- Build metadata (git)
- Entrypoint
- Network port occupancy
- Snapshot policy binding
- Notes
"""

from __future__ import annotations

import json
import subprocess
# Subprocess usage: system diagnostics (ss, lsof, git) for runtime context.
# NOT UI ENTRYPOINT – only used by diagnostic scripts and Supervisor bootstrap.
import hashlib
import time
import os
import sys
import platform
import socket
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

try:
    import psutil  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    psutil = None  # type: ignore


# ----------------------------------------------------------------------
# Runtime context data model (optional)
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeContext:
    platform: str
    python_version: str
    hostname: str
    pid: int
    is_wsl: bool
    cpu_count: int
    memory_total_mb: int


def get_runtime_context() -> RuntimeContext:
    hostname = socket.gethostname()
    is_wsl = "microsoft" in platform.release().lower() or "wsl" in platform.release().lower()

    cpu_count = os.cpu_count() or 1

    mem_total_mb = 0
    if psutil is not None:
        try:
            mem_total_mb = int(psutil.virtual_memory().total / (1024 * 1024))
        except Exception:
            mem_total_mb = 0
    else:
        # stdlib fallback: /proc/meminfo (Linux)
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        mem_total_mb = int(kb / 1024)
                        break
        except Exception:
            mem_total_mb = 0

    return RuntimeContext(
        platform=platform.platform(),
        python_version=platform.python_version(),
        hostname=hostname,
        pid=os.getpid(),
        is_wsl=is_wsl,
        cpu_count=cpu_count,
        memory_total_mb=mem_total_mb,
    )


def probe_local_ipv4_addrs() -> List[str]:
    addrs: List[str] = list()

    if psutil is not None:
        try:
            for ifname, infos in psutil.net_if_addrs().items():
                for info in infos:
                    if getattr(info, "family", None) == socket.AF_INET:
                        ip = getattr(info, "address", "")
                        if ip and not ip.startswith("127."):
                            addrs.append(ip)
        except Exception:
            pass

    # fallback (works even without psutil)
    if not addrs:
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and not ip.startswith("127."):
                addrs.append(ip)
        except Exception:
            pass

    # stable ordering for tests
    return sorted(set(addrs))


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------

def _run(cmd) -> str:
    """Run a shell command and return its stdout as string."""
    try:
        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            timeout=2
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def _probe_ss(port: int) -> str:
    """Probe port occupancy using ss command."""
    cmd = ["ss", "-tlnp", f"sport = :{port}"]
    out = _run(cmd)
    if not out or "LISTEN" not in out:
        return "NOT AVAILABLE (ss command failed or no LISTEN)"
    return out


def _probe_lsof(port: int) -> str:
    """Probe port occupancy using lsof command."""
    cmd = ["bash", "-lc", f"lsof -i :{port} -sTCP:LISTEN -n -P"]
    out = _run(cmd)
    if not out or "LISTEN" not in out:
        return "NOT AVAILABLE (lsof command failed or no LISTEN)"
    return out


def _analyze_port_occupancy(port: int) -> Tuple[str, str, str, str]:
    """Analyze port occupancy using both probes.
    
    Returns:
        ss_output, lsof_output, bound ("yes"/"no"), verdict string
    """
    ss_out = _probe_ss(port)
    lsof_out = _probe_lsof(port)
    
    bound = "no"
    verdict = ""
    
    # Determine if port is bound
    if "LISTEN" in ss_out or "LISTEN" in lsof_out:
        bound = "yes"
    
    # Try to extract PID
    pid = None
    if "pid=" in ss_out:
        import re
        m = re.search(r'pid=(\d+)', ss_out)
        if m:
            pid = m.group(1)
    elif lsof_out and lsof_out.strip():
        # lsof output format: COMMAND PID USER ...
        parts = lsof_out.split()
        if len(parts) >= 2:
            pid_candidate = parts[1]
            if pid_candidate.isdigit():
                pid = pid_candidate
    
    if pid:
        verdict = f"PORT BOUND with PID {pid}"
    elif bound == "yes":
        verdict = "bound but no PID (UNRESOLVED)"
    else:
        verdict = "PORT NOT BOUND"
    
    return ss_out, lsof_out, bound, verdict


def get_snapshot_timestamp() -> str:
    """Get timestamp of latest snapshot.
    
    Looks for outputs/snapshots/full/MANIFEST.json first,
    then outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md.
    Returns ISO UTC string or "UNKNOWN".
    """
    # Updated to point to runtime/snapshots as per Logic-Only Constitution
    manifest_path = Path("outputs/runtime/snapshots/full/MANIFEST.json")
    if manifest_path.exists():
        try:
            with open(manifest_path, encoding='utf-8') as f:
                data = json.load(f)
                ts = data.get("generated_at_utc")
                if ts:
                    return ts
        except Exception:
            pass
    
    snapshot_path = Path("outputs/runtime/snapshots/SYSTEM_FULL_SNAPSHOT.md")
    if snapshot_path.exists():
        try:
            mtime = snapshot_path.stat().st_mtime
            dt = datetime.fromtimestamp(mtime, timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    
    return "UNKNOWN"


def get_git_info() -> Tuple[str, str]:
    """Get current git commit hash and dirty status.
    
    Returns:
        (commit_hash, dirty_flag) where dirty_flag is "yes" or "no"
    """
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent.parent,
            stderr=subprocess.DEVNULL
        )
        # output may be bytes or str depending on text param (default bytes)
        if isinstance(output, bytes):
            commit = output.decode('utf-8').strip()
        else:
            commit = output.strip()
    except Exception:
        commit = "UNKNOWN"
    
    try:
        subprocess.check_output(
            ["git", "diff", "--quiet"],
            cwd=Path(__file__).parent.parent.parent,
            stderr=subprocess.DEVNULL
        )
        dirty = "no"
    except subprocess.CalledProcessError:
        dirty = "yes"
    except Exception:
        dirty = "UNKNOWN"
    
    return commit, dirty


def get_policy_hash(policy_path: Path) -> str:
    """Compute SHA256 of policy file, or "UNKNOWN"."""
    if not policy_path.exists() or not policy_path.is_file():
        return "UNKNOWN"
    try:
        with open(policy_path, 'rb') as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()
    except Exception:
        return "UNKNOWN"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def write_runtime_context(
    out_path: str,
    entrypoint: str,
    listen_host: str = "0.0.0.0",
    listen_port: Optional[int] = None,
) -> Path:
    """Write runtime context markdown file.
    
    Args:
        out_path: Path to output markdown file
        entrypoint: Script that launched the runtime
        listen_host: Host interface (default 0.0.0.0)
        listen_port: Optional port for network section
    """
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    lines = list()
    
    # Header
    lines.append("# Runtime Context")
    lines.append("")
    lines.append("## Timestamp")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}")
    lines.append("")
    
    # Process
    lines.append("## Process")
    lines.append(f"- PID: {os.getpid()}")
    try:
        if psutil is not None:
            p = psutil.Process()
            lines.append(f"- Command: {' '.join(p.cmdline())}")
            lines.append(f"- CPU count: {psutil.cpu_count()}")
            lines.append(f"- Memory total: {psutil.virtual_memory().total:,} bytes")
        else:
            # fallback using stdlib
            lines.append(f"- Command: {' '.join(sys.argv)}")
            lines.append(f"- CPU count: {os.cpu_count() or 1}")
            # memory total unknown
            lines.append("- Memory total: unknown (psutil not available)")
    except Exception as e:
        lines.append(f"- Process info unavailable: {e}")
    lines.append("")
    
    # Build
    lines.append("## Build")
    commit, dirty = get_git_info()
    lines.append(f"- Git commit: {commit}")
    lines.append(f"- Dirty working tree: {dirty}")
    snapshot_ts = get_snapshot_timestamp()
    lines.append(f"- Snapshot timestamp: {snapshot_ts}")
    lines.append("")
    
    # Entrypoint
    lines.append("## Entrypoint")
    lines.append(f"- Script: {entrypoint}")
    lines.append(f"- Python: {sys.version}")
    lines.append(f"- CWD: {os.getcwd()}")
    lines.append("")
    
    # Network
    lines.append("## Network")
    if listen_port is not None:
        if listen_host == "0.0.0.0":
            lines.append(f"- Listen: :{listen_port}")
        else:
            lines.append(f"- Listen: {listen_host}:{listen_port}")
        ss_out, lsof_out, bound, verdict = _analyze_port_occupancy(listen_port)
        lines.append(f"- Port occupancy ({listen_port}):")
        lines.append(f"  - Bound: {bound}")
        lines.append(f"  - Process identified: {'yes' if 'PID' in verdict else 'no'}")
        lines.append(f"  - Final verdict: {verdict}")
        lines.append("### ss")
        lines.append("```")
        lines.append(ss_out)
        lines.append("```")
        lines.append("### lsof")
        lines.append("```")
        lines.append(lsof_out)
        lines.append("```")
        lines.append("### Resolution")
        lines.append(verdict)
    else:
        lines.append("- No listen port specified")
    lines.append("")
    
    # Governance
    lines.append("## Governance")
    lines.append("- Runtime context itself is non‑authoritative.")
    lines.append("- For auditability, see manifest and snapshot logs.")
    lines.append("")
    
    # Snapshot Policy Binding
    lines.append("## Snapshot Policy Binding")
    policy_path = Path("outputs/runtime/snapshots/full/LOCAL_SCAN_RULES.json")
    if policy_path.exists():
        policy_hash = get_policy_hash(policy_path)
        lines.append(f"- Local scan rules sha256: {policy_hash}")
        lines.append(f"- Local scan rules source: {policy_path.resolve()}")
    else:
        lines.append("- Local scan rules file not found.")
    lines.append("")
    
    # Notes
    lines.append("## Notes")
    lines.append("- This file is generated automatically at runtime.")
    lines.append("- It reflects a best‑effort snapshot of the environment.")
    lines.append("- Values may be UNKNOWN if underlying commands fail.")
    lines.append("")
    
    # Write file
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# For backward compatibility
port_occupancy = _analyze_port_occupancy  # alias