"""
LEGACY UI DEPRECATED (Phase 9‑OMEGA).

This file is quarantined and MUST NOT be used as the official governance UI.
All governance functionality has moved to src.dashboard.ui backed by
dashboard.service.PortfolioService.

Run the official UI with:
    python scripts/start_dashboard.py
"""
from nicegui import ui


@ui.page("/")
def tombstone_page() -> None:
    """Display deprecation notice."""
    with ui.column().classes("w-full h-screen items-center justify-center bg-gray-100"):
        ui.icon("warning").classes("text-6xl text-amber-500 mb-4")
        ui.label("Legacy UI Deprecated").classes("text-3xl font-bold text-gray-800 mb-2")
        ui.label("This UI is no longer the official governance console.").classes("text-lg text-gray-600 mb-6")
        
        with ui.card().classes("p-6 max-w-md"):
            ui.label("Official UI").classes("text-xl font-bold mb-2")
            ui.label("Run the new single‑truth governance console:").classes("mb-4")
            ui.code("python scripts/start_dashboard.py").classes("block p-3 bg-gray-800 text-green-300 rounded mb-4")
            ui.label("The new UI is backed by PortfolioService and enforces proper policy.").classes("text-sm text-gray-500")
        
        ui.label("Do not import or call governance backend modules from this file.").classes("text-sm text-red-500 mt-8")


if __name__ == "__main__":
    # If accidentally executed, still start but show tombstone
    ui.run(title="Legacy UI (Deprecated)", port=8080, reload=False)
