"""Dashboard page (read-only)."""
import logging
from typing import List, Dict, Any
from nicegui import ui
from .. import ui_compat as uic

from ..layout.cards import render_card
from ..layout.tables import render_simple_table
from ..layout.toasts import show_toast, ToastType
from ..layout.terminal import render_terminal
from ..services.status_service import get_system_status
from ..services.run_index_service import list_runs
from ..services.logs_service import get_recent_logs
from ..state.app_state import AppState

logger = logging.getLogger(__name__)


def render() -> None:
    """Render the Dashboard page."""
    app_state = AppState.get()
    
    ui.label("Dashboard").classes("text-2xl font-bold text-primary mb-6")
    
    # System status row
    with ui.row().classes("w-full gap-4 mb-6"):
        system_status_card = render_card(
            title="System Status",
            content="Checking...",
            icon="check_circle",
            color="success",
            width="w-1/4",
        )
        active_runs_card = render_card(
            title="Active Runs",
            content="0",
            icon="play_circle",
            color="cyan",
            width="w-1/4",
        )
        candidates_card = render_card(
            title="Candidates",
            content="0",
            icon="emoji_events",
            color="purple",
            width="w-1/4",
        )
        storage_card = render_card(
            title="Storage",
            content="N/A",
            icon="storage",
            color="blue",
            width="w-1/4",
        )
    
    # Recent runs table
    with ui.column().classes("w-full bg-panel-dark rounded-lg p-4") as runs_container:
        ui.label("Recent Runs").classes("text-lg font-bold mb-2")
        # Table will be inserted by update function
    
    # Log tail
    with ui.column().classes("w-full bg-panel-dark rounded-lg p-4 mt-4"):
        ui.label("Log Tail").classes("text-lg font-bold mb-2")
        log_terminal = render_terminal(content="", height="150px", follow=True)
    
    # Refresh button
    uic.button("Refresh Dashboard", icon="refresh", on_click=lambda: update_dashboard(
        system_status_card, active_runs_card, candidates_card, storage_card, runs_container, log_terminal
    ), classes="mt-4")
    
    # Initial update
    update_dashboard(system_status_card, active_runs_card, candidates_card, storage_card, runs_container, log_terminal)
    # Auto-refresh every 30 seconds
    ui.timer(30.0, lambda: update_dashboard(
        system_status_card, active_runs_card, candidates_card, storage_card, runs_container, log_terminal
    ))


def update_dashboard(status_card, active_runs_card, candidates_card, storage_card, runs_container, log_terminal) -> None:
    """Fetch live data and update dashboard widgets."""
    try:
        # System status
        status = get_system_status()
        backend_online = status["backend"]["online"]
        worker_alive = status["worker"].get("alive", False)
        overall = status["overall"]
        
        if overall:
            status_card.update_content("All systems operational")
            status_card.update_color("success")
            # icon stays same (check_circle)
        elif backend_online and not worker_alive:
            status_card.update_content("Worker down")
            status_card.update_color("warning")
            # icon stays same (warning)
        else:
            status_card.update_content("Backend unreachable")
            status_card.update_color("danger")  # error -> danger
            # icon stays same (error)
        
        # Active runs count
        runs = list_runs(limit=100)  # get all runs
        active_runs = [r for r in runs if r.get("status") in ("RUNNING", "PENDING")]
        active_runs_card.update_content(str(len(active_runs)))
        
        # Candidates count (placeholder - need candidates service)
        # For now, sum of candidates across runs? Use dummy.
        candidates_card.update_content("N/A")
        
        # Storage (placeholder)
        storage_card.update_content("N/A")
        
        # Update runs table
        columns = ["Run ID", "Season", "Status", "Progress", "Actions"]
        rows = []
        for run in runs[:10]:  # recent 10
            run_id = run.get("run_id", "unknown")
            season = run.get("season", "unknown")
            status = run.get("status", "UNKNOWN")
            progress = run.get("progress", "0%")
            rows.append([run_id, season, status, progress, "View"])
        # Update runs table using simple table helper
        runs_container.clear()
        with runs_container:
            ui.label("Recent Runs").classes("text-lg font-bold mb-2")
            render_simple_table(columns, rows, striped=True, hover=True)
        
        # Log tail
        logs = get_recent_logs(lines=20)
        log_text = "\n".join(logs) if logs else "No logs available"
        log_terminal.set_value(log_text)
        
    except Exception as e:
        logger.exception("Dashboard update failed")
        show_toast(f"Dashboard update failed: {e}", ToastType.ERROR)