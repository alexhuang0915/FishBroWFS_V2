#!/usr/bin/env python3
"""Test websocket upgrade on Socket.IO path."""
import sys
import os
sys.path.insert(0, '.')

import subprocess
import time
import requests
import socket
import asyncio
import websockets
import json

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

async def test_websocket(port):
    # First get session ID via polling
    polling_url = f"http://127.0.0.1:{port}/_nicegui_ws/socket.io/?EIO=4&transport=polling"
    resp = requests.get(polling_url, timeout=5)
    if resp.status_code != 200:
        print(f"Polling failed: {resp.status_code}")
        return False
    # Response format: "0{"sid":"...",...}"
    body = resp.text
    if not body.startswith('0'):
        print(f"Unexpected polling response: {body[:100]}")
        return False
    # parse JSON part
    try:
        data = json.loads(body[1:])
        sid = data['sid']
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Failed to parse polling response: {e}")
        return False
    print(f"Session ID: {sid}")
    
    # Attempt websocket upgrade
    ws_url = f"ws://127.0.0.1:{port}/_nicegui_ws/socket.io/?EIO=4&transport=websocket&sid={sid}"
    try:
        async with websockets.connect(ws_url) as ws:
            print("WebSocket connection established")
            # Send probe
            await ws.send("2probe")
            response = await asyncio.wait_for(ws.recv(), timeout=2)
            print(f"Received: {response}")
            # Expect "3probe"
            if response == "3probe":
                print("WebSocket upgrade successful")
                return True
            else:
                print(f"Unexpected probe response: {response}")
                return False
    except Exception as e:
        print(f"WebSocket connection failed: {e}")
        return False

async def main():
    port = find_free_port()
    print(f"Starting UI server on port {port}")
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
        
        # Test websocket upgrade
        success = await test_websocket(port)
        if success:
            print("SUCCESS: WebSocket upgrade works, no ASGI contract violation")
        else:
            print("FAILURE: WebSocket upgrade failed")
    finally:
        print("Terminating server")
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(main())