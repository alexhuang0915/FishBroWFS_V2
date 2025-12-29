"""Portfolio page - Human selects instances, assigns weights."""
from nicegui import ui

from ..layout.cards import render_card
from ..layout.tables import render_simple_table


def render() -> None:
    """Render the Portfolio page."""
    ui.label("Portfolio Construction").classes("text-2xl font-bold text-primary mb-6")
    ui.label("Select candidate instances and assign weights. No auto‑balancing.").classes("text-secondary mb-8")
    
    # Available candidates panel
    with ui.row().classes("w-full gap-8"):
        with ui.column().classes("w-1/2"):
            ui.label("Available Candidates").classes("text-lg font-bold mb-2")
            columns = ["Select", "Strategy ID", "Side", "Sharpe", "Weight"]
            rows = [
                [True, "L7", "Long", "2.45", "0%"],
                [False, "S3", "Short", "2.12", "0%"],
                [False, "L2", "Long", "1.98", "0%"],
                [True, "S8", "Short", "1.87", "0%"],
                [False, "L5", "Long", "1.76", "0%"],
            ]
            # Store checkboxes for validation
            candidate_checkboxes = []
            # Simulate table with checkboxes
            with ui.column().classes("w-full bg-panel-dark rounded-lg p-4"):
                for idx, row in enumerate(rows):
                    with ui.row().classes("w-full items-center py-2 border-b border-panel-light last:border-0"):
                        cb = ui.checkbox(value=row[0])
                        candidate_checkboxes.append((cb, row[1], row[2]))  # store checkbox, id, side
                        ui.label(row[1]).classes("w-1/4")
                        ui.label(row[2]).classes("w-1/4")
                        ui.label(row[3]).classes("w-1/4")
                        ui.label(row[4]).classes("w-1/4")
        
        # Weight assignment panel
        with ui.column().classes("w-1/2"):
            ui.label("Portfolio Weights").classes("text-lg font-bold mb-2")
            ui.label("Adjust sliders to assign weights (must sum to 100%).").classes("text-sm text-tertiary mb-4")
            # Example weight sliders (only for selected candidates L7 and S8)
            with ui.column().classes("w-full gap-4"):
                with ui.row().classes("w-full items-center"):
                    ui.label("L7 (Long)").classes("w-1/3")
                    slider_l7 = ui.slider(min=0, max=100, value=40).classes("w-1/3")
                    ui.label().bind_text_from(slider_l7, "value", lambda v: f"{v}%")
                with ui.row().classes("w-full items-center"):
                    ui.label("S8 (Short)").classes("w-1/3")
                    slider_s8 = ui.slider(min=0, max=100, value=60).classes("w-1/3")
                    ui.label().bind_text_from(slider_s8, "value", lambda v: f"{v}%")
                ui.label("Total: 100%").classes("font-bold")
    
    # Validation banner (initially hidden)
    validation_banner = ui.column().classes("w-full mb-6")
    
    # Portfolio metrics
    with ui.row().classes("w-full gap-4 mt-8"):
        sharpe_card = render_card(
            title="Portfolio Sharpe",
            content="1.89",
            icon="trending_up",
            color="success",
            width="w-1/4",
        )
        return_card = render_card(
            title="Expected Return",
            content="12.4%",
            icon="show_chart",
            color="cyan",
            width="w-1/4",
        )
        drawdown_card = render_card(
            title="Max Drawdown",
            content="-18.2%",
            icon="warning",
            color="warning",
            width="w-1/4",
        )
        correlation_card = render_card(
            title="Correlation",
            content="0.32",
            icon="link",
            color="purple",
            width="w-1/4",
        )
    
    # Action buttons
    with ui.row().classes("w-full gap-4 mt-8"):
        save_btn = ui.button("Save Portfolio", icon="save", color="primary")
        load_btn = ui.button("Load Previous", icon="upload")
        export_btn = ui.button("Export Spec", icon="download")
        validate_btn = ui.button("Validate", icon="check_circle")
    
    # Note
    ui.label("Portfolio is human‑selected only. Machine does NOT auto‑balance.").classes("text-xs text-muted mt-8")
    
    # Validation logic
    def validate_portfolio():
        """Run validation and update banner."""
        # Collect selected candidates
        selected = []
        for cb, sid, side in candidate_checkboxes:
            if cb.value:
                selected.append((sid, side))
        
        # Compute total weight
        total_weight = slider_l7.value + slider_s8.value
        weight_ok = abs(total_weight - 100.0) < 0.1
        
        # Compute exposure
        long_weight = slider_l7.value if "L7" in [s[0] for s in selected] else 0.0
        short_weight = slider_s8.value if "S8" in [s[0] for s in selected] else 0.0
        
        # Validation reasons
        reasons = []
        if not selected:
            reasons.append("No candidate selected.")
        if not weight_ok:
            reasons.append(f"Total weight {total_weight:.1f}% must equal 100%.")
        # Additional rules can be added
        
        is_valid = len(reasons) == 0
        
        # Exposure summary
        exposure_summary = f"Long: {long_weight:.1f}%, Short: {short_weight:.1f}%"
        
        # Update banner
        validation_banner.clear()
        with validation_banner:
            if is_valid:
                with ui.card().classes("w-full bg-success/10 border-success border-l-4"):
                    ui.label("✅ Portfolio valid").classes("text-success font-medium")
                    ui.label(f"Exposure: {exposure_summary}").classes("text-success text-sm")
            else:
                with ui.card().classes("w-full bg-warning/10 border-warning border-l-4"):
                    ui.label("⚠️ Portfolio validation failed").classes("text-warning font-medium")
                    for reason in reasons:
                        ui.label(f"• {reason}").classes("text-warning text-sm")
                    ui.label(f"Exposure: {exposure_summary}").classes("text-warning text-sm")
        
        # Update save button state
        save_btn.disable = not is_valid
        if is_valid:
            save_btn.props(remove="disabled")
        else:
            save_btn.props("disabled")
        
        return is_valid, reasons, exposure_summary
    
    # Attach validation to button click
    validate_btn.on("click", validate_portfolio)
    
    # Also validate on slider change (optional)
    slider_l7.on("change", validate_portfolio)
    slider_s8.on("change", validate_portfolio)
    for cb, _, _ in candidate_checkboxes:
        cb.on("change", validate_portfolio)
    
    # Initial validation
    validate_portfolio()