#!/usr/bin/env python3
"""
Generate supervisor entrypoint evidence for Phase D.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gui.desktop.supervisor_lifecycle import discover_supervisor_command, log_entrypoint

def main():
    """Discover supervisor command and log it."""
    print("Discovering supervisor entrypoint...")
    cmd = discover_supervisor_command()
    print(f"Discovered command: {cmd}")
    
    # Log it using the existing function
    log_entrypoint(cmd)
    
    # Also print to stdout
    import json
    import time
    entrypoint_info = {
        "timestamp": time.time(),
        "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": cmd,
        "python_executable": sys.executable,
        "cwd": os.getcwd(),
    }
    print(json.dumps(entrypoint_info, indent=2))
    
    # Check if file was created
    from src.gui.desktop.config import SUPERVISOR_ENTRYPOINT_LOG
    if os.path.exists(SUPERVISOR_ENTRYPOINT_LOG):
        print(f"\nEntrypoint logged to: {SUPERVISOR_ENTRYPOINT_LOG}")
        with open(SUPERVISOR_ENTRYPOINT_LOG, 'r') as f:
            print("File content:")
            print(f.read())
    else:
        print(f"\nERROR: File not created at {SUPERVISOR_ENTRYPOINT_LOG}")

if __name__ == "__main__":
    main()