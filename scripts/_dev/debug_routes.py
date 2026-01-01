#!/usr/bin/env python3
"""Debug route mounting for NiceGUI Socket.IO."""
import sys
sys.path.insert(0, '.')

from src.gui.nicegui.app import build_ui_fastapi_app

app = build_ui_fastapi_app()

print("=== FastAPI app routes ===")
for route in app.routes:
    print(f"{route.path} ({route.methods})")

print("\n=== Inspecting mounted sub-apps ===")
for route in app.routes:
    if hasattr(route, 'app'):
        print(f"Mounted sub-app at {route.path}: {route.app}")
        if hasattr(route.app, 'routes'):
            for subroute in route.app.routes:
                print(f"  {subroute.path} ({subroute.methods})")

print("\n=== Checking for Socket.IO endpoint via ASGI scope ===")
# Try to find a route that matches /_nicegui_ws/socket.io
from fastapi.routing import APIRoute, Mount
for route in app.routes:
    if isinstance(route, Mount):
        if route.path == '/_nicegui_ws':
            print(f"Found Mount at {route.path}")
            # inspect its app
            subapp = route.app
            if hasattr(subapp, 'routes'):
                for subroute in subapp.routes:
                    print(f"  Subroute: {subroute.path} ({subroute.methods})")
        elif route.path.startswith('/_nicegui_ws'):
            print(f"Mount with path {route.path}")
    elif isinstance(route, APIRoute):
        if '/socket.io' in route.path:
            print(f"APIRoute for socket.io: {route.path}")

print("\n=== Using Starlette's router inspection ===")
from starlette.routing import Router
def print_routes(router, prefix=''):
    for route in router.routes:
        if hasattr(route, 'routes'):
            print_routes(route, prefix + route.path)
        else:
            print(f"{prefix}{route.path} ({route.methods})")

try:
    print_routes(app.router)
except Exception as e:
    print(f"Error: {e}")

print("\n=== Checking if NiceGUI's socketio is registered via ui.run_with ===")
import nicegui
print(f"NiceGUI version: {nicegui.__version__}")
# Check if ui.server has a socketio attribute
from nicegui import ui
if hasattr(ui, 'server'):
    print(f"ui.server: {ui.server}")
    if hasattr(ui.server, 'socketio'):
        print(f"ui.server.socketio: {ui.server.socketio}")
else:
    print("ui.server not available")