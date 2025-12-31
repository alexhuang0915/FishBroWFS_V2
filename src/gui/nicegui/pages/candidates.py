"""Candidates page - Read-only view with explicit "Not implemented; use CLI" message.

This page is part of Minimum Honest UI: it explicitly declares its limitations
and directs users to CLI for actual functionality.
"""
import logging
from nicegui import ui

from ..layout.cards import render_card
from ..layout.toasts import show_toast, ToastType
from ..constitution.page_shell import page_shell

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True


def render() -> None:
    """Render the Candidates page with explicit truthfulness."""
    
    def render_content():
        ui.label("Candidate Strategies").classes("text-2xl font-bold text-primary mb-6")
        
        # Explicit truth banner
        with ui.card().classes("w-full bg-warning/20 border-warning border-l-4 mb-6"):
            ui.label("⚠️ READ‑ONLY / NOT IMPLEMENTED").classes("text-warning font-bold mb-2")
            ui.label("This UI page is a read‑only prototype. Candidate selection and analysis").classes("text-warning text-sm")
            ui.label("must be performed via CLI commands. No real data is shown.").classes("text-warning text-sm")
        
        # CLI instructions
        with ui.card().classes("w-full mb-6"):
            ui.label("Use CLI Instead").classes("text-lg font-bold mb-2")
            with ui.column().classes("w-full gap-2 font-mono text-sm bg-panel-dark p-4 rounded"):
                ui.label("$ python -m scripts.candidate_analysis --top-k 20 --side long")
                ui.label("$ python -m scripts.export_candidates --format csv --output candidates.csv")
                ui.label("$ python -m scripts.portfolio_select --input candidates.csv")
            ui.label("The CLI provides full functionality with real data.").classes("text-tertiary text-sm mt-2")
        
        # Placeholder data (explicitly labeled as such)
        with ui.card().classes("w-full mb-6"):
            ui.label("Placeholder Data (S1/S2/S3 only)").classes("text-lg font-bold mb-2")
            ui.label("The table below shows example data for demonstration only.").classes("text-tertiary text-sm mb-4")
            
            # Simple static table
            columns = ["Strategy", "Side", "Sharpe", "Win Rate", "Max DD", "Status"]
            rows = [
                ["S1", "Long", "2.45", "62.3%", "-12.4%", "Example"],
                ["S2", "Short", "2.12", "58.7%", "-15.2%", "Example"],
                ["S3", "Long", "1.98", "55.1%", "-18.7%", "Example"],
                ["S1", "Short", "1.87", "60.5%", "-14.3%", "Example"],
                ["S2", "Long", "1.76", "57.2%", "-16.8%", "Example"],
            ]
            
            # Render as simple table
            with ui.column().classes("w-full"):
                # Header
                with ui.row().classes("w-full font-bold border-b border-panel-light pb-2 mb-2"):
                    for col in columns:
                        ui.label(col).classes("flex-1")
                # Rows
                for row in rows:
                    with ui.row().classes("w-full py-2 border-b border-panel-light last:border-0"):
                        for cell in row:
                            ui.label(cell).classes("flex-1")
        
        # Stats cards (explicitly placeholder)
        with ui.row().classes("w-full gap-4 mb-6"):
            render_card(
                title="Total Candidates",
                content="5 (example)",
                icon="stacked_line_chart",
                color="purple",
                width="w-1/3",
            )
            render_card(
                title="Avg Sharpe",
                content="2.04 (example)",
                icon="trending_up",
                color="success",
                width="w-1/3",
            )
            render_card(
                title="Avg Win Rate",
                content="58.8% (example)",
                icon="percent",
                color="cyan",
                width="w-1/3",
            )
        
        # Refresh button that shows explicit message
        def on_refresh():
            show_toast("Candidates page is read‑only. Use CLI for actual data.", ToastType.INFO)
            logger.info("Refresh clicked on read‑only candidates page")
        
        ui.button("Refresh (Read‑Only)", icon="refresh", on_click=on_refresh).classes("mt-4")
        
        # Final note
        ui.label("This page complies with Minimum Honest UI: it does not pretend to be functional.").classes("text-xs text-muted mt-8")
    
    # Wrap in page shell
    page_shell("Candidate Strategies", render_content)
