"""Dashboard page (read-only)."""
import logging
from typing import List, Dict, Any
from nicegui import ui
from .. import ui_compat as uic

from ..layout.cards import render_card
from ..layout.tables import render_simple_table
from ..layout.toasts import show_toast, ToastType
from ..layout.terminal import render_terminal
from ..services.logs_service import get_recent_logs
from ..state.app_state import AppState
from ..constitution.page_shell import page_shell
from ..constitution.truth_providers import (
    get_backend_status_dict,
    list_local_runs,
    get_run_count_by_status,
)

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True


def render() -> None:
    """Render the Dashboard page."""
    app_state = AppState.get()
    
    def render_content():
        ui.label("Dashboard").classes("text-2xl font-bold text-primary mb-6")
        
        # System status row - islands grid
        with ui.element('div').classes('nexus-islands'):
            system_status_card = render_card(
                title="System Status",
                content="Checking...",
                icon="check_circle",
                color="success",
                width="w-full",
            )
            active_runs_card = render_card(
                title="Active Runs",
                content="0",
                icon="play_circle",
                color="cyan",
                width="w-full",
            )
            candidates_card = render_card(
                title="Candidates",
                content="0",
                icon="emoji_events",
                color="purple",
                width="w-full",
            )
            storage_card = render_card(
                title="Storage",
                content="N/A",
                icon="storage",
                color="blue",
                width="w-full",
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
    
    # Wrap in page shell
    page_shell("Dashboard", render_content)


def update_dashboard(status_card, active_runs_card, candidates_card, storage_card, runs_container, log_terminal) -> None:
    """Fetch live data and update dashboard widgets using truth providers."""
    try:
        app_state = AppState.get()
        
        # System status from truth provider
        status = get_backend_status_dict()
        backend_online = status["backend"]["online"]
        worker_alive = status["worker"]["alive"]
        overall = status["overall"]
        state = status.get("state", "UNKNOWN")
        summary = status.get("summary", "")
        
        # Update status card with truthful information
        if state == "ONLINE":
            status_card.update_content("All systems operational")
            status_card.update_color("success")
        elif state == "DEGRADED":
            status_card.update_content("Worker down")
            status_card.update_color("warning")
        else:  # OFFLINE
            status_card.update_content("Backend unreachable")
            status_card.update_color("danger")
        
        # Active runs count from truth provider
        runs = list_local_runs(limit=100, season=app_state.season)  # get all runs for current season
        active_runs = [r for r in runs if r.get("status") in ("RUNNING", "PENDING")]
        active_runs_card.update_content(str(len(active_runs)))
        
        # Get run counts for better insights
        run_counts = get_run_count_by_status(season=app_state.season)
        
        # Candidates count (placeholder - need candidates service)
        # For now, use completed runs as proxy
        candidates_count = run_counts.get("COMPLETED", 0)
        candidates_card.update_content(str(candidates_count))
        
        # Storage (placeholder) - could be enhanced with actual disk usage
        storage_card.update_content("N/A")
        
        # Update runs table with truthful data
        columns = ["Run ID", "Season", "Status", "Started", "Actions"]
        rows = []
        for run in runs[:10]:  # recent 10
            run_id = run.get("run_id", "unknown")
            season = run.get("season", "unknown")
            status = run.get("status", "UNKNOWN")
            started = run.get("started", "N/A")
            # Determine color/icon based on status
            rows.append([run_id, season, status, started, "View"])
        # Update runs table using simple table helper
        runs_container.clear()
        with runs_container:
            ui.label("Recent Runs").classes("text-lg font-bold mb-2")
            render_simple_table(columns, rows, striped=True, hover=True)
        
        # Log tail (still uses logs service, but that's okay for now)
        logs = get_recent_logs(lines=20)
        log_text = "\n".join(logs) if logs else "No logs available"
        log_terminal.set_value(log_text)
        
        # Log truthfulness verification
        logger.debug(f"Dashboard updated with truthful data: state={state}, active_runs={len(active_runs)}")
        
    except Exception as e:
        logger.exception("Dashboard update failed")
        show_toast(f"Dashboard update failed: {e}", ToastType.ERROR)