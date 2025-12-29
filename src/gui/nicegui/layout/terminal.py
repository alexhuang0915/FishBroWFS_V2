"""Log viewer terminal."""
from typing import Optional
from nicegui import ui

from ..theme.nexus_tokens import TOKENS
from ..ui_compat import register_element


def render_terminal(
    content: str = "",
    height: str = "300px",
    follow: bool = True,
    font_family: str = "mono",
) -> ui.textarea:
    """Render a terminal‑like log viewer.
    
    Args:
        content: Initial content.
        height: CSS height.
        follow: Whether to auto‑scroll to bottom on update.
        font_family: 'mono' or 'ui'.
    
    Returns:
        Textarea widget styled as terminal.
    """
    font = TOKENS['fonts']['mono'] if font_family == "mono" else TOKENS['fonts']['ui']
    terminal = ui.textarea(value=content).classes("w-full font-mono text-sm").props("readonly")
    terminal.style(f"font-family: {font}; height: {height};")
    terminal.classes("bg-black text-green-400 p-4 rounded-lg overflow-auto")
    register_element("logs", {"height": height, "font_family": font_family})
    
    if follow:
        # Auto‑scroll to bottom when content changes (requires JavaScript)
        # This is a simple implementation; may need more robust solution.
        pass
    
    return terminal


def update_terminal(terminal: ui.textarea, new_content: str, append: bool = True) -> None:
    """Update terminal content."""
    if append:
        current = terminal.value
        terminal.set_value(current + "\n" + new_content if current else new_content)
    else:
        terminal.set_value(new_content)
    # Scroll to bottom (requires JS, skipped for now)