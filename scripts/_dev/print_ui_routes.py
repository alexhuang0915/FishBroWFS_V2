#!/usr/bin/env python3
"""
Print all FastAPI routes created by the UI server (without starting uvicorn).
Used for route inventory verification.
"""
import sys
sys.path.insert(0, "src")

from fastapi import FastAPI
from gui.nicegui.app import build_ui_fastapi_app

def main() -> None:
    app = build_ui_fastapi_app()
    print("=== FastAPI routes ===")
    for route in app.routes:
        if hasattr(route, "methods"):
            methods = ",".join(sorted(route.methods))
            path = getattr(route, "path", "???")
            print(f"{methods:10} {path}")
        else:
            # Likely a mounted ASGI sub‑application (e.g., NiceGUI's Socket.IO)
            # Try to extract path from route
            path = getattr(route, "path", None) or getattr(route, "prefix", None) or "???"
            print(f"MOUNT     {path}")
    
    print("\n=== Checking critical paths ===")
    critical_paths = [
        "/_nicegui_ws/socket.io",
        "/_nicegui/",
        "/health",
        "/api/status",
    ]
    for path in critical_paths:
        found = False
        for route in app.routes:
            route_path = getattr(route, "path", None) or getattr(route, "prefix", None)
            if route_path and route_path.startswith(path):
                found = True
                break
        status = "✓" if found else "✗"
        print(f"{status} {path}")

if __name__ == "__main__":
    main()