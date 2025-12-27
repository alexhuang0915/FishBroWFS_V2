"""Jobs List Page for M1.

Display list of jobs with state, stage, units_done, units_total.
"""

from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime

from nicegui import ui
# Use JobsBridge for Zero-Violation Split-Brain Architecture
from FishBroWFS_V2.gui.nicegui.bridge.jobs_bridge import get_jobs_bridge


def create_job_card(job: Dict[str, Any]) -> None:
    """Create a job card for the jobs list."""
    with ui.card().classes("w-full mb-4 hover:shadow-md transition-shadow cursor-pointer"):
        # Card header with job ID and status
        with ui.row().classes("w-full items-center justify-between"):
            # Left: Job ID and basic info
            with ui.column().classes("flex-1"):
                with ui.row().classes("items-center gap-2"):
                    # Status badge
                    status = job.get("status", "").lower()
                    status_color = {
                        "queued": "bg-yellow-100 text-yellow-800",
                        "running": "bg-green-100 text-green-800",
                        "done": "bg-blue-100 text-blue-800",
                        "failed": "bg-red-100 text-red-800",
                        "killed": "bg-gray-100 text-gray-800",
                    }.get(status, "bg-gray-100 text-gray-800")
                    
                    ui.badge(job.get("status", "UNKNOWN").upper(), color=status_color).classes("font-mono text-xs")
                    
                    # Job ID
                    job_id = job.get("job_id", "unknown")
                    ui.label(f"Job: {job_id[:8]}...").classes("font-mono text-sm")
                
                # Season and dataset
                with ui.row().classes("items-center gap-4 text-sm text-gray-600"):
                    ui.label(f"Season: {job.get('season', 'N/A')}")
                    ui.label(f"Dataset: {job.get('dataset_id', 'N/A')}")
            
            # Right: Timestamp
            ui.label(job.get("created_at", "")).classes("text-xs text-gray-500")
        
        # Progress section
        with ui.column().classes("w-full mt-3"):
            # Units progress
            units_done = job.get("units_done", 0)
            units_total = job.get("units_total", 0)
            
            if units_total > 0:
                progress = units_done / units_total
                
                # Progress bar
                with ui.row().classes("w-full items-center gap-2"):
                    ui.linear_progress(progress, show_value=False).classes("flex-1")
                    ui.label(f"{units_done}/{units_total} units").classes("text-sm font-medium")
                
                # Percentage
                ui.label(f"{progress:.1%} complete").classes("text-xs text-gray-600")
            else:
                ui.label("Units: Not calculated").classes("text-sm text-gray-500")
        
        # Footer with actions
        with ui.row().classes("w-full justify-end mt-3 pt-3 border-t"):
            ui.button("View Details",
                     on_click=lambda j=job: ui.navigate.to(f"/jobs/{j.get('job_id', 'unknown')}"),
                     icon="visibility").props("size=sm outline")
            
            # Action buttons based on status
            if status == "running":
                ui.button("Pause", icon="pause", color="warning").props("size=sm outline disabled").tooltip("Not implemented in M1")
            elif status == "queued":
                ui.button("Start", icon="play_arrow", color="positive").props("size=sm outline disabled").tooltip("Not implemented in M1")


def refresh_jobs_list(container: ui.column) -> None:
    """Refresh the jobs list in the container."""
    container.clear()
    
    try:
        bridge = get_jobs_bridge()
        jobs = bridge.list_jobs()
        
        # Apply limit of 50 jobs
        jobs = jobs[:50]
        
        if not jobs:
            with container:
                with ui.card().classes("w-full text-center p-8"):
                    ui.icon("inbox", size="xl").classes("text-gray-400 mb-2")
                    ui.label("No jobs found").classes("text-gray-600")
                    ui.label("Submit a job using the wizard to get started").classes("text-sm text-gray-500")
            return
        
        # Sort jobs: running first, then by creation time
        status_order = {"running": 0, "queued": 1, "done": 2, "failed": 3, "killed": 4}
        jobs.sort(key=lambda j: (status_order.get(j.get("status", "").lower(), 5), j.get("created_at", "")), reverse=True)
        
        # Create job cards
        for job in jobs:
            create_job_card(job)
            
    except Exception as e:
        with container:
            with ui.card().classes("w-full bg-red-50 border-red-200"):
                ui.label("Error loading jobs").classes("text-red-800 font-bold mb-2")
                ui.label(f"Details: {str(e)}").classes("text-red-700 text-sm")
                ui.label("Make sure the control API is running").classes("text-red-700 text-sm")


@ui.page("/jobs")
def jobs_page() -> None:
    """Jobs list page."""
    ui.page_title("FishBroWFS V2 - Jobs")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        # Header
        with ui.row().classes("w-full items-center justify-between mb-6"):
            ui.label("Jobs").classes("text-3xl font-bold")
            
            with ui.row().classes("gap-2"):
                # Refresh button
                refresh_button = ui.button(icon="refresh", color="primary").props("flat")
                
                # New job button
                ui.button("New Job", 
                         on_click=lambda: ui.navigate.to("/wizard"),
                         icon="add",
                         color="positive")
        
        # Stats summary
        with ui.row().classes("w-full gap-4 mb-6"):
            try:
                bridge = get_jobs_bridge()
                jobs = bridge.list_jobs()
                
                # Apply limit of 100 jobs for stats
                jobs = jobs[:100]
                
                # Calculate stats
                total_jobs = len(jobs)
                running_jobs = sum(1 for j in jobs if j.get("status", "").lower() == "running")
                done_jobs = sum(1 for j in jobs if j.get("status", "").lower() == "done")
                total_units = sum(j.get("units_total", 0) for j in jobs)
                completed_units = sum(j.get("units_done", 0) for j in jobs)
                
                # Stats cards
                with ui.card().classes("flex-1"):
                    ui.label("Total Jobs").classes("text-sm text-gray-600")
                    ui.label(str(total_jobs)).classes("text-2xl font-bold")
                
                with ui.card().classes("flex-1"):
                    ui.label("Running").classes("text-sm text-gray-600")
                    ui.label(str(running_jobs)).classes("text-2xl font-bold text-green-600")
                
                with ui.card().classes("flex-1"):
                    ui.label("Completed").classes("text-sm text-gray-600")
                    ui.label(str(done_jobs)).classes("text-2xl font-bold text-blue-600")
                
                with ui.card().classes("flex-1"):
                    ui.label("Units Progress").classes("text-sm text-gray-600")
                    if total_units > 0:
                        progress = completed_units / total_units
                        ui.label(f"{progress:.1%}").classes("text-2xl font-bold")
                    else:
                        ui.label("N/A").classes("text-2xl font-bold")
                        
            except Exception:
                # Fallback if stats can't be loaded
                with ui.card().classes("flex-1"):
                    ui.label("Jobs").classes("text-sm text-gray-600")
                    ui.label("--").classes("text-2xl font-bold")
        
        # Jobs list container
        jobs_container = ui.column().classes("w-full")
        
        # Initial load
        refresh_jobs_list(jobs_container)
        
        # Setup refresh on button click
        def on_refresh():
            refresh_button.props("loading")
            refresh_jobs_list(jobs_container)
            refresh_button.props("loading=false")
        
        refresh_button.on_click(on_refresh)
        
        # Auto-refresh timer for running jobs
        def auto_refresh():
            # Check if any jobs are running
            try:
                bridge = get_jobs_bridge()
                jobs = bridge.list_jobs()
                jobs = jobs[:10]  # Limit to 10 for performance
                has_running = any(j.get("status", "").lower() == "running" for j in jobs)
                if has_running:
                    refresh_jobs_list(jobs_container)
            except Exception:
                pass  # Ignore errors in auto-refresh
        
        ui.timer(5.0, auto_refresh)
        
        # Footer note
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("M1 Jobs List - Shows units_done/units_total for each job")


def register() -> None:
    """Register jobs page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /jobs/list for compatibility
@ui.page("/jobs/list")
def jobs_list_page() -> None:
    """Alternative route for jobs list."""
    jobs_page()