"""Portfolio page - Read-only prototype with explicit "Not implemented; use CLI" message.

This page is part of Minimum Honest UI: it explicitly declares its limitations
and directs users to CLI for actual portfolio construction.
"""
from nicegui import ui

from ..layout.cards import render_card
from ..layout.toasts import show_toast, ToastType
from ..constitution.page_shell import page_shell

# Page shell compliance flag
PAGE_SHELL_ENABLED = True


def render() -> None:
    """Render the Portfolio page with explicit truthfulness."""
    
    def render_content():
        ui.label("Portfolio Construction").classes("text-2xl font-bold text-primary mb-6")
        
        # Explicit truth banner
        with ui.card().classes("w-full bg-warning/20 border-warning border-l-4 mb-6"):
            ui.label("⚠️ PROTOTYPE / NOT IMPLEMENTED").classes("text-warning font-bold mb-2")
            ui.label("Portfolio construction must be performed via CLI commands.").classes("text-warning text-sm")
            ui.label("This UI page is a read‑only prototype showing example data only.").classes("text-warning text-sm")
        
        # CLI instructions
        with ui.card().classes("w-full mb-6"):
            ui.label("Use CLI Instead").classes("text-lg font-bold mb-2")
            with ui.column().classes("w-full gap-2 font-mono text-sm bg-panel-dark p-4 rounded"):
                ui.label("$ python -m scripts.portfolio_build --candidates candidates.csv")
                ui.label("$ python -m scripts.portfolio_optimize --method mvo --risk MEDIUM")
                ui.label("$ python -m scripts.portfolio_export --format json --output portfolio.json")
            ui.label("The CLI provides full portfolio construction and optimization.").classes("text-tertiary text-sm mt-2")
        
        # Example portfolio (clearly labeled as example)
        with ui.card().classes("w-full mb-6"):
            ui.label("Example Portfolio (S1/S2/S3 only)").classes("text-lg font-bold mb-2")
            ui.label("This is a static example for demonstration. Weights are not editable.").classes("text-tertiary text-sm mb-4")
            
            # Static portfolio table
            columns = ["Strategy", "Side", "Weight", "Sharpe", "Status"]
            rows = [
                ["S1", "Long", "40%", "2.45", "Example"],
                ["S1", "Short", "60%", "1.87", "Example"],
                ["S2", "Long", "0%", "1.76", "Not selected"],
                ["S2", "Short", "0%", "2.12", "Not selected"],
                ["S3", "Long", "0%", "1.98", "Not selected"],
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
            
            # Total weight note
            ui.label("Total weight: 100% (example only)").classes("text-sm text-tertiary mt-4")
        
        # Portfolio metrics (example)
        with ui.row().classes("w-full gap-4 mt-8"):
            render_card(
                title="Portfolio Sharpe",
                content="1.89 (example)",
                icon="trending_up",
                color="success",
                width="w-1/4",
            )
            render_card(
                title="Expected Return",
                content="12.4% (example)",
                icon="show_chart",
                color="cyan",
                width="w-1/4",
            )
            render_card(
                title="Max Drawdown",
                content="-18.2% (example)",
                icon="warning",
                color="warning",
                width="w-1/4",
            )
            render_card(
                title="Correlation",
                content="0.32 (example)",
                icon="link",
                color="purple",
                width="w-1/4",
            )
        
        # Action buttons that show explicit messages
        def on_save():
            show_toast("Portfolio saving not implemented. Use CLI instead.", ToastType.INFO)
        
        def on_load():
            show_toast("Portfolio loading not implemented. Use CLI instead.", ToastType.INFO)
        
        def on_export():
            show_toast("Portfolio export not implemented. Use CLI instead.", ToastType.INFO)
        
        def on_validate():
            show_toast("Portfolio validation not implemented. Use CLI instead.", ToastType.INFO)
        
        with ui.row().classes("w-full gap-4 mt-8"):
            ui.button("Save (Read‑Only)", icon="save", on_click=on_save)
            ui.button("Load (Read‑Only)", icon="upload", on_click=on_load)
            ui.button("Export (Read‑Only)", icon="download", on_click=on_export)
            ui.button("Validate (Read‑Only)", icon="check_circle", on_click=on_validate)
        
        # Final note
        ui.label("This page complies with Minimum Honest UI: all limitations are explicitly declared.").classes("text-xs text-muted mt-8")
    
    # Wrap in page shell
    page_shell("Portfolio Construction", render_content)
