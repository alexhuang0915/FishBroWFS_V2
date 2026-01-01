#!/usr/bin/env python3
"""
Entry point for Nexus UI (FishBroWFS V2).

This replaces the legacy war_room UI.
"""
import sys
import logging
import argparse

# Ensure src is in path
sys.path.insert(0, "src")

from gui.nicegui.app import start_ui

if __name__ in {"__main__", "__mp_main__"}:
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="Start Nexus UI server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--show", action="store_true", default=False, help="Open browser window")
    
    args = parser.parse_args()
    
    start_ui(host=args.host, port=args.port, show=args.show)