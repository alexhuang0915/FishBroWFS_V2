"""Settings page - defaults and presets."""
from nicegui import ui
from .. import ui_compat as uic

from ..layout.cards import render_card


def render() -> None:
    """Render the Settings page."""
    ui.label("System Settings").classes("text-2xl font-bold text-primary mb-6")
    ui.label("Defaults affect FUTURE intents only.").classes("text-secondary mb-8")
    
    # Compute defaults
    with ui.card().classes("w-full mb-6"):
        ui.label("Compute Defaults").classes("text-lg font-bold mb-2")
        with ui.row().classes("w-full gap-4"):
            ui.select(["LOW", "MID", "HIGH"], label="Default Compute Level", value="MID").classes("w-1/3")
            ui.number("Default Max Combinations", value=1000, min=1, max=100000).classes("w-1/3")
            ui.number("Safety Limit (jobs)", value=500, min=1, max=10000).classes("w-1/3")
    
    # UI preferences
    with ui.card().classes("w-full mb-6"):
        ui.label("UI Preferences").classes("text-lg font-bold mb-2")
        with ui.row().classes("w-full gap-4"):
            ui.select(["Light", "Dark", "Auto"], label="Theme", value="Dark").classes("w-1/3")
            ui.checkbox("Enable animations")
            ui.checkbox("Show confirmations before destructive actions")
        ui.select(["English", "Chinese"], label="Language", value="English").classes("w-1/3 mt-2")
    
    # Presets management
    with ui.card().classes("w-full mb-6"):
        ui.label("Presets").classes("text-lg font-bold mb-2")
        ui.label("Presets are NON‑AUTHORITATIVE and deletable.").classes("text-sm text-tertiary mb-4")
        with ui.row().classes("w-full gap-4"):
            ui.select(["SMOKE‑MNQ‑30m", "LITE‑MES‑60m", "FULL‑MNQ‑240m"], label="Load Preset", value=None).classes("w-1/3")
            ui.button("Load", icon="upload").classes("w-1/6")
            ui.button("Save Current", icon="save").classes("w-1/6")
            ui.button("Delete", icon="delete", color="danger").classes("w-1/6")
        # Preset list
        with ui.column().classes("w-full mt-4"):
            for name in ["SMOKE‑MNQ‑30m", "LITE‑MES‑60m", "FULL‑MNQ‑240m"]:
                with ui.row().classes("w-full items-center py-2 border-b border-panel-light last:border-0"):
                    ui.label(name).classes("flex-grow")
                    uic.button("Apply", size=uic.BtnSize.SM)
                    uic.button("Edit", size=uic.BtnSize.SM, color="transparent")
    
    # System info
    with ui.card().classes("w-full mb-6"):
        ui.label("System Information").classes("text-lg font-bold mb-2")
        with ui.column().classes("w-full gap-1"):
            ui.label("FishBroWFS V2 · Nexus UI")
            ui.label("Backend API: http://localhost:8000")
            ui.label("Python: 3.11.6")
            ui.label("NiceGUI: 2.0+")
            ui.label("Workspace: /home/fishbro/FishBroWFS_V2")
    
    # Danger zone
    with ui.card().classes("w-full border-2 border-danger"):
        ui.label("⚠️ Danger Zone").classes("text-lg font-bold text-danger mb-2")
        with ui.column().classes("w-full gap-2"):
            ui.label("Actions here can affect system stability.")
            with ui.row().classes("w-full gap-2"):
                ui.button("Clear All Presets", icon="delete_forever", color="danger")
                ui.button("Reset Defaults", icon="restart_alt", color="warning")
                ui.button("Flush Cache", icon="cleaning_services", color="warning")
            ui.label("These actions only affect UI settings, not run artifacts.").classes("text-xs text-muted")