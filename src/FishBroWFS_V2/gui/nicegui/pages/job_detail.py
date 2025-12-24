"""Job Detail Page for M1.

Display real-time status + log tail for a specific job.
"""

from __future__ import annotations

import json
from typing import Dict, Any

from nicegui import ui

from FishBroWFS_V2.control.job_api import get_job_summary, get_job_status
from FishBroWFS_V2.control.pipeline_runner import check_job_status, start_job_async


def create_status_badge(status: str) -> ui.badge:
    """Create a status badge with appropriate color."""
    status_lower = status.lower()
    
    color_map = {
        "queued": "yellow",
        "running": "green",
        "done": "blue",
        "failed": "red",
        "killed": "gray",
    }
    
    color = color_map.get(status_lower, "gray")
    return ui.badge(status.upper(), color=color).classes("text-sm font-bold")


def create_units_progress(units_done: int, units_total: int) -> None:
    """Create units progress display."""
    if units_total <= 0:
        ui.label("Units: Not calculated").classes("text-gray-600")
        return
    
    progress = units_done / units_total
    
    with ui.column().classes("w-full"):
        # Progress bar
        with ui.row().classes("w-full items-center gap-2"):
            ui.linear_progress(progress, show_value=False).classes("flex-1")
            ui.label(f"{units_done}/{units_total}").classes("text-sm font-medium")
        
        # Percentage and formula
        ui.label(f"{progress:.1%} complete").classes("text-xs text-gray-600")
        
        # Formula explanation (if we have the breakdown)
        if units_total > 0 and units_done < units_total:
            remaining = units_total - units_done
            ui.label(f"{remaining} units remaining").classes("text-xs text-gray-500")


def refresh_job_detail(job_id: str, 
                      status_container: ui.column,
                      logs_container: ui.column,
                      config_container: ui.column) -> None:
    """Refresh job detail information."""
    try:
        # Get job summary
        summary = get_job_summary(job_id)
        
        # Update status container
        status_container.clear()
        with status_container:
            # Status badge and basic info
            with ui.row().classes("w-full items-center gap-4 mb-4"):
                create_status_badge(summary["status"])
                
                ui.label(f"Job ID: {summary['job_id'][:8]}...").classes("font-mono")
                ui.label(f"Season: {summary.get('season', 'N/A')}").classes("text-gray-600")
                ui.label(f"Created: {summary.get('created_at', 'N/A')}").classes("text-gray-600")
            
            # Units progress
            ui.label("Units Progress").classes("font-bold mt-4 mb-2")
            units_done = summary.get("units_done", 0)
            units_total = summary.get("units_total", 0)
            create_units_progress(units_done, units_total)
            
            # Action buttons based on status
            with ui.row().classes("w-full gap-2 mt-4"):
                if summary["status"].lower() == "queued":
                    ui.button("Start Job", 
                             on_click=lambda: start_job_async(job_id),
                             icon="play_arrow",
                             color="positive").tooltip("Start job execution")
                
                ui.button("Refresh", 
                         icon="refresh",
                         on_click=lambda: refresh_job_detail(job_id, status_container, logs_container, config_container))
                
                ui.button("Back to Jobs",
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="arrow_back",
                         color="gray").props("outline")
        
        # Update logs container
        logs_container.clear()
        with logs_container:
            ui.label("Logs").classes("font-bold mb-2")
            
            logs = summary.get("logs", [])
            if logs:
                # Show last 20 lines
                log_text = "\n".join(logs[-20:])
                log_display = ui.textarea(log_text).classes("w-full h-64 font-mono text-xs").props("readonly")
                
                # Auto-scroll to bottom
                ui.run_javascript(f"""
                    const textarea = document.getElementById('{log_display.id}');
                    if (textarea) {{
                        textarea.scrollTop = textarea.scrollHeight;
                    }}
                """)
            else:
                ui.label("No logs available").classes("text-gray-500 italic")
        
        # Update config container
        config_container.clear()
        with config_container:
            ui.label("Configuration").classes("font-bold mb-2")
            
            # Show basic config info
            with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                ui.label("Job ID:").classes("font-medium")
                ui.label(summary["job_id"]).classes("font-mono text-xs")
                
                ui.label("Status:").classes("font-medium")
                ui.label(summary["status"].upper())
                
                ui.label("Season:").classes("font-medium")
                ui.label(summary.get("season", "N/A"))
                
                ui.label("Dataset:").classes("font-medium")
                ui.label(summary.get("dataset_id", "N/A"))
                
                ui.label("Created:").classes("font-medium")
                ui.label(summary.get("created_at", "N/A"))
                
                ui.label("Updated:").classes("font-medium")
                ui.label(summary.get("updated_at", "N/A"))
                
                ui.label("Units Done:").classes("font-medium")
                ui.label(str(summary.get("units_done", 0)))
                
                ui.label("Units Total:").classes("font-medium")
                ui.label(str(summary.get("units_total", 0)))
            
            # Show raw config if available
            if "config" in summary:
                ui.label("Raw Configuration:").classes("font-medium mt-4 mb-2")
                config_json = json.dumps(summary["config"], indent=2)
                ui.textarea(config_json).classes("w-full h-48 font-mono text-xs").props("readonly")
    
    except Exception as e:
        status_container.clear()
        with status_container:
            with ui.card().classes("w-full bg-red-50 border-red-200"):
                ui.label("Error loading job details").classes("text-red-800 font-bold mb-2")
                ui.label(f"Details: {str(e)}").classes("text-red-700 text-sm")
                
                ui.button("Back to Jobs",
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="arrow_back",
                         color="red").props("outline").classes("mt-2")


@ui.page("/jobs/{job_id}")
def job_detail_page(job_id: str) -> None:
    """Job detail page."""
    ui.page_title(f"FishBroWFS V2 - Job {job_id[:8]}...")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        # Header
        with ui.row().classes("w-full items-center justify-between mb-6"):
            ui.label(f"Job Details").classes("text-3xl font-bold")
            
            with ui.row().classes("gap-2"):
                ui.button("Jobs List", 
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="list",
                         color="gray").props("outline")
        
        # Create containers for dynamic content
        status_container = ui.column().classes("w-full mb-6")
        logs_container = ui.column().classes("w-full mb-6")
        config_container = ui.column().classes("w-full")
        
        # Initial load
        refresh_job_detail(job_id, status_container, logs_container, config_container)
        
        # Auto-refresh timer for running jobs
        def auto_refresh():
            try:
                # Check if job is still running
                status = get_job_status(job_id)
                if status["status"].lower() == "running":
                    refresh_job_detail(job_id, status_container, logs_container, config_container)
            except Exception:
                pass  # Ignore errors in auto-refresh
        
        ui.timer(3.0, auto_refresh)
        
        # Footer note
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("M1 Job Detail - Shows real-time status and log tail")


def register() -> None:
    """Register job detail page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /job/{job_id} for compatibility
@ui.page("/job/{job_id}")
def job_detail_alt_page(job_id: str) -> None:
    """Alternative route for job detail."""
    job_detail_page(job_id)