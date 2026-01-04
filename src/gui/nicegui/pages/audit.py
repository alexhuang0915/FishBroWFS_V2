"""Audit page (Historian).

Immutable historical record.
All Run / Accept / Activate actions timestamped.
Audit NEVER participates in decisions.

Constitution Requirements:
- Query-only interface
- Timestamped audit log
- No participation in decisions
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

from nicegui import ui
from .. import ui_compat as uic

from ..layout.tables import render_simple_table
from ..state.app_state import AppState
from ..constitution.page_shell import page_shell
from ..layout.navigation import render_top_nav

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True

# Mock audit data
def generate_mock_audit_log() -> List[Dict[str, Any]]:
    """Generate mock audit log data."""
    base_time = datetime.now() - timedelta(days=7)
    events = []
    
    event_types = ["RUN", "ACCEPT", "ACTIVATE", "DEACTIVATE", "ADMIT", "DROP"]
    users = ["operator", "researcher", "system"]
    strategies = ["S1_TXF_60_L1", "S2_MNQ_30_L2", "S3_MES_120_L3", "S1_M2K_240_L1"]
    
    for i in range(50):
        event_time = base_time + timedelta(hours=i*3)
        event_type = event_types[i % len(event_types)]
        user = users[i % len(users)]
        strategy = strategies[i % len(strategies)]
        
        if event_type == "RUN":
            message = f"Backtest run: {strategy} (TF: 60, DATA: TXF)"
        elif event_type == "ACCEPT":
            message = f"Result accepted → Registry: {strategy} (Status: INCUBATION)"
        elif event_type == "ACTIVATE":
            message = f"Strategy activated: {strategy} → LIVE"
        elif event_type == "DEACTIVATE":
            message = f"Strategy deactivated: {strategy} → CANDIDATE"
        elif event_type == "ADMIT":
            message = f"Strategy admitted: {strategy} → CANDIDATE"
        else:  # DROP
            message = f"Strategy dropped: {strategy} → RETIRED"
        
        events.append({
            "timestamp": event_time.isoformat(),
            "event_type": event_type,
            "user": user,
            "strategy": strategy,
            "message": message,
        })
    
    # Sort by timestamp descending (newest first)
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events


@ui.page('/audit')
def page_audit():
    """Audit page route."""
    # Render navigation
    render_top_nav('/audit')
    
    # Render page content
    render()


def render() -> None:
    """Render the Audit page."""
    app_state = AppState.get()
    
    def render_content():
        ui.label("Audit").classes("text-2xl font-bold text-primary mb-2")
        ui.label("Immutable historical record — Audit NEVER participates in decisions").classes("text-secondary mb-6")
        
        # Warning: Query-only
        with ui.card().classes("w-full bg-blue-900/20 border-blue-700 p-4 mb-6"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("history").classes("text-blue-500")
                ui.label("QUERY-ONLY").classes("font-bold text-blue-500")
            ui.label("Audit NEVER participates in decisions. No actions allowed.").classes("text-blue-400 text-sm")
        
        # Filter controls (query-only, no actions)
        with ui.card().classes("w-full bg-panel-dark p-6 mb-6"):
            ui.label("Query Filters").classes("text-lg font-bold text-primary mb-4")
            
            with ui.grid(columns=4).classes("w-full gap-4"):
                # Event type filter
                event_type_select = uic.select(
                    "Event Type",
                    ["ALL", "RUN", "ACCEPT", "ACTIVATE", "DEACTIVATE", "ADMIT", "DROP"],
                    value="ALL"
                ).classes("w-full")
                
                # User filter
                user_select = uic.select(
                    "User",
                    ["ALL", "operator", "researcher", "system"],
                    value="ALL"
                ).classes("w-full")
                
                # Date range
                date_from = uic.input_text(
                    "From Date",
                    value=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                ).classes("w-full")
                
                date_to = uic.input_text(
                    "To Date",
                    value=datetime.now().strftime("%Y-%m-%d")
                ).classes("w-full")
            
            # Search button (query only)
            ui.button(
                "Query Audit Log",
                icon="search",
                on_click=lambda: query_audit_log(event_type_select.value, user_select.value, date_from.value, date_to.value),
                color="primary"
            ).classes("mt-2")
        
        # Audit log table
        ui.label("Audit Log").classes("text-xl font-bold mb-4")
        
        # Generate mock data
        audit_log = generate_mock_audit_log()
        
        # Table columns
        columns = [
            "Timestamp (UTC)",
            "Event Type",
            "User",
            "Strategy",
            "Message",
        ]
        
        # Table rows
        rows = []
        for event in audit_log[:20]:  # Show first 20
            # Format timestamp
            ts = datetime.fromisoformat(event["timestamp"].replace('Z', '+00:00'))
            formatted_ts = ts.strftime("%Y-%m-%d %H:%M:%S")
            
            # Determine color based on event type
            color_class = ""
            if event["event_type"] == "RUN":
                color_class = "text-cyan-500"
            elif event["event_type"] == "ACCEPT":
                color_class = "text-green-500"
            elif event["event_type"] == "ACTIVATE":
                color_class = "text-positive"
            elif event["event_type"] == "DEACTIVATE":
                color_class = "text-warning"
            elif event["event_type"] == "ADMIT":
                color_class = "text-blue-500"
            else:  # DROP
                color_class = "text-negative"
            
            rows.append([
                formatted_ts,
                event["event_type"],  # plain string instead of UI label
                event["user"],
                event["strategy"],
                event["message"],
            ])
        
        # Render table
        render_simple_table(columns, rows, striped=True, hover=True)
        
        # Pagination info
        with ui.row().classes("w-full justify-between items-center mt-4"):
            ui.label(f"Showing 20 of {len(audit_log)} audit events").classes("text-tertiary text-sm")
            
            # Pagination buttons (query-only)
            with ui.row().classes("gap-2"):
                ui.button(
                    "← Previous",
                    on_click=lambda: ui.notify("Query: Previous page"),
                    color="primary"
                ).props("flat")
                ui.button(
                    "Next →",
                    on_click=lambda: ui.notify("Query: Next page"),
                    color="primary"
                ).props("flat")
        
        # Export button (read-only export)
        ui.button(
            "Export Audit Log (CSV)",
            icon="download",
            on_click=lambda: export_audit_log(),
            color="secondary"
        ).classes("mt-4")
    
    # Wrap in page shell
    page_shell("Audit", render_content)


def query_audit_log(event_type: str, user: str, date_from: str, date_to: str) -> None:
    """Query audit log (mock implementation)."""
    # This is a query-only function - no modifications
    ui.notify(f"Query: event_type={event_type}, user={user}, date_from={date_from}, date_to={date_to}", type="info")
    # In real implementation, would fetch filtered audit data from backend


def export_audit_log() -> None:
    """Export audit log to CSV (read-only)."""
    ui.notify("Exporting audit log to CSV (read-only)", type="info")
    # In real implementation, would generate CSV download