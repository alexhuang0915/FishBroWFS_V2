"""
UI Contract – Canonical definitions of UI pages and tabs.

This module is the single source of truth for UI page IDs, import paths,
and the expected tab order. It must NOT contain any runtime UI creation,
import‑time side effects, or dependencies on other UI modules.

All UI‑related modules (forensics, wizard, app shell, etc.) must import
these constants from here, never from ui_compat or elsewhere.
"""

UI_CONTRACT = {
    "tabs_expected": [
        "Dashboard",
        "Wizard",
        "History",
        "Candidates",
        "Portfolio",
        "Deploy",
        "Settings",
    ],
    "tab_ids": ["dashboard", "wizard", "history", "candidates", "portfolio", "deploy", "settings"],
    "pages": {
        "dashboard": "gui.nicegui.pages.dashboard",
        "wizard": "gui.nicegui.pages.wizard",
        "history": "gui.nicegui.pages.history",
        "candidates": "gui.nicegui.pages.candidates",
        "portfolio": "gui.nicegui.pages.portfolio",
        "deploy": "gui.nicegui.pages.deploy",
        "settings": "gui.nicegui.pages.settings",
    },
}

PAGE_IDS = UI_CONTRACT["tab_ids"]

PAGE_MODULES = {
    "dashboard":  "gui.nicegui.pages.dashboard",
    "wizard":     "gui.nicegui.pages.wizard",
    "history":    "gui.nicegui.pages.history",
    "candidates": "gui.nicegui.pages.candidates",
    "portfolio":  "gui.nicegui.pages.portfolio",
    "deploy":     "gui.nicegui.pages.deploy",
    "settings":   "gui.nicegui.pages.settings",
}