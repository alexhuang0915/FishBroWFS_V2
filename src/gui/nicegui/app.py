"""UI root / app shell for Nexus UI.

Responsibilities:
- Apply Nexus Theme once
- Render Global Header
- Render Primary Tab Bar (7 tabs EXACT)
- Render active page content
"""
import logging
import os
from typing import Optional

from nicegui import ui

from .theme.nexus_theme import apply_nexus_theme
from .layout.header import render_header
from .layout.tabs import render_tab_bar, TAB_IDS, get_tab_content
from .layout.toasts import init_toast_system
from .services.status_service import start_polling
# Hidden forensic page (requires import to register the route)
from .pages import forensics

logger = logging.getLogger(__name__)

# Global app state
_current_tab: Optional[str] = None
_tab_panels: Optional[ui.tab_panels] = None
_SHELL_BUILT: bool = False
_SHELL_BUILD_COUNT: int = 0

# Bootstrap guard
_UI_BOOTSTRAPPED: bool = False
_BOOTSTRAP_COUNT: int = 0


def _on_tab_change(tab_id: str) -> None:
    """Handle tab switching."""
    global _current_tab
    logger.debug(f"Tab changed to {tab_id}")
    _current_tab = tab_id
    if _tab_panels:
        _tab_panels.value = tab_id
    # Optionally load page content dynamically
    # For now, content is pre-rendered in tab panels


def bootstrap_app_shell_and_services() -> None:
    """Bootstrap theme, shell, and polling exactly once per process."""
    global _BOOTSTRAP_COUNT
    if _BOOTSTRAP_COUNT > 0:
        logger.debug("UI already bootstrapped, skipping bootstrap")
        return
    _BOOTSTRAP_COUNT += 1
    logger.debug("Starting UI bootstrap (count = %d)", _BOOTSTRAP_COUNT)
    
    # Theme, shell, polling are idempotent internally
    apply_nexus_theme(use_tailwind=False)
    create_app_shell()
    start_polling()


def create_app_shell() -> None:
    """Create the main app shell with header, tabs, and content area.
    
    This function should be called after ui.run() setup.
    """
    global _tab_panels, _SHELL_BUILT, _SHELL_BUILD_COUNT
    if _SHELL_BUILT:
        logger.debug("App shell already built, skipping")
        return
    _SHELL_BUILD_COUNT += 1
    logger.info("App shell created (pid=%d, call #%d)", os.getpid(), _SHELL_BUILD_COUNT)
    
    # Initialize toast system
    init_toast_system()
    
    # Global Header (top‑level, no container)
    render_header()
    
    # Main content area (everything below header)
    with ui.column().classes("w-full h-full min-h-screen bg-nexus-primary"):
        # Primary Tab Bar (7 tabs EXACT)
        initial_tab = TAB_IDS[0]
        tab_bar = render_tab_bar(value=initial_tab, on_change=_on_tab_change)
        
        # Tab content area
        with ui.tab_panels(tab_bar, value=initial_tab).classes("w-full flex-grow") as panels:
            _tab_panels = panels
            for tab_id in TAB_IDS:
                with ui.tab_panel(tab_id):
                    # Each page is responsible for its own content
                    get_tab_content(tab_id)
        
        # Footer (optional)
        with ui.row().classes("w-full py-2 px-4 text-center text-tertiary text-sm border-t border-panel-dark"):
            ui.label("Nexus UI · Single-Human System · Machine Must Not Make Mistakes")
    
    _SHELL_BUILT = True


def start_ui(host: str = "0.0.0.0", port: int = 8080, show: bool = True) -> None:
    """Start the Nexus UI server.
    
    Args:
        host: Host to bind.
        port: Port to bind.
        show: Whether to open browser window.
    """
    global _UI_BOOTSTRAPPED
    if _UI_BOOTSTRAPPED:
        logger.warning("UI already bootstrapped, start_ui called again. Ignoring.")
        return
    _UI_BOOTSTRAPPED = True  # Set flag before bootstrap
    bootstrap_app_shell_and_services()
    
    # Ensure deterministic single‑process mode
    os.environ['WATCHFILES_RELOAD'] = '0'
    
    # Run NiceGUI
    ui.run(
        host=host,
        port=port,
        title="FishBro War Room",
        favicon="🚀",
        show=show,
        reload=False,
        reconnect_timeout=10.0,
    )