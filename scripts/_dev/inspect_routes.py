#!/usr/bin/env python3
"""Inspect routes of the FastAPI app."""
import sys
sys.path.insert(0, '.')

# Monkey-patch to avoid import errors
import builtins
real_import = builtins.__import__
def patched_import(name, *args, **kwargs):
    if name == 'gui':
        raise ImportError("Skip gui")
    return real_import(name, *args, **kwargs)
builtins.__import__ = patched_import

try:
    from src.gui.nicegui.app import build_ui_fastapi_app
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

app = build_ui_fastapi_app()

print("=== FastAPI app routes ===")
for route in app.routes:
    print(f"{route.path} ({route.methods})")
    if hasattr(route, 'app'):
        print(f"  -> Mounted sub-app: {route.app}")
        if hasattr(route.app, 'routes'):
            for subroute in route.app.routes:
                print(f"    {subroute.path} ({subroute.methods})")

print("\n=== Searching for Socket.IO mount ===")
from fastapi.routing import Mount
for route in app.routes:
    if isinstance(route, Mount):
        print(f"Mount at {route.path}")
        if route.path == '/_nicegui_ws':
            print("  Found /_nicegui_ws mount")
            subapp = route.app
            if hasattr(subapp, 'routes'):
                for subroute in subapp.routes:
                    print(f"    Subroute: {subroute.path} ({subroute.methods})")
                    if hasattr(subroute, 'app'):
                        print(f"      Sub-sub-app: {subroute.app}")