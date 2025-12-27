"""
Portfolio Governance Page - UI‑1/2 Determinism‑Safe Portfolio OS.

Portfolio Overview (read‑only snapshot) and Decision Dialog.
Zero‑Leakage: uses only PortfolioBridge.
No auto‑polling, no websockets, no client‑side timers.
"""

from nicegui import ui

from ..layout import render_shell
from ..bridge.portfolio_bridge import get_portfolio_bridge
from ...contracts.portfolio_dto import PortfolioStateSnapshot, PortfolioItem


def render_portfolio_overview() -> None:
    """Render portfolio overview page."""
    ui.page_title("FishBroWFS V2 - Portfolio Governance")

    # Use shell layout
    with render_shell("/portfolio-governance", "2026Q1"):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # Page title
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Portfolio Governance").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                # Refresh button
                refresh_button = ui.button("🔄 Refresh Snapshot", icon="refresh")
                refresh_button.props("outline")
                refresh_button.classes("bg-cyber-900 hover:bg-cyber-800 text-cyber-300")

            # Container for snapshot content
            snapshot_container = ui.column().classes("w-full")

            # Initial empty state
            with snapshot_container:
                ui.label("Snapshot ready").classes("text-xl font-bold text-cyber-400 mb-2")
                ui.label("Click 'Refresh Snapshot' to load portfolio state").classes("text-slate-500")
                ui.label("UI‑1/2 Contract: No auto‑polling, manual refresh only").classes("text-sm text-slate-600 mt-4")

            # Refresh action
            def refresh_snapshot():
                snapshot_container.clear()
                try:
                    bridge = get_portfolio_bridge()
                    snapshot = bridge.get_snapshot("2026Q1")  # TODO: dynamic season
                except Exception as e:
                    with snapshot_container:
                        ui.label(f"Failed to load snapshot: {e}").classes("text-red-400")
                        ui.label("Check if portfolio ledger exists.").classes("text-slate-500")
                    return

                # Render snapshot
                with snapshot_container:
                    render_snapshot_content(snapshot)

            refresh_button.on("click", refresh_snapshot)


def render_snapshot_content(snapshot: PortfolioStateSnapshot) -> None:
    """Render portfolio snapshot content."""
    # Summary cards
    with ui.row().classes("w-full gap-4 mb-8"):
        with ui.card().classes("fish-card flex-1 p-4 border-cyber-500/30"):
            ui.label("Season").classes("font-bold text-slate-300")
            ui.label(snapshot.season_id).classes("text-2xl font-bold text-cyber-glow")
            ui.label("Governance season").classes("text-sm text-slate-500")

        with ui.card().classes("fish-card flex-1 p-4 border-blue-500/30"):
            ui.label("Items").classes("font-bold text-slate-300")
            ui.label(str(len(snapshot.items))).classes("text-2xl font-bold text-blue-400")
            ui.label("Portfolio items").classes("text-sm text-slate-500")

        with ui.card().classes("fish-card flex-1 p-4 border-purple-500/30"):
            ui.label("Decisions").classes("font-bold text-slate-300")
            ui.label(str(len(snapshot.decisions))).classes("text-2xl font-bold text-purple-400")
            ui.label("Total decisions").classes("text-sm text-slate-500")

        with ui.card().classes("fish-card flex-1 p-4 border-green-500/30"):
            ui.label("KEEP").classes("font-bold text-slate-300")
            keep_count = sum(1 for i in snapshot.items if i.current_status == "KEEP")
            ui.label(str(keep_count)).classes("text-2xl font-bold text-green-400")
            ui.label("Kept items").classes("text-sm text-slate-500")

    # Items table
    ui.label("Portfolio Items").classes("text-2xl font-bold mb-4 text-cyber-400")
    if not snapshot.items:
        with ui.card().classes("fish-card w-full p-6 border-amber-500/30"):
            ui.label("No portfolio items").classes("text-slate-500")
            ui.label("Submit a decision to create items.").classes("text-sm text-slate-600")
    else:
        with ui.card().classes("fish-card w-full p-6 border-purple-500/30"):
            # Table headers
            with ui.row().classes("w-full font-bold text-slate-300 border-b border-nexus-800 pb-2 mb-2"):
                ui.label("Strategy").classes("flex-1")
                ui.label("Instance").classes("flex-1")
                ui.label("Status").classes("flex-1")
                ui.label("Last Decision").classes("flex-1")
                ui.label("Actions").classes("flex-1 text-right")

            # Table rows
            for item in snapshot.items:
                with ui.row().classes("w-full py-3 border-b border-nexus-800 last:border-0 items-center"):
                    ui.label(item.strategy_id).classes("flex-1 font-mono text-sm")
                    ui.label(item.instance_id).classes("flex-1 font-mono text-sm")
                    # Status badge
                    status_color = {
                        "CANDIDATE": "text-slate-400",
                        "KEEP": "text-green-400",
                        "DROP": "text-red-400",
                        "FROZEN": "text-amber-400",
                    }.get(item.current_status, "text-slate-400")
                    ui.label(item.current_status).classes(f"flex-1 font-bold {status_color}")
                    ui.label(item.last_decision_id[:8] if item.last_decision_id else "—").classes("flex-1 font-mono text-xs text-slate-500")
                    with ui.row().classes("flex-1 justify-end gap-2"):
                        if item.current_status != "FROZEN":
                            ui.button("KEEP", on_click=lambda i=item: open_decision_dialog(i, "KEEP")).props("outline size=sm").classes("bg-green-900/30 text-green-300")
                            ui.button("DROP", on_click=lambda i=item: open_decision_dialog(i, "DROP")).props("outline size=sm").classes("bg-red-900/30 text-red-300")
                            ui.button("FREEZE", on_click=lambda i=item: open_decision_dialog(i, "FREEZE")).props("outline size=sm").classes("bg-amber-900/30 text-amber-300")
                        else:
                            ui.label("Frozen").classes("text-xs text-slate-500")

    # Decisions history
    ui.label("Decision History").classes("text-2xl font-bold mb-4 text-cyber-400 mt-8")
    if not snapshot.decisions:
        with ui.card().classes("fish-card w-full p-6 border-amber-500/30"):
            ui.label("No decision history").classes("text-slate-500")
            ui.label("Decisions will appear here after submission.").classes("text-sm text-slate-600")
    else:
        with ui.card().classes("fish-card w-full p-6 border-blue-500/30"):
            # Show last 10 decisions
            recent = list(reversed(snapshot.decisions))[:10]
            for ev in recent:
                with ui.row().classes("w-full py-3 border-b border-nexus-800 last:border-0 items-center"):
                    ui.label(ev.action).classes("w-20 font-bold text-slate-300")
                    ui.label(f"{ev.strategy_id}/{ev.instance_id}").classes("flex-1 font-mono text-sm")
                    ui.label(ev.reason).classes("flex-2 text-sm text-slate-400 truncate")
                    ui.label(ev.actor).classes("w-32 text-xs text-slate-500")
                    ui.label(ev.created_at_utc[:19]).classes("w-48 text-xs text-slate-600")


def open_decision_dialog(item: PortfolioItem, action: str) -> None:
    """Open decision dialog for a portfolio item."""
    with ui.dialog() as dialog, ui.card().classes("fish-card w-[500px] p-6"):
        ui.label(f"{action} {item.strategy_id}/{item.instance_id}").classes("text-xl font-bold text-cyber-400 mb-4")
        ui.label(f"Season: {item.season_id}").classes("text-sm text-slate-400 mb-2")
        ui.label("Reason (required):").classes("font-bold text-slate-300 mb-2")
        reason_input = ui.textarea(placeholder="Explain why this decision is made...").classes("w-full mb-4")
        reason_input.props("autogrow")
        ui.label("Actor (optional, defaults to 'user:ui'):").classes("font-bold text-slate-300 mb-2")
        actor_input = ui.input(value="user:ui").classes("w-full mb-6")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("outline")
            ui.button("Submit", on_click=lambda: submit_decision(item, action, reason_input.value, actor_input.value, dialog)).props("color=primary")


def submit_decision(item: PortfolioItem, action: str, reason: str, actor: str, dialog) -> None:
    """Submit decision via PortfolioBridge."""
    if not reason.strip():
        ui.notify("Reason is required", type="negative")
        return
    if not actor.strip():
        actor = "user:ui"

    try:
        bridge = get_portfolio_bridge()
        event = bridge.submit_decision(
            season_id=item.season_id,
            strategy_id=item.strategy_id,
            instance_id=item.instance_id,
            action=action,
            reason=reason,
            actor=actor,
        )
        ui.notify(f"Decision {action} submitted", type="positive")
        dialog.close()
        # Refresh snapshot (by simulating a click on refresh button)
        # We'll just reload the page for simplicity
        ui.navigate.to("/portfolio-governance", reload=True)
    except Exception as e:
        ui.notify(f"Submission failed: {e}", type="negative")


def register() -> None:
    """Register portfolio governance page route."""

    @ui.page("/portfolio-governance")
    def portfolio_governance_page() -> None:
        """Portfolio governance page."""
        render_portfolio_overview()