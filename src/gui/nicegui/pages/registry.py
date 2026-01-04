"""Registry page (Strategy Inventory).

Inventory / Barracks — not an action hub.
Activation is ONLY allowed here (OP cannot activate strategies).

Constitution Requirements:
- Layout: Strategy Name, DATA, TF, Status
- Status Indicator: 🟢 Healthy, 🟡 Warning, 🔴 Disabled / Zombie
- Activation allowed only from this tab
"""
import logging
from typing import List, Dict, Any

from nicegui import ui
from .. import ui_compat as uic

# No longer need render_simple_table
from ..layout.toasts import show_toast, ToastType
from ..state.app_state import AppState
from ..constitution.page_shell import page_shell
from ..layout.navigation import render_top_nav

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True

# Mock data for demonstration
MOCK_STRATEGIES = [
    {
        "name": "S1_TXF_60_L1",
        "data": "TXF",
        "tf": "60",
        "status": "INCUBATION",
        "health": "warning",  # 🟡
        "created": "2026-01-01",
    },
    {
        "name": "S2_MNQ_30_L2", 
        "data": "MNQ",
        "tf": "30",
        "status": "CANDIDATE",
        "health": "healthy",  # 🟢
        "created": "2026-01-02",
    },
    {
        "name": "S3_MES_120_L3",
        "data": "MES",
        "tf": "120",
        "status": "LIVE",
        "health": "healthy",  # 🟢
        "created": "2026-01-01",
    },
    {
        "name": "S1_M2K_240_L1",
        "data": "M2K",
        "tf": "240",
        "status": "RETIRED",
        "health": "disabled",  # 🔴
        "created": "2025-12-30",
    },
    {
        "name": "S2_TXF_60_L2",
        "data": "TXF",
        "tf": "60",
        "status": "INCUBATION",
        "health": "warning",  # 🟡
        "created": "2026-01-02",
    },
]


@ui.page('/registry')
def page_registry():
    """Registry page route."""
    # Render navigation
    render_top_nav('/registry')
    
    # Render page content
    render()


def render() -> None:
    """Render the Registry page."""
    app_state = AppState.get()
    
    def render_content():
        ui.label("Strategy Registry").classes("fb-h1 text-primary")
        ui.label("Inventory / Barracks — Activation allowed ONLY here").classes("fb-sub text-secondary")
        
        # Status legend - compact row
        with ui.row().classes("fb-legend-row items-center gap-4 mb-4 p-3 bg-panel-dark rounded"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("circle").classes("text-green-500 text-sm")
                ui.label("Healthy").classes("text-sm")
            with ui.row().classes("items-center gap-2"):
                ui.icon("circle").classes("text-yellow-500 text-sm")
                ui.label("Warning").classes("text-sm")
            with ui.row().classes("items-center gap-2"):
                ui.icon("circle").classes("text-red-500 text-sm")
                ui.label("Disabled / Zombie").classes("text-sm")
        
        # Strategy table using NiceGUI table with slots for actions
        columns = [
            {"name": "name", "label": "Strategy Name", "field": "name", "align": "left"},
            {"name": "data", "label": "DATA", "field": "data", "align": "left"},
            {"name": "tf", "label": "TF", "field": "tf", "align": "left"},
            {"name": "status", "label": "Status", "field": "status", "align": "left"},
            {"name": "health", "label": "Health", "field": "health", "align": "center"},
            {"name": "created", "label": "Created", "field": "created", "align": "left"},
            {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
        ]
        
        rows_data = []
        for strat in MOCK_STRATEGIES:
            # Determine health icon
            if strat["health"] == "healthy":
                health_icon = "🟢"
            elif strat["health"] == "warning":
                health_icon = "🟡"
            else:  # disabled
                health_icon = "🔴"
            
            # Determine action type based on status (used by slot)
            action_type = None
            if strat["status"] == "INCUBATION":
                action_type = "admit"
            elif strat["status"] == "CANDIDATE":
                action_type = "activate"
            elif strat["status"] == "LIVE":
                action_type = "deactivate"
            else:  # RETIRED or others
                action_type = "none"
            
            rows_data.append({
                "name": strat["name"],
                "data": strat["data"],
                "tf": strat["tf"],
                "status": strat["status"],
                "health": health_icon,
                "created": strat["created"],
                "action_type": action_type,
                "_strategy": strat,  # store original strategy for callback
            })
        
        # Create table with dense styling
        table = ui.table(columns=columns, rows=rows_data).classes("w-full striped hover fb-table-dense")
        table.props("dense flat")
        
        # Add slot for actions column
        table.add_slot(
            "body-cell-actions",
            '''
            <q-td :props="props">
                <q-btn
                    v-if="props.row.action_type === 'admit'"
                    label="Admit"
                    dense flat
                    color="primary"
                    @click="() => $parent.$emit('admit-click', props.row)"
                />
                <q-btn
                    v-else-if="props.row.action_type === 'activate'"
                    label="Activate"
                    dense flat
                    color="positive"
                    @click="() => $parent.$emit('activate-click', props.row)"
                />
                <q-btn
                    v-else-if="props.row.action_type === 'deactivate'"
                    label="Deactivate"
                    dense flat
                    color="warning"
                    @click="() => $parent.$emit('deactivate-click', props.row)"
                />
                <span v-else>—</span>
            </q-td>
            '''
        )
        
        # Handle button clicks
        def on_admit_click(row):
            admit_strategy(row["_strategy"])
        
        def on_activate_click(row):
            activate_strategy(row["_strategy"])
        
        def on_deactivate_click(row):
            deactivate_strategy(row["_strategy"])
        
        table.on("admit-click", on_admit_click)
        table.on("activate-click", on_activate_click)
        table.on("deactivate-click", on_deactivate_click)
        
        # Refresh button - compact
        ui.button(
            "Refresh Registry",
            icon="refresh",
            on_click=lambda: show_toast("Registry refreshed", ToastType.INFO),
            color="primary"
        ).classes("fb-actions")
    
    # Wrap in page shell
    page_shell("Strategy Registry", render_content)


def admit_strategy(strategy: Dict[str, Any]) -> None:
    """Admit an INCUBATION strategy to CANDIDATE status."""
    show_toast(f"Admitted {strategy['name']} → CANDIDATE", ToastType.SUCCESS)
    # In real implementation, would update strategy status in backend


def activate_strategy(strategy: Dict[str, Any]) -> None:
    """Activate a CANDIDATE strategy to LIVE status."""
    show_toast(f"Activated {strategy['name']} → LIVE", ToastType.SUCCESS)
    # Constitution: Activation is ONLY allowed here
    # In real implementation, would update strategy status in backend


def deactivate_strategy(strategy: Dict[str, Any]) -> None:
    """Deactivate a LIVE strategy."""
    show_toast(f"Deactivated {strategy['name']} → CANDIDATE", ToastType.WARNING)
    # In real implementation, would update strategy status in backend