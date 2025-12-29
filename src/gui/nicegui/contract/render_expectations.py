"""
Render expectations – minimal UI footprint per page.

This module defines the minimum counts of UI elements each page must produce
when rendered correctly, and optional markers for diagnostic purposes.

All expectations must be satisfied even when backend is offline.
"""

RENDER_EXPECTATIONS = {
    "dashboard": {
        "min": {"cards": 1, "tables": 1, "logs": 1},
        "markers": ["has_status_cards"],
    },
    "wizard": {
        "min": {"buttons": 1, "selects": 1, "checkboxes": 1, "cards": 1},
        "markers": ["has_stepper"],
    },
    "history": {
        "min": {"cards": 1, "tables": 1},
        "markers": [],
    },
    "candidates": {
        "min": {"tables": 1},
        "markers": ["has_truth_banner"],
    },
    "portfolio": {
        "min": {"cards": 1},
        "markers": [],
    },
    "deploy": {
        "min": {"buttons": 1},
        "markers": [],
    },
    "settings": {
        "min": {"buttons": 1},
        "markers": [],
    },
}