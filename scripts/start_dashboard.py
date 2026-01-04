#!/usr/bin/env python3
"""
Official entry point for the FishBro Governance Console (Phase 14.1).

This script starts the constitution‑mandated governance UI with URL navigation:
[ OP | Registry | Allocation | Audit ]
"""
import sys
import os
import argparse

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nicegui import ui
from gui.nicegui.constitution.ui_constitution import apply_ui_constitution

# Import pages to register their routes
import gui.nicegui.pages.op
import gui.nicegui.pages.registry
import gui.nicegui.pages.allocation
import gui.nicegui.pages.audit

# Apply UI constitution (dark theme, page shell guarantees)
apply_ui_constitution()

# Apply WebSocket guard middleware to suppress engine.io mismatch spam
from gui.nicegui.asgi.ws_guard import WebSocketGuardMiddleware, WebSocketGuardConfig, default_ws_guard_config_from_env
from gui.nicegui.asgi.socketio_path_normalize import SocketIOPathNormalizeMiddleware
import nicegui.ui_run_with
from fastapi import FastAPI

# Create a FastAPI app
app = FastAPI()

# Add a WebSocket route at /socket.io to blackhole before engineio gets it
# This ensures any WebSocket request to /socket.io is accepted then closed
# before reaching engineio's not_found handler
from starlette.websockets import WebSocket

@app.websocket("/socket.io")
async def websocket_socketio_blackhole(websocket: WebSocket):
    await websocket.accept()
    await websocket.close(code=1008)  # Policy violation

# Let NiceGUI take over the app (mounts its routes)
nicegui.ui_run_with.run_with(app)

# Apply Socket.IO path normalization middleware to ensure trailing slash
app = SocketIOPathNormalizeMiddleware(app)

# At this point, NiceGUI has mounted its routes on the app.
# Now wrap with WebSocket guard middleware to intercept websocket requests
# before they reach engineio/socketio
# Phase 14.7: Allow NiceGUI's socket.io path for live wire
config = default_ws_guard_config_from_env()
app = WebSocketGuardMiddleware(app, config)

# ui.run() will use the wrapped app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start FishBro Governance Console")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--reload", action="store_true", default=False, help="Enable auto-reload")
    parser.add_argument("--show", action="store_true", default=False, help="Open browser window")
    
    args = parser.parse_args()
    
    # Start the UI with the configured app using uvicorn directly
    # ui.run() would start its own server, but we need to use our wrapped app
    import uvicorn
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
