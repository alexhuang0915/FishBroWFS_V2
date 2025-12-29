"""Global header bar."""
from datetime import datetime
from typing import Optional

from nicegui import ui
from .. import ui_compat as uic

from ..theme.nexus_tokens import TOKENS


def _state_to_color(state: str) -> str:
    """Map state string to accent color token."""
    if state == "ONLINE":
        return TOKENS['accents']['success']
    elif state == "DEGRADED":
        return TOKENS['accents']['warning']
    else:  # OFFLINE
        return TOKENS['accents']['danger']


def _state_to_text(state: str) -> str:
    """Map state string to display text."""
    if state == "ONLINE":
        return "System Online"
    elif state == "DEGRADED":
        return "System Degraded"
    else:
        return "System Offline"


def _state_to_style_class(state: str) -> str:
    """Map state string to CSS text color class."""
    if state == "ONLINE":
        return "text-success"
    elif state == "DEGRADED":
        return "text-warning"
    else:
        return "text-danger"


def render_header() -> None:
    """Render the global header bar."""
    with ui.header().classes("w-full bg-panel-dark border-b border-panel-light px-6 py-3"):
        with ui.row().classes("w-full items-center justify-between"):
            # Left: Logo and title
            with ui.row().classes("items-center gap-4"):
                uic.icon("rocket", color=TOKENS['accents']['purple'], size=uic.IconSize.LG)
                ui.label("Nexus UI").classes("text-xl font-bold text-primary")
                ui.separator().props("vertical").classes("h-6")
                ui.label("FishBroWFS V2").classes("text-secondary font-medium")
            
            # Center: System status indicator (dynamic)
            from ..services.status_service import get_state, get_summary
            status_row = ui.row().classes("items-center gap-2")
            with status_row:
                status_icon = uic.icon("circle", color=TOKENS['accents']['success'], size=uic.IconSize.SM)
                status_label = ui.label("System Online").classes("text-success text-sm")
                # Tooltip with mutable label
                with ui.tooltip() as status_tooltip:
                    tooltip_label = ui.label('')
            
            def update_status_display() -> None:
                state = get_state()
                summary = get_summary()
                color = _state_to_color(state)
                text = _state_to_text(state)
                style_class = _state_to_style_class(state)
                # Update UI
                status_icon._props['color'] = color  # type: ignore
                status_label.set_text(text)
                status_label.classes(replace=f"{style_class} text-sm")
                if hasattr(tooltip_label, 'set_text'):
                    tooltip_label.set_text(summary)
                else:
                    tooltip_label.text = summary
            
            # Update immediately and every 5 seconds
            ui.timer(5.0, update_status_display)
            update_status_display()
            
            # Right: User & time
            with ui.row().classes("items-center gap-4"):
                # Current time
                time_label = ui.label().classes("text-tertiary text-sm")
                
                def update_time() -> None:
                    time_label.set_text(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                
                # Update time every second
                ui.timer(1.0, update_time)
                update_time()
                
                # Human operator badge
                with ui.row().classes("items-center gap-2 bg-panel-medium px-3 py-1 rounded-full"):
                    uic.icon("person", size=uic.IconSize.SM, classes="text-cyan")
                    ui.label("Single Human").classes("text-sm text-secondary")
                
                # Settings button (opens settings page)
                with uic.button("", icon="settings", color="transparent").props("flat dense"):
                    ui.tooltip("Settings")
                    # TODO: navigate to settings tab