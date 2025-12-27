#!/usr/bin/env python3
"""
Runtime Truth Block - auto-written on dashboard start.

Contract:
- MUST be generated automatically on make dashboard startup.
- MUST include PID / command / entrypoint module / git commit+dirty / port occupancy / governance state.
- MUST never crash startup; failures degrade to UNKNOWN with short error snippet.
- Output path: outputs/snapshots/RUNTIME_CONTEXT.md (flattened).
- SHOULD include hash of Local-Strict scan rules (LOCAL_SCAN_RULES.json) to bind runtime-to-scan-policy.
"""

from __future__ import annotations
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# psutil is optional for port/process info
try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _run(cmd: list[str]) -> str:
    """Run command and return output, never raise."""
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=False)
        return out.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return f"ERROR: {e!r}"


def _probe_ss(port: int) -> str:
    """Return raw ss output or explicit failure reason."""
    cmd = ["bash", "-lc", f"ss -ltnp '( sport = :{port} )'"]
    result = _run(cmd)
    if not result or "ERROR" in result:
        return "NOT AVAILABLE (ss command failed or returned empty)"
    return result


def _probe_lsof(port: int) -> str:
    """Return raw lsof output or explicit failure reason."""
    cmd = ["bash", "-lc", f"lsof -i :{port} -sTCP:LISTEN -n -P"]
    result = _run(cmd)
    if not result or "ERROR" in result:
        return "NOT AVAILABLE (lsof command failed or returned empty)"
    return result


def _analyze_port_occupancy(port: int) -> tuple[str, str, str, str]:
    """
    Dual-probe port occupancy analysis.
    
    WSL and restricted environments may prevent single-tool socket attribution.
    Dual-probe with explicit resolution guarantees runtime truth without guesswork.
    
    Returns:
        (ss_output, lsof_output, bound_status, resolution_verdict)
    """
    ss_output = _probe_ss(port)
    lsof_output = _probe_lsof(port)
    
    # Determine if port is bound
    bound = "no"
    process_identified = "no"
    pid = None
    
    import re
    
    # Check ss output for actual binding (not just header)
    # Look for a line containing the port number and LISTEN state
    ss_lines = ss_output.splitlines()
    for line in ss_lines:
        if f":{port}" in line and "LISTEN" in line:
            bound = "yes"
            # Try to extract PID from this line
            ss_pid_match = re.search(r'pid=(\d+)', line)
            if ss_pid_match:
                pid = ss_pid_match.group(1)
                process_identified = "yes"
            break
    
    # Check lsof output if ss didn't find it
    if bound == "no" or process_identified == "no":
        lsof_lines = lsof_output.splitlines()
        for line in lsof_lines:
            if f":{port}" in line and "LISTEN" in line:
                bound = "yes"
                # Try to extract PID from lsof output
                # lsof pattern: python3 12345 user 3u IPv4 12345 0t0 TCP *:8080 (LISTEN)
                lsof_pid_match = re.search(r'^\S+\s+(\d+)\s+', line)
                if lsof_pid_match and not pid:  # Only if PID not already found
                    pid = lsof_pid_match.group(1)
                    process_identified = "yes"
                break
    
    # Build resolution verdict
    if bound == "no":
        verdict = "PORT NOT BOUND"
    elif process_identified == "yes":
        verdict = f"PID {pid}"
    else:
        verdict = "UNRESOLVED (bound but no PID identified)"
    
    return ss_output, lsof_output, bound, verdict


def get_git_info() -> tuple[str, str]:
    """Get git commit hash and dirty status."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except Exception:
        commit = "UNKNOWN"
    
    try:
        dirty_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
        dirty = "yes" if dirty_out else "no"
    except Exception:
        dirty = "UNKNOWN"
    
    return commit, dirty


def get_policy_hash(policy_path: Path) -> str:
    """Compute SHA256 hash of LOCAL_SCAN_RULES.json."""
    if not policy_path.exists():
        return "UNKNOWN"
    
    try:
        with open(policy_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return "UNKNOWN"


def get_season_state() -> tuple[str, str]:
    """Get current season state and ID if available."""
    # Try to import SeasonState if available
    try:
        from core.season_state import SeasonState
        state = SeasonState.load_current()
        season_id = state.season_id if hasattr(state, "season_id") else "UNKNOWN"
        frozen = "FROZEN" if state.is_frozen() else "ACTIVE"
        return frozen, season_id
    except Exception:
        return "UNKNOWN", "UNKNOWN"


def write_runtime_context(
    out_path: str | Path = "outputs/snapshots/RUNTIME_CONTEXT.md",
    *,
    entrypoint: str,
    listen_host: str | None = None,
    listen_port: int | None = 8080,
) -> Path:
    """
    Write runtime truth block; never raise; always returns out_path.
    
    Args:
        out_path: Path to write the runtime context file.
        entrypoint: Entrypoint module name (e.g., "scripts/launch_dashboard.py").
        listen_host: Host the service is listening on (optional).
        listen_port: Port the service is listening on (default 8080).
    
    Returns:
        Path to the written file.
    """
    out_path = Path(out_path)
    
    # Never crash - catch all exceptions
    try:
        lines = []
        lines.append("# Runtime Context")
        lines.append("")
        
        # Timestamp
        lines.append("## Timestamp")
        lines.append(datetime.datetime.now(datetime.timezone.utc).isoformat())
        lines.append("")
        
        # Process
        lines.append("## Process")
        lines.append(f"PID: {os.getpid()}")
        lines.append(f"PPID: {os.getppid()}")
        cmdline = "UNKNOWN"
        if HAS_PSUTIL:
            try:
                proc = psutil.Process()
                cmdline = " ".join(proc.cmdline())
            except Exception:
                pass
        else:
            # Fallback to sys.argv
            cmdline = " ".join(sys.argv)
        lines.append(f"Command: {cmdline}")
        lines.append(f"Working directory: {os.getcwd()}")
        lines.append("")
        
        # Build
        lines.append("## Build")
        git_commit, git_dirty = get_git_info()
        lines.append(f"Git commit: {git_commit}")
        lines.append(f"Dirty: {git_dirty}")
        lines.append(f"Python: {sys.version.split()[0]}")
        lines.append(f"Platform: {platform.platform()}")
        lines.append("")
        
        # Entrypoint
        lines.append("## Entrypoint")
        lines.append(f"Module: {entrypoint}")
        lines.append("")
        
        # Network
        lines.append("## Network")
        if listen_host:
            lines.append(f"Listen: {listen_host}:{listen_port}")
        else:
            lines.append(f"Listen: :{listen_port}")
        
        if listen_port:
            lines.append("")
            lines.append(f"Port occupancy ({listen_port}):")
            lines.append("")
            
            # Dual-probe strategy
            ss_output, lsof_output, bound_status, resolution_verdict = _analyze_port_occupancy(listen_port)
            
            lines.append("### ss")
            for line in ss_output.splitlines():
                lines.append(line)
            lines.append("")
            
            lines.append("### lsof")
            for line in lsof_output.splitlines():
                lines.append(line)
            lines.append("")
            
            lines.append("### Resolution")
            lines.append(f"- Bound: {bound_status}")
            lines.append(f"- Process identified: {'yes' if 'PID' in resolution_verdict else 'no'}")
            lines.append(f"- Final verdict: {resolution_verdict}")
        lines.append("")
        
        # Governance
        lines.append("## Governance")
        season_state, season_id = get_season_state()
        lines.append(f"Season state: {season_state}")
        lines.append(f"Season id (if any): {season_id}")
        lines.append("")
        
        # Snapshot Policy Binding
        lines.append("## Snapshot Policy Binding")
        # Look for LOCAL_SCAN_RULES.json embedded in SYSTEM_FULL_SNAPSHOT.md
        # or in the old location for backward compatibility
        policy_paths = [
            Path("outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md"),  # Embedded in flattened snapshot
            Path("outputs/snapshots/full/LOCAL_SCAN_RULES.json"),  # Old location (backward compat)
        ]
        
        policy_hash = "UNKNOWN"
        policy_source = "NOT_FOUND"
        
        for policy_path in policy_paths:
            if policy_path.exists():
                if policy_path.name == "SYSTEM_FULL_SNAPSHOT.md":
                    # Try to extract LOCAL_SCAN_RULES from embedded content
                    try:
                        content = policy_path.read_text(encoding="utf-8")
                        # Look for LOCAL_SCAN_RULES section
                        import re
                        json_match = re.search(r'```json\s*({.*?})\s*```', content, re.DOTALL)
                        if json_match:
                            # Compute hash of the JSON content
                            json_str = json_match.group(1)
                            policy_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
                            policy_source = f"embedded in {policy_path.name}"
                            break
                    except Exception:
                        pass
                else:
                    # Direct JSON file
                    policy_hash = get_policy_hash(policy_path)
                    policy_source = str(policy_path)
                    break
        
        lines.append(f"Local scan rules sha256: {policy_hash}")
        lines.append(f"Local scan rules source: {policy_source}")
        lines.append("")
        
        # Notes
        lines.append("## Notes")
        lines.append("Generated automatically on dashboard startup.")
        lines.append("This file is part of the Local-Strict snapshot system.")
        lines.append("")
        
        # Write file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(lines)
        out_path.write_text(content, encoding="utf-8")
        
    except Exception as e:
        # Degrade gracefully - write minimal content with error
        try:
            error_content = f"""# Runtime Context

## Error
Failed to generate full runtime context: {e!r}

## Timestamp
{datetime.datetime.now(datetime.timezone.utc).isoformat()}

## Minimal Info
PID: {os.getpid()}
Entrypoint: {entrypoint}
"""
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(error_content, encoding="utf-8")
        except Exception:
            # Last resort - create empty file
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text("# Runtime Context - Generation Failed", encoding="utf-8")
            except Exception:
                pass
    
    return out_path


def get_snapshot_timestamp() -> str:
    """
    Get snapshot timestamp for UI banner.
    
    Priority:
    1. MANIFEST.json generation time (embedded in SYSTEM_FULL_SNAPSHOT.md)
    2. mtime of outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md
    3. UNKNOWN
    """
    # Check SYSTEM_FULL_SNAPSHOT.md for embedded MANIFEST
    snapshot_path = Path("outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md")
    if snapshot_path.exists():
        try:
            content = snapshot_path.read_text(encoding="utf-8")
            # Look for MANIFEST section with JSON
            import re
            # Find the MANIFEST section
            manifest_section_match = re.search(r'## MANIFEST\s*(.*?)(?=##|\Z)', content, re.DOTALL)
            if manifest_section_match:
                manifest_section = manifest_section_match.group(1)
                # Look for JSON code block
                json_match = re.search(r'```json\s*({.*?})\s*```', manifest_section, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    data = json.loads(json_str)
                    if "generated_at_utc" in data:
                        return data["generated_at_utc"]
        except Exception:
            pass
        
        # Fallback to file modification time
        try:
            mtime = snapshot_path.stat().st_mtime
            dt = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    
    # Check old location for backward compatibility
    manifest_path = Path("outputs/snapshots/full/MANIFEST.json")
    if manifest_path.exists():
        try:
            with open(manifest_path, "r") as f:
                data = json.load(f)
                if "generated_at_utc" in data:
                    return data["generated_at_utc"]
        except Exception:
            pass
    
    return "UNKNOWN"


if __name__ == "__main__":
    # Test when run directly
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Write runtime context file for testing."
    )
    parser.add_argument(
        "--out-path",
        default="outputs/snapshots/RUNTIME_CONTEXT.md",
        help="Output path for runtime context."
    )
    parser.add_argument(
        "--entrypoint",
        default="test",
        help="Entrypoint module name."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to check occupancy for."
    )
    
    args = parser.parse_args()
    
    path = write_runtime_context(
        out_path=args.out_path,
        entrypoint=args.entrypoint,
        listen_port=args.port,
    )
    print(f"Runtime context written to: {path}")
    print(f"Size: {path.stat().st_size:,} bytes")