"""History page - list runs."""
import logging
from typing import List, Dict, Any
from nicegui import ui

from ..layout.tables import render_simple_table
from ..layout.cards import render_card
from ..services.run_index_service import list_runs, get_run_details
from ..state.app_state import AppState
from ..constitution.page_shell import page_shell
from ..utils.json_safe import sanitize_rows

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True


def render() -> None:
    """Render the History page."""
    app_state = AppState.get()
    
    def render_content():
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
        columns = ["Run ID", "Season", "Status", "Created", "Experiment YAML", "Actions"]
        table_container = ui.column().classes("w-full")
        
        # Pagination
        with ui.row().classes("w-full justify-center mt-6"):
            prev_btn = ui.button("Previous", icon="chevron_left")
            page_buttons = ui.row().classes("gap-1")
            next_btn = ui.button("Next", icon="chevron_right")
        
        def update_history():
            """Fetch runs and update UI."""
            try:
                # Determine season to fetch
                selected_season = season_select.value
                if selected_season == "All":
                    # For "All", we need to fetch runs from all seasons.
                    # Since list_runs requires a season, we'll fetch for each season individually.
                    # For simplicity, just fetch current season for now.
                    selected_season = app_state.season
                
                runs = list_runs(season=selected_season, limit=100)
                # Apply filters (status and search)
                status = status_select.value
                search = search_input.value.strip()
                filtered = []
                for run in runs:
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
                
                if not filtered:
                    with table_container:
                        ui.label("(no results yet)").classes("text-tertiary italic")
                    return
                
                # Prepare JSON-safe rows data
                rows_data = []
                for run in filtered[:20]:  # pagination
                    run_id = run.get("run_id", "unknown")
                    path = run.get("path", "")
                    rows_data.append({
                        "run_id": run_id,
                        "season": run.get("season", "unknown"),
                        "status": run.get("status", "UNKNOWN"),
                        "started": run.get("started", "N/A"),
                        "experiment_yaml": run.get("experiment_yaml", "—"),
                        "path": path,  # Store path for button callback
                        "actions": "Reveal"  # Placeholder text
                    })
                
                with table_container:
                    # Create table with JSON-safe data
                    table = ui.table(columns=[
                        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
                        {"name": "season", "label": "Season", "field": "season", "align": "left"},
                        {"name": "status", "label": "Status", "field": "status", "align": "left"},
                        {"name": "started", "label": "Created", "field": "started", "align": "left"},
                        {"name": "experiment_yaml", "label": "Experiment YAML", "field": "experiment_yaml", "align": "left"},
                        {"name": "actions", "label": "Actions", "field": "actions", "align": "center"}
                    ], rows=rows_data)
                    
                    # Add slot for actions column with Quasar q-btn
                    table.add_slot(
                        "body-cell-actions",
                        '''
                        <q-td :props="props">
                            <q-btn
                                label="Reveal"
                                dense flat
                                color="primary"
                                @click="() => $parent.$emit('reveal-click', props.row)"
                            />
                        </q-td>
                        '''
                    )
                    
                    # Handle reveal button clicks
                    def on_reveal_click(row):
                        path = row.get("path", "")
                        ui.notify(f"Run directory: {path}", type="info", timeout=3000)
                    
                    table.on("reveal-click", on_reveal_click)
                    
            except Exception as e:
                logger.exception("Failed to update history")
                ui.notify(f"Failed to load runs: {e}", type="negative")
        
        filter_btn.on("click", update_history)
        # Initial load
        update_history()
    
    # Wrap in page shell
    page_shell("Run History", render_content)
