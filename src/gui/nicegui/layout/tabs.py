"""Primary Tab Bar with 7 tabs EXACT."""
from typing import Callable, Optional

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

# Tab IDs in exact order, no more, no less
TAB_IDS = [
    "dashboard",
    "wizard",
    "history",
    "candidates",
    "portfolio",
    "deploy",
    "settings",
]

TAB_LABELS = {
    "dashboard": "Dashboard",
    "wizard": "Wizard",
    "history": "History",
    "candidates": "Candidates",
    "portfolio": "Portfolio",
    "deploy": "Deploy",
    "settings": "Settings",
}

TAB_ICONS = {
    "dashboard": "dashboard",
    "wizard": "auto_fix_high",
    "history": "history",
    "candidates": "emoji_events",
    "portfolio": "account_balance",
    "deploy": "rocket_launch",
    "settings": "settings",
}


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
        ui.label(f"Page '{tab_id}' not implemented").classes("text-danger")