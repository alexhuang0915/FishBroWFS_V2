#!/usr/bin/env python3
"""
Official entry point for the FishBro Governance Console (Phase 9‑OMEGA).

This script starts the single‑truth UI defined in src.dashboard.ui.
"""
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import dashboard.ui to register routes
import dashboard.ui

from nicegui import ui


if __name__ == "__main__":
    ui.run(
        title="FishBro Governance Console",
        port=8080,
        reload=False,
        show=False,  # don't auto‑open browser
    )
