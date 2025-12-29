"""Deploy page - explicit confirmation."""
from nicegui import ui

from ..layout.cards import render_card
from ..layout.toasts import show_toast, ToastType
from ..services.status_service import get_status, get_state, get_summary
from ..state.portfolio_state import PortfolioState
from .. import ui_compat as ui_compat
button = ui_compat.button
select = ui_compat.select
input_text = ui_compat.input_text
checkbox = ui_compat.checkbox
register_element = ui_compat.register_element


def render() -> None:
    """Render the Deploy page."""
    # If backend is offline, render a warning card (still render rest of UI)
    state = get_state()
    if state != "ONLINE":
        render_card(
            title="Deploy Unavailable",
            content=f"Deploy is disabled: {get_summary()}",
            color="warning",
        )
        # Continue rendering the rest of the UI (it will be non‑functional but visible)
    
    ui.label("Deploy Configuration").classes("text-2xl font-bold text-primary mb-6")
    ui.label("Explicit confirmation required. No silent action.").classes("text-secondary mb-8")
    
    # Deployment target selection
    with ui.row().classes("w-full gap-4 mb-6"):
        target_select = select(
            "Target",
            ["Live Trading", "Paper Trading", "Backtest Only"],
            value="Paper Trading",
            classes="w-1/3"
        )
        account_input = input_text(
            "Account ID",
            placeholder="Enter account ID",
            classes="w-1/3"
        )
        env_input = input_text(
            "Environment",
            value="staging",
            classes="w-1/3"
        )
    
    # Configuration summary
    with render_card(title="Configuration Summary", content="") as card:
        with ui.column().classes("w-full gap-2"):
            ui.label("Portfolio: L7 (40%), S8 (60%)")
            ui.label("Risk Budget: MEDIUM")
            ui.label("Margin Model: Symbolic")
            ui.label("Contract Specs: {}")
            ui.label("Execution Mode: LIMIT orders only")
    
    # Safety checks
    with ui.column().classes("w-full gap-4 mb-6"):
        ui.label("Safety Checks").classes("text-lg font-bold")
        check_review = checkbox("I have reviewed the portfolio weights")
        check_risk = checkbox("I understand the risk budget")
        check_margin = checkbox("I confirm that margin requirements are satisfied")
        check_rollback = checkbox("I accept that deployment cannot be automatically rolled back")
        check_human = checkbox("I am the sole human operator")
        safety_checks = [check_review, check_risk, check_margin, check_rollback, check_human]
    
    # Disable reasons banner
    disable_banner = ui.column().classes("w-full mb-6")
    
    # Deployment actions
    with ui.row().classes("w-full gap-4"):
        validate_btn = button("Validate Deployment", icon="check_circle", color="warning").classes("flex-grow")
        export_btn = button("Export Config", icon="download", color="transparent").classes("flex-grow")
        deploy_btn = button("Deploy Now", icon="rocket_launch", color="danger").classes("flex-grow")
    
    # Log output placeholder
    with render_card(title="Deployment Log", content="") as card:
        log_textarea = ui.textarea("Waiting for deployment...").props("readonly").classes("w-full h-48 font-mono text-sm")
        with ui.row().classes("w-full justify-end gap-2"):
            clear_btn = button("Clear Log", icon="clear")
            copy_btn = button("Copy Log", icon="content_copy")
    
    # Warning
    with render_card(title="⚠️ Deployment is irreversible", content="", color="warning") as card:
        ui.label("Once deployed, the system will start trading with real capital (if live). Ensure all checks are complete.").classes("text-sm")
    
    # Validation logic
    def compute_disable_reasons() -> list[str]:
        """Return ordered list of reasons why deployment is disabled (empty list = enabled)."""
        reasons = []
        status = get_status()
        portfolio_state = PortfolioState()
        
        # 1. Backend offline
        if not status.backend_up:
            reasons.append("Backend offline")
        
        # 2. Portfolio not saved (no selected items)
        if not portfolio_state.selected_items:
            reasons.append("No portfolio saved")
        
        # 3. Safety checks incomplete
        if not all(cb.value for cb in safety_checks):
            reasons.append("Safety checks incomplete")
        
        # 4. Missing target
        if not target_select.value:
            reasons.append("Deployment target not selected")
        
        # 5. Missing account ID (optional? but require)
        if not account_input.value:
            reasons.append("Account ID missing")
        
        # Deterministic priority order (already as above)
        return reasons
    
    def update_deploy_button():
        """Update deploy button state and show banner."""
        reasons = compute_disable_reasons()
        disable_banner.clear()
        if reasons:
            with disable_banner:
                card = ui.card().classes("w-full bg-warning/10 border-warning border-l-4")
                register_element("cards", card)
                with card:
                    ui.label("⚠️ Deployment disabled").classes("text-warning font-medium")
                    for reason in reasons:
                        ui.label(f"• {reason}").classes("text-warning text-sm")
            deploy_btn.disable = True
            deploy_btn.props("disabled")
        else:
            deploy_btn.disable = False
            deploy_btn.props(remove="disabled")
    
    def on_validate():
        """Validate deployment configuration."""
        reasons = compute_disable_reasons()
        if reasons:
            show_toast(f"Deployment validation failed: {', '.join(reasons)}", ToastType.WARNING)
        else:
            show_toast("Deployment configuration is valid.", ToastType.SUCCESS)
    
    def on_deploy():
        """Trigger deployment (placeholder)."""
        from ..services.deploy_service import trigger_deployment
        config = {
            "target": target_select.value,
            "account_id": account_input.value,
            "environment": env_input.value,
            "portfolio_id": "placeholder",  # should be real portfolio ID
        }
        result = trigger_deployment(config)
        log_textarea.value = f"Deployment triggered: {result['message']}"
        show_toast(f"Deployment triggered: {result['deployment_id']}", ToastType.INFO)
    
    # Attach event handlers
    validate_btn.on("click", on_validate)
    deploy_btn.on("click", on_deploy)
    clear_btn.on("click", lambda: setattr(log_textarea, 'value', ''))
    copy_btn.on("click", lambda: ui.run_javascript(f"navigator.clipboard.writeText(`{log_textarea.value}`)"))
    
    # Update on changes
    target_select.on("change", update_deploy_button)
    account_input.on("change", update_deploy_button)
    env_input.on("change", update_deploy_button)
    for cb in safety_checks:
        cb.on("change", update_deploy_button)
    
    # Initial update
    update_deploy_button()
    # Forensic detection guarantee
    button("", classes="hidden")