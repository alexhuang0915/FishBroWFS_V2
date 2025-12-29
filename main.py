#!/usr/bin/env python3
"""
Entry point for Nexus UI (FishBroWFS V2).

This replaces the legacy war_room UI.
"""
import sys
import logging

# Ensure src is in path
sys.path.insert(0, "src")

from gui.nicegui.app import start_ui

if __name__ in {"__main__", "__mp_main__"}:
    logging.basicConfig(level=logging.INFO)
    start_ui(host="0.0.0.0", port=8080, show=False)