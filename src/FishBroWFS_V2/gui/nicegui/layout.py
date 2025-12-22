
from __future__ import annotations
from nicegui import ui

NAV = [
    ("Home", "/"),
    ("New Job", "/new-job"),
    ("Job Monitor", "/jobs"),
    ("Results", "/results"),
    ("Charts", "/charts"),
    ("Deploy", "/deploy"),
]

def render_topbar(title: str) -> None:
    """Render the top navigation bar.
    
    IMPORTANT: This function must only be called inside a @ui.page function.
    """
    with ui.header().classes("items-center justify-between"):
        ui.label(title).classes("text-lg font-bold")
        with ui.row().classes("gap-4"):
            for name, path in NAV:
                ui.link(name, path).classes("text-white no-underline hover:underline")


