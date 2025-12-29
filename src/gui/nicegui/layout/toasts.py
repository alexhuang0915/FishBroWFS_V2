"""Toast notifications system."""
from enum import Enum
from typing import Optional

from nicegui import ui

from ..theme.nexus_tokens import TOKENS


class ToastType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


def init_toast_system() -> None:
    """Initialize the toast system (currently just sets up CSS)."""
    # Custom CSS for toast positioning
    css = """
    .nicegui-toast {
        font-family: var(--font-ui);
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-elevated);
    }
    """
    ui.add_head_html(f"<style>{css}</style>")


def show_toast(
    message: str,
    toast_type: ToastType = ToastType.INFO,
    duration: int = 3000,
    position: str = "bottom-right",
) -> None:
    """Show a toast notification.
    
    Args:
        message: Text to display.
        toast_type: Toast type (info, success, warning, error).
        duration: Duration in milliseconds.
        position: One of 'top-left', 'top-right', 'bottom-left', 'bottom-right'.
    """
    color_map = {
        ToastType.INFO: TOKENS['accents']['blue'],
        ToastType.SUCCESS: TOKENS['accents']['success'],
        ToastType.WARNING: TOKENS['accents']['warning'],
        ToastType.ERROR: TOKENS['accents']['danger'],
    }
    icon_map = {
        ToastType.INFO: "info",
        ToastType.SUCCESS: "check_circle",
        ToastType.WARNING: "warning",
        ToastType.ERROR: "error",
    }
    
    ui.notify(
        message,
        type=toast_type.value,
        color=color_map[toast_type],
        icon=icon_map[toast_type],
        position=position,
        timeout=duration,
    )