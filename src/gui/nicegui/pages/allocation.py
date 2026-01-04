"""Allocation page (Read-only).

Reality check — detect fake diversification.
NO controls. NO suggestions. NO automation.

Constitution Requirements:
- Instrument exposure (Treemap / stacked bar)
- Time Frame distribution
- Long / Short ratio
- Read-only cards only
"""
import logging
from typing import Dict, Any

from nicegui import ui
from .. import ui_compat as uic

from ..layout.cards import render_card
from ..state.app_state import AppState
from ..constitution.page_shell import page_shell
from ..layout.navigation import render_top_nav

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True

# Mock data for demonstration
MOCK_ALLOCATION_DATA = {
    "instrument_exposure": {
        "TXF": 0.35,
        "MNQ": 0.25,
        "MES": 0.20,
        "MYM": 0.15,
        "M2K": 0.05,
    },
    "timeframe_distribution": {
        "15": 0.10,
        "30": 0.25,
        "60": 0.40,
        "120": 0.20,
        "240": 0.05,
    },
    "long_short_ratio": {
        "long": 0.65,
        "short": 0.35,
    },
    "strategy_family_distribution": {
        "S1": 0.40,
        "S2": 0.35,
        "S3": 0.25,
    },
}


@ui.page('/allocation')
def page_allocation():
    """Allocation page route."""
    # Render navigation
    render_top_nav('/allocation')
    
    # Render page content
    render()


def render() -> None:
    """Render the Allocation page."""
    app_state = AppState.get()
    
    def render_content():
        ui.label("Allocation").classes("text-2xl font-bold text-primary mb-2")
        ui.label("Reality check — detect fake diversification (Read-only)").classes("text-secondary mb-6")
        
        # Warning: Read-only
        with ui.card().classes("w-full bg-yellow-900/20 border-yellow-700 p-4 mb-6"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("warning").classes("text-yellow-500")
                ui.label("READ-ONLY").classes("font-bold text-yellow-500")
            ui.label("NO controls. NO suggestions. NO automation.").classes("text-yellow-400 text-sm")
        
        # Card grid
        with ui.grid(columns=2).classes("w-full gap-6"):
            # Card A: Instrument Exposure
            with ui.card().classes("w-full bg-panel-dark p-6"):
                ui.label("Instrument Exposure").classes("text-lg font-bold text-primary mb-4")
                
                # Stacked bar visualization (simplified)
                total = sum(MOCK_ALLOCATION_DATA["instrument_exposure"].values())
                for instrument, value in MOCK_ALLOCATION_DATA["instrument_exposure"].items():
                    percentage = (value / total) * 100 if total > 0 else 0
                    with ui.row().classes("w-full items-center mb-2"):
                        ui.label(instrument).classes("w-16 text-sm")
                        ui.linear_progress(value=value, show_value=False).classes("flex-1")
                        ui.label(f"{percentage:.1f}%").classes("w-16 text-right text-sm")
            
            # Card B: Time Frame Distribution
            with ui.card().classes("w-full bg-panel-dark p-6"):
                ui.label("Time Frame Distribution").classes("text-lg font-bold text-primary mb-4")
                
                for tf, value in MOCK_ALLOCATION_DATA["timeframe_distribution"].items():
                    percentage = value * 100
                    with ui.row().classes("w-full items-center mb-2"):
                        ui.label(f"{tf}m").classes("w-16 text-sm")
                        ui.linear_progress(value=value, show_value=False).classes("flex-1")
                        ui.label(f"{percentage:.1f}%").classes("w-16 text-right text-sm")
            
            # Card C: Long/Short Ratio
            with ui.card().classes("w-full bg-panel-dark p-6"):
                ui.label("Long/Short Ratio").classes("text-lg font-bold text-primary mb-4")
                
                long_pct = MOCK_ALLOCATION_DATA["long_short_ratio"]["long"] * 100
                short_pct = MOCK_ALLOCATION_DATA["long_short_ratio"]["short"] * 100
                
                # Visual representation
                with ui.row().classes("w-full h-8 mb-2 rounded overflow-hidden"):
                    ui.element('div').style(f"width: {long_pct}%; background-color: #4CAF50;")
                    ui.element('div').style(f"width: {short_pct}%; background-color: #F44336;")
                
                with ui.row().classes("w-full justify-between"):
                    with ui.column().classes("items-center"):
                        ui.icon("trending_up").classes("text-green-500 text-2xl")
                        ui.label(f"Long: {long_pct:.1f}%").classes("text-sm")
                    with ui.column().classes("items-center"):
                        ui.icon("trending_down").classes("text-red-500 text-2xl")
                        ui.label(f"Short: {short_pct:.1f}%").classes("text-sm")
            
            # Card D: Strategy Family Distribution
            with ui.card().classes("w-full bg-panel-dark p-6"):
                ui.label("Strategy Family Distribution").classes("text-lg font-bold text-primary mb-4")
                
                for family, value in MOCK_ALLOCATION_DATA["strategy_family_distribution"].items():
                    percentage = value * 100
                    with ui.row().classes("w-full items-center mb-2"):
                        ui.label(family).classes("w-16 text-sm")
                        ui.linear_progress(value=value, show_value=False).classes("flex-1")
                        ui.label(f"{percentage:.1f}%").classes("w-16 text-right text-sm")
        
        # Summary statistics
        with ui.card().classes("w-full bg-panel-dark p-6 mt-6"):
            ui.label("Portfolio Summary").classes("text-lg font-bold text-primary mb-4")
            
            with ui.grid(columns=4).classes("w-full gap-4"):
                render_card(
                    title="Total Strategies",
                    content="24",
                    icon="account_balance",
                    color="blue",
                    width="w-full",
                )
                render_card(
                    title="Live Strategies",
                    content="18",
                    icon="play_circle",
                    color="green",
                    width="w-full",
                )
                render_card(
                    title="Avg Correlation",
                    content="0.12",
                    icon="show_chart",
                    color="cyan",
                    width="w-full",
                )
                render_card(
                    title="Max Drawdown",
                    content="-8.5%",
                    icon="trending_down",
                    color="orange",
                    width="w-full",
                )
        
        # Constitution reminder
        with ui.card().classes("w-full bg-gray-900/50 p-4 mt-6"):
            ui.label("Constitution Compliance").classes("text-sm font-bold text-gray-400 mb-2")
            ui.label("This tab is READ-ONLY. No controls, suggestions, or automation allowed.").classes("text-xs text-gray-500")
    
    # Wrap in page shell
    page_shell("Allocation", render_content)