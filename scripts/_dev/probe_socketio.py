#!/usr/bin/env python3
"""Probe Socket.IO route on a running UI server."""
import sys
import os
sys.path.insert(0, '.')

import subprocess
import time
import requests
import socket

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def main():
    port = find_free_port()
    print(f"Starting UI server on port {port}")
    # Start server using main.py (like the test)
    cmd = [sys.executable, "main.py", "--port", str(port)]
    env = os.environ.copy()
    env['PYTHONPATH'] = f"src:{env.get('PYTHONPATH', '')}"
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        # Wait for server to be ready
        base_url = f"http://127.0.0.1:{port}"
        timeout = 30
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                resp = requests.get(f"{base_url}/health", timeout=2)
                if resp.status_code == 200:
                    print("Server is ready")
                    break
            except requests.exceptions.ConnectionError:
                time.sleep(0.5)
        else:
            print("Server failed to start within timeout")
            proc.terminate()
            proc.wait()
            sys.exit(1)
        
        # Probe Socket.IO route
        url = f"{base_url}/_nicegui_ws/socket.io/?EIO=4&transport=polling"
        print(f"Probing {url}")
        resp = requests.get(url, timeout=5)
        print(f"Status: {resp.status_code}")
        print(f"Headers: {resp.headers}")
        if resp.status_code == 404:
            print("Socket.IO route missing (404)")
        else:
            print(f"Body preview: {resp.text[:200]}")
    finally:
        print("Terminating server")
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main()