"""Primary Tab Bar with tabs filtered by UI capabilities."""
from typing import Callable, Optional, List

from nicegui import ui

from ..pages import (
    dashboard,
    wizard,
    history,
    candidates,
    portfolio,
    deploy,
    settings,
)
from ..services.ui_capabilities import get_ui_capabilities

# Get current UI capabilities
_CAPS = get_ui_capabilities()

# Tab definitions with their capability flags
_TAB_DEFINITIONS = [
    ("dashboard", "Dashboard", "dashboard", _CAPS.enable_dashboard),
    ("wizard", "Wizard", "auto_fix_high", _CAPS.enable_wizard),
    ("history", "History", "history", _CAPS.enable_history),
    ("candidates", "Candidates", "emoji_events", _CAPS.enable_candidates),
    ("portfolio", "Portfolio", "account_balance", _CAPS.enable_portfolio),
    ("deploy", "Deploy", "rocket_launch", _CAPS.enable_deploy),
    ("settings", "Settings", "settings", _CAPS.enable_settings),
]

# Filter tabs based on capabilities
TAB_IDS: List[str] = [tab_id for tab_id, _, _, enabled in _TAB_DEFINITIONS if enabled]
TAB_LABELS = {tab_id: label for tab_id, label, _, enabled in _TAB_DEFINITIONS if enabled}
TAB_ICONS = {tab_id: icon for tab_id, _, icon, enabled in _TAB_DEFINITIONS if enabled}


def render_tab_bar(
    value: Optional[str] = None,
    on_change: Optional[Callable[[str], None]] = None,
) -> ui.tabs:
    """Render the primary tab bar with 7 tabs.

    Args:
        value: Initial selected tab ID (defaults to first tab).
        on_change: Callback function when tab changes.

    Returns:
        ui.tabs instance.
    """
    if value is None:
        value = TAB_IDS[0]

    with ui.tabs(value=value).classes("w-full bg-panel-dark border-b border-panel-light") as tabs:
        for tab_id in TAB_IDS:
            with ui.tab(tab_id):
                with ui.row().classes("items-center gap-2"):
                    ui.icon(TAB_ICONS[tab_id])
                    ui.label(TAB_LABELS[tab_id])

    if on_change:
        tabs.on("update:model-value", lambda e: on_change(e.args))

    return tabs


def get_tab_content(tab_id: str) -> None:
    """Return the content component for a given tab.
    
    This function renders the appropriate page inside the tab panel.
    For tabs that are disabled by capabilities, shows a "not implemented" message.
    """
    # Map tab IDs to page rendering functions
    page_map = {
        "dashboard": dashboard.render,
        "wizard": wizard.render,
        "history": history.render,
        "candidates": candidates.render,
        "portfolio": portfolio.render,
        "deploy": deploy.render,
        "settings": settings.render,
    }
    
    render_func = page_map.get(tab_id)
    if render_func:
        with ui.column().classes("w-full h-full p-4"):
            render_func()
    else:
        # This should only happen if a tab ID is passed that's not in page_map
        # or if a disabled tab is somehow accessed
        with ui.column().classes("w-full h-full p-4 items-center justify-center"):
            ui.icon("warning").classes("text-6xl text-warning mb-4")
            ui.label(f"Tab '{tab_id}' is not available").classes("text-xl font-bold mb-2")
            ui.label("This feature is disabled in the current UI configuration.").classes("text-tertiary")