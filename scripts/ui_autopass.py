#!/usr/bin/env python3
"""
UI AUTOPASS — single‑command system self‑test.

Thin wrapper around the autopass module in src.
"""
import sys

from gui.nicegui.autopass.report import main

if __name__ == "__main__":
    sys.exit(main())