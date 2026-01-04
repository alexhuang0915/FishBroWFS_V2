"""URL-based navigation for Phase 14.1."""
from nicegui import ui

# Navigation definitions for URL-based navigation
NAV = [
    ("OP", "/"),
    ("REGISTRY", "/registry"),
    ("ALLOCATION", "/allocation"),
    ("AUDIT", "/audit"),
]

def render_top_nav(active: str) -> None:
    """Render top navigation links for URL-based navigation.
    
    Args:
        active: The active route (e.g., '/' for OP, '/registry' for Registry)
    """
    with ui.row().classes("w-full items-center justify-center gap-8 py-2"):
        for label, href in NAV:
            is_active = (href == active)
            cls = "text-sm font-semibold tracking-wide"
            cls += " text-white underline underline-offset-8" if is_active else " text-gray-300 hover:text-white"
            ui.link(label, href).classes(cls)