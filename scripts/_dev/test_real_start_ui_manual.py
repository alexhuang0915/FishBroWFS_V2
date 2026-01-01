#!/usr/bin/env python3
"""Test the actual start_ui function."""
import sys
import asyncio
import httpx
import os

sys.path.insert(0, "src")

# Set environment to match production
os.environ['WATCHFILES_RELOAD'] = '0'

from gui.nicegui.app import start_ui
import threading
import time
import signal

def run_server():
    """Run server in a thread."""
    start_ui(host="127.0.0.1", port=8083, show=False)

async def test():
    """Test the running server."""
    # Start server in background thread
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    
    # Wait for server to start
    await asyncio.sleep(3)
    
    try:
        async with httpx.AsyncClient() as client:
            # Test Socket.IO endpoint
            resp = await client.get("http://127.0.0.1:8083/_nicegui_ws/socket.io/?EIO=4&transport=polling")
            print(f"Socket.IO polling: {resp.status_code}")
            print(f"Response preview: {resp.text[:100] if resp.text else 'None'}")
            
            if resp.status_code == 404:
                print("ERROR: Socket.IO endpoint returned 404")
                return False
            else:
                print("SUCCESS: Socket.IO endpoint is accessible")
                return True
    finally:
        # Cannot easily stop uvicorn server, but thread will die when process exits
        pass

if __name__ == "__main__":
    # Run test
    success = asyncio.run(test())
    sys.exit(0 if success else 1)