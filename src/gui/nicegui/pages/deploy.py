"""Deploy page - Read-only prototype with explicit "Not implemented; use CLI" message.

This page is part of Minimum Honest UI: it explicitly declares its limitations
and directs users to CLI for actual deployment.
"""
from nicegui import ui

from ..layout.cards import render_card
from ..layout.toasts import show_toast, ToastType
from ..constitution.page_shell import page_shell

# Page shell compliance flag
PAGE_SHELL_ENABLED = True


def render() -> None:
    """Render the Deploy page with explicit truthfulness."""
    
    def render_content():
        ui.label("Deploy Configuration").classes("text-2xl font-bold text-primary mb-6")
        
        # Explicit truth banner
        with ui.card().classes("w-full bg-danger/20 border-danger border-l-4 mb-6"):
            ui.label("🚫 NOT IMPLEMENTED - USE CLI").classes("text-danger font-bold mb-2")
            ui.label("Deployment must be performed via CLI commands. This UI is read‑only.").classes("text-danger text-sm")
            ui.label("No actual deployment can be triggered from this page.").classes("text-danger text-sm")
        
        # CLI instructions
        with ui.card().classes("w-full mb-6"):
            ui.label("Use CLI Instead").classes("text-lg font-bold mb-2")
            with ui.column().classes("w-full gap-2 font-mono text-sm bg-panel-dark p-4 rounded"):
                ui.label("$ python -m scripts.deploy_preflight --portfolio portfolio.json")
                ui.label("$ python -m scripts.deploy_validate --target paper --account ACC123")
                ui.label("$ python -m scripts.deploy_execute --confirm --dry-run")
                ui.label("$ python -m scripts.deploy_monitor --deployment-id DEP123")
            ui.label("The CLI provides full deployment control with proper validation.").classes("text-tertiary text-sm mt-2")
        
        # Configuration summary (example)
        with ui.card().classes("w-full mb-6"):
            ui.label("Example Configuration (Read‑Only)").classes("text-lg font-bold mb-2")
            ui.label("This is a static example for demonstration. No changes are possible.").classes("text-tertiary text-sm mb-4")
            
            with ui.column().classes("w-full gap-2"):
                ui.label("Target: Paper Trading (example)")
                ui.label("Account ID: ACC‑EXAMPLE‑123")
                ui.label("Environment: staging")
                ui.label("Portfolio: S1 (40%), S1‑Short (60%)")
                ui.label("Risk Budget: MEDIUM")
                ui.label("Margin Model: Symbolic")
                ui.label("Execution Mode: LIMIT orders only")
        
        # Safety checks (read-only, pre-checked to show example)
        with ui.column().classes("w-full gap-4 mb-6"):
            ui.label("Example Safety Checks").classes("text-lg font-bold")
            ui.checkbox("I have reviewed the portfolio weights", value=True).props("disable")
            ui.checkbox("I understand the risk budget", value=True).props("disable")
            ui.checkbox("I confirm that margin requirements are satisfied", value=True).props("disable")
            ui.checkbox("I accept that deployment cannot be automatically rolled back", value=True).props("disable")
            ui.checkbox("I am the sole human operator", value=True).props("disable")
            ui.label("All checks are pre‑filled as example only.").classes("text-xs text-tertiary")
        
        # Deployment status
        with ui.card().classes("w-full mb-6 border-2 border-warning"):
            ui.label("Deployment Status").classes("text-lg font-bold text-warning mb-2")
            ui.label("Status: NOT READY (UI is read‑only)").classes("text-warning")
            ui.label("All deployment actions are disabled in this UI.").classes("text-sm text-tertiary")
        
        # Action buttons that show explicit messages
        def on_validate():
            show_toast("Deployment validation not implemented. Use CLI instead.", ToastType.INFO)
        
        def on_export():
            show_toast("Config export not implemented. Use CLI instead.", ToastType.INFO)
        
        def on_deploy():
            show_toast("Deployment not implemented. Use CLI instead. This button does nothing.", ToastType.WARNING)
        
        def on_clear_log():
            show_toast("Log is read‑only in this prototype.", ToastType.INFO)
        
        def on_copy_log():
            show_toast("Log copied to clipboard (example only)", ToastType.INFO)
            # Actually copy example text
            ui.run_javascript("navigator.clipboard.writeText('Example deployment log\\nStatus: UI is read‑only\\nUse CLI for actual deployment')")
        
        with ui.row().classes("w-full gap-4"):
            ui.button("Validate (Read‑Only)", icon="check_circle", color="warning", on_click=on_validate)
            ui.button("Export (Read‑Only)", icon="download", color="transparent", on_click=on_export)
            ui.button("Deploy (Disabled)", icon="rocket_launch", color="danger", on_click=on_deploy).props("disabled")
        
        # Log output (example)
        with ui.card().classes("w-full mb-6"):
            ui.label("Example Deployment Log").classes("text-lg font-bold mb-2")
            log_content = """[INFO] Deployment UI is read‑only
[INFO] No actual deployment can be triggered
[INFO] Use CLI for real deployment:
[INFO]   $ python -m scripts.deploy_execute --confirm
[WARNING] This is example text only
"""
            log_textarea = ui.textarea(value=log_content).props("readonly").classes("w-full h-48 font-mono text-sm")
            
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Clear (Read‑Only)", icon="clear", on_click=on_clear_log)
                ui.button("Copy Example", icon="content_copy", on_click=on_copy_log)
        
        # Final warning
        with ui.card().classes("w-full border-2 border-danger"):
            ui.label("⚠️ CRITICAL REMINDER").classes("text-lg font-bold text-danger mb-2")
            ui.label("This UI page cannot trigger actual deployment. All deployment must be done via CLI with proper human review.").classes("text-sm")
            ui.label("The system follows the principle: 'Machine Must Not Make Mistakes'.").classes("text-xs text-muted mt-2")
        
        # Final note
        ui.label("This page complies with Minimum Honest UI: it explicitly declares its read‑only nature.").classes("text-xs text-muted mt-8")
    
    # Wrap in page shell
    page_shell("Deploy Configuration", render_content)
