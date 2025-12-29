"""History page - list runs."""
import logging
from typing import List, Dict, Any
from nicegui import ui

from ..layout.tables import render_simple_table
from ..layout.cards import render_card
from ..services.run_index_service import list_runs, get_run_details
from ..state.app_state import AppState

logger = logging.getLogger(__name__)


def render() -> None:
    """Render the History page."""
    app_state = AppState.get()
    
    ui.label("Run History").classes("text-2xl font-bold text-primary mb-6")
    
    # Filters
    with ui.row().classes("w-full gap-4 mb-6"):
        season_select = ui.select(["All", "2026Q1", "2025Q4", "2025Q3"], label="Season", value="All").classes("w-1/4")
        status_select = ui.select(["All", "Completed", "Running", "Failed"], label="Status", value="All").classes("w-1/4")
        search_input = ui.input("Search Run ID", placeholder="Enter run ID...").classes("w-1/4")
        filter_btn = ui.button("Apply Filters", icon="filter_list").classes("w-1/4")
    
    # Stats cards
    with ui.row().classes("w-full gap-4 mb-6"):
        total_card = render_card(
            title="Total Runs",
            content="",
            icon="history",
            color="purple",
            width="w-1/4",
        )
        success_card = render_card(
            title="Successful",
            content="",
            icon="check_circle",
            color="success",
            width="w-1/4",
        )
        failed_card = render_card(
            title="Failed",
            content="",
            icon="error",
            color="danger",
            width="w-1/4",
        )
        duration_card = render_card(
            title="Avg Duration",
            content="",
            icon="timer",
            color="cyan",
            width="w-1/4",
        )
    
    # Runs table
    columns = ["Run ID", "Season", "Status", "Started", "Duration", "Artifacts", "Actions"]
    table_container = ui.column().classes("w-full")
    
    # Pagination
    with ui.row().classes("w-full justify-center mt-6"):
        prev_btn = ui.button("Previous", icon="chevron_left")
        page_buttons = ui.row().classes("gap-1")
        next_btn = ui.button("Next", icon="chevron_right")
    
    def update_history():
        """Fetch runs and update UI."""
        try:
            runs = list_runs(limit=100)
            # Apply filters
            season = season_select.value
            status = status_select.value
            search = search_input.value.strip()
            filtered = []
            for run in runs:
                if season != "All" and run.get("season") != season:
                    continue
                if status != "All" and run.get("status") != status.upper():
                    continue
                if search and search.lower() not in run.get("run_id", "").lower():
                    continue
                filtered.append(run)
            
            # Update stats
            total = len(filtered)
            success = sum(1 for r in filtered if r.get("status") == "COMPLETED")
            failed = sum(1 for r in filtered if r.get("status") == "FAILED")
            avg_dur = "N/A"
            total_card.update_content(str(total))
            success_card.update_content(str(success))
            failed_card.update_content(str(failed))
            duration_card.update_content(avg_dur)
            
            # Update table
            table_container.clear()
            rows = []
            for run in filtered[:20]:  # pagination
                run_id = run.get("run_id", "unknown")
                season = run.get("season", "unknown")
                status = run.get("status", "UNKNOWN")
                started = run.get("started", "N/A")
                duration = run.get("duration", "N/A")
                artifacts = "View" if run.get("has_artifacts") else "N/A"
                rows.append([run_id, season, status, started, duration, artifacts, "Open"])
            
            with table_container:
                render_simple_table(columns, rows)
                
        except Exception as e:
            logger.exception("Failed to update history")
            ui.notify(f"Failed to load runs: {e}", type="negative")
    
    filter_btn.on("click", update_history)
    # Initial load
    update_history()