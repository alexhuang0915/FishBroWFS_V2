#!/usr/bin/env python3
"""
Topology Probe - inspect which ports have listeners and fetch service identity.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/topology_probe.py

Behavior:
- Uses subprocess to run ss -lntp and parse lines for common ports (8080, 8000, 8001).
- For each detected listener on :8080, attempt HTTP GET:
    http://localhost:8080/__identity
    http://localhost:8080/health
    http://localhost:8080/status (best-effort)
- Print results as a structured text report.

Must exit 0 always (this is a probe tool), but print failures.
No external deps beyond stdlib. Use urllib.request for GET.
"""

import subprocess
import sys
import json
import urllib.request
import urllib.error
import socket
from typing import Dict, Any, List, Optional


def run_ss() -> List[str]:
    """Run ss -lntp and return lines."""
    try:
        result = subprocess.run(
            ["ss", "-lntp"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"WARNING: ss command failed: {result.stderr}", file=sys.stderr)
            return []
        return result.stdout.strip().splitlines()
    except FileNotFoundError:
        print("WARNING: 'ss' command not found, falling back to netstat", file=sys.stderr)
        return run_netstat()


def run_netstat() -> List[str]:
    """Fallback using netstat -tlnp."""
    try:
        result = subprocess.run(
            ["netstat", "-tlnp"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"WARNING: netstat command failed: {result.stderr}", file=sys.stderr)
            return []
        return result.stdout.strip().splitlines()
    except FileNotFoundError:
        print("ERROR: Neither ss nor netstat available", file=sys.stderr)
        return []


def parse_listeners(lines: List[str]) -> Dict[str, Dict[str, Any]]:
    """Parse ss/netstat output for listeners on ports 8080, 8000, 8001."""
    listeners = {}
    for line in lines:
        # Skip header lines
        if "LISTEN" not in line:
            continue
        parts = line.split()
        # Find address column (varies between ss and netstat)
        addr = None
        for part in parts:
            if ":" in part and ("8080" in part or "8000" in part or "8001" in part):
                addr = part
                break
        if not addr:
            continue
        # Extract port
        if ":" in addr:
            port = addr.split(":")[-1]
        else:
            continue
        # Extract PID/process (if available)
        pid = "unknown"
        for part in parts:
            if "pid=" in part:
                pid = part.split("=")[1].split(",")[0]
                break
        listeners[port] = {"address": addr, "pid": pid, "raw": line}
    return listeners


def http_get(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """Perform HTTP GET and return JSON if possible, else None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "topology-probe/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status == 200:
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return {"raw": body.strip()}
            else:
                return {"status": resp.status, "body": body[:200]}
    except urllib.error.URLError as e:
        return {"error": str(e)}
    except socket.timeout:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


def probe_port(port: str) -> Dict[str, Any]:
    """Probe a single port for identity, health, status."""
    base = f"http://localhost:{port}"
    result = {
        "port": port,
        "identity": None,
        "health": None,
        "status": None,
    }
    # Identity endpoint
    ident_resp = http_get(f"{base}/__identity")
    result["identity"] = ident_resp
    # Health endpoint
    health_resp = http_get(f"{base}/health")
    result["health"] = health_resp
    # Status endpoint (optional)
    status_resp = http_get(f"{base}/status")
    result["status"] = status_resp
    return result


def main() -> None:
    print("=== Topology Probe ===")
    lines = run_ss()
    listeners = parse_listeners(lines)
    if not listeners:
        print("No listeners found on ports 8080, 8000, 8001.")
        sys.exit(0)
    
    print(f"Found {len(listeners)} listener(s):")
    for port, info in listeners.items():
        print(f"  Port {port}: {info['address']} (PID {info['pid']})")
    
    print("\n--- Probing each listener ---")
    for port in listeners:
        print(f"\nPort {port}:")
        probe = probe_port(port)
        if probe["identity"] and "service_name" in probe["identity"]:
            print(f"  Identity: service_name={probe['identity'].get('service_name')}")
            print(f"    pid={probe['identity'].get('pid')}, git={probe['identity'].get('git_commit', 'unknown')[:8]}")
        else:
            print(f"  Identity: {probe['identity']}")
        if probe["health"]:
            if isinstance(probe["health"], dict) and "status" in probe["health"]:
                print(f"  Health: {probe['health']['status']}")
            else:
                print(f"  Health: {probe['health']}")
        if probe["status"]:
            print(f"  Status: {probe['status']}")
    
    print("\n=== Summary ===")
    for port in listeners:
        probe = probe_port(port)
        ident = probe["identity"]
        if ident and isinstance(ident, dict) and "service_name" in ident:
            print(f"Port {port}: {ident['service_name']} (pid {ident.get('pid')})")
        else:
            print(f"Port {port}: unknown")


if __name__ == "__main__":
    main()