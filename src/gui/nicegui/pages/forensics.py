"""
Hidden diagnostic page: /__forensics

Generates a UI forensic dump on demand.
"""
import logging
import traceback
from pathlib import Path

from nicegui import ui

from ..services.forensics_service import (
    generate_ui_forensics,
    write_forensics_files,
)

logger = logging.getLogger(__name__)


@ui.page("/__forensics")
def render() -> None:
    """Render the forensic dump page."""
    ui.query("body").classes("bg-panel-dark")
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
        ui.label("UI Forensics").classes("text-3xl font-bold text-primary mb-2")
        ui.label("Generate a complete, deterministic snapshot of the NiceGUI UI subsystem.").classes(
            "text-secondary mb-8"
        )
        
        # Output display area
        output_card = ui.card().classes("w-full bg-panel-medium p-4 mb-4")
        with output_card:
            ui.label("Output will appear here").classes("text-tertiary")
        
        def on_generate() -> None:
            """Generate forensic dump and update UI."""
            try:
                # Clear previous content
                output_card.clear()
                with output_card:
                    ui.label("Generating forensic dump...").classes("text-info")
                    ui.spinner(size="lg")
                    ui.update()
                
                # Generate snapshot
                snapshot = generate_ui_forensics()
                
                # Write files
                result = write_forensics_files(snapshot)
                json_path = Path(result["json_path"]).resolve()
                txt_path = Path(result["txt_path"]).resolve()
                
                # Update UI with results
                output_card.clear()
                with output_card:
                    ui.label("✅ Forensic dump generated").classes("text-success text-lg font-bold mb-2")
                    ui.label(f"JSON: {json_path}").classes("text-secondary mb-1")
                    ui.label(f"Text: {txt_path}").classes("text-secondary mb-4")
                    
                    # Summary
                    status = snapshot["system_status"]
                    ui.label("System Status").classes("font-bold mt-4")
                    ui.label(f"State: {status['state']}").classes("text-secondary")
                    ui.label(f"Summary: {status['summary']}").classes("text-secondary mb-4")
                    
                    # Pages
                    ui.label("Pages").classes("font-bold")
                    pages = snapshot["pages_static"]
                    for page_name, info in pages.items():
                        ok = "✓" if info["import_ok"] else "✗"
                        ui.label(f"  {ok} {page_name}").classes("text-sm")
                    
                    # Open buttons (optional)
                    with ui.row().classes("mt-4 gap-2"):
                        ui.button("Open JSON", icon="open_in_new", on_click=lambda: ui.open(json_path.as_uri()))
                        ui.button("Open Text", icon="open_in_new", on_click=lambda: ui.open(txt_path.as_uri()))
                        ui.button("Copy JSON Path", icon="content_copy", on_click=lambda: ui.clipboard.write(str(json_path)))
                        
            except Exception as e:
                logger.exception("Forensic dump generation failed")
                output_card.clear()
                with output_card:
                    ui.label("❌ Forensic dump failed").classes("text-danger text-lg font-bold mb-2")
                    ui.label(f"{type(e).__name__}: {e}").classes("text-secondary")
                    ui.label(traceback.format_exc()).classes("font-mono text-xs whitespace-pre-wrap")
        
        # Generate button
        ui.button("Generate Forensic Dump", icon="bug_report", on_click=on_generate).classes(
            "bg-cyan text-white px-6 py-3 text-lg"
        )
        
        ui.separator().classes("my-8")
        
        # Explanation
        with ui.card().classes("w-full bg-panel-light p-4"):
            ui.label("What this dump contains").classes("font-bold mb-2")
            ui.label("""
            • System status (backend/worker health, last errors)
            • UI contract validation (expected vs. detected tabs)
            • Page‑render success/failure
            • Wizard, portfolio, and deploy state snapshots
            • Tail of UI logs (if available)
            • Registered UI elements (buttons, inputs, selects, checkboxes)
            """).classes("text-sm text-secondary")
        
        # CLI / UI note
        with ui.card().classes("w-full bg-panel-light p-4 mt-4"):
            ui.label("How to generate from CLI").classes("font-bold mb-2")
            ui.label("CLI: make forensics").classes("text-sm text-secondary")
            ui.label("UI: open /__forensics").classes("text-sm text-secondary")
        
        ui.label("This page is hidden from normal navigation.").classes("text-xs text-muted mt-8")