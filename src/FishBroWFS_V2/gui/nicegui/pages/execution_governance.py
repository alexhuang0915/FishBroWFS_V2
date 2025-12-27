"""
Execution Governance Page - UI‑1/2 Determinism‑Safe Execution OS.

Execution Plan Overview (read‑only snapshot) and Create/Transition Dialogs.
Zero‑Leakage: uses only ExecutionBridge.
No auto‑polling, no websockets, no client‑side timers.
"""

from nicegui import ui

from ..layout import render_shell
from ..bridge.execution_bridge import get_execution_bridge
from ...contracts.execution_dto import ExecutionStateSnapshot, ExecutionPlan


def render_execution_overview() -> None:
    """Render execution overview page."""
    ui.page_title("FishBroWFS V2 - Execution Governance")

    # Use shell layout
    with render_shell("/execution-governance", "2026Q1"):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # Page title
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Execution Governance").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                # Refresh button
                refresh_button = ui.button("🔄 Refresh Snapshot", icon="refresh")
                refresh_button.props("outline")
                refresh_button.classes("bg-cyber-900 hover:bg-cyber-800 text-cyber-300")
                # Create Plan button
                create_button = ui.button("➕ Create Plan", icon="add")
                create_button.props("outline")
                create_button.classes("bg-green-900/30 hover:bg-green-800/30 text-green-300")

            # Container for snapshot content
            snapshot_container = ui.column().classes("w-full")

            # Initial empty state
            with snapshot_container:
                ui.label("Snapshot ready").classes("text-xl font-bold text-cyber-400 mb-2")
                ui.label("Click 'Refresh Snapshot' to load execution state").classes("text-slate-500")
                ui.label("UI‑1/2 Contract: No auto‑polling, manual refresh only").classes("text-sm text-slate-600 mt-4")

            # Refresh action
            def refresh_snapshot():
                snapshot_container.clear()
                try:
                    bridge = get_execution_bridge()
                    snapshot = bridge.get_snapshot("2026Q1")  # TODO: dynamic season
                except Exception as e:
                    with snapshot_container:
                        ui.label(f"Failed to load snapshot: {e}").classes("text-red-400")
                        ui.label("Check if execution ledger exists.").classes("text-slate-500")
                    return

                # Render snapshot
                with snapshot_container:
                    render_snapshot_content(snapshot)

            refresh_button.on("click", refresh_snapshot)

            # Create Plan action
            def open_create_dialog():
                with ui.dialog() as dialog, ui.card().classes("fish-card w-[600px] p-6"):
                    ui.label("Create Execution Plan").classes("text-xl font-bold text-cyber-400 mb-4")
                    ui.label("Season:").classes("font-bold text-slate-300 mb-1")
                    season_input = ui.input(value="2026Q1").classes("w-full mb-4")
                    ui.label("Risk Profile ID:").classes("font-bold text-slate-300 mb-1")
                    risk_input = ui.input(value="default").classes("w-full mb-4")
                    ui.label("Portfolio Item IDs (one per line):").classes("font-bold text-slate-300 mb-1")
                    items_input = ui.textarea(placeholder="item1\nitem2\nitem3").classes("w-full mb-4")
                    items_input.props("autogrow")
                    ui.label("Reason (required):").classes("font-bold text-slate-300 mb-1")
                    reason_input = ui.textarea(placeholder="Why create this plan?").classes("w-full mb-4")
                    reason_input.props("autogrow")
                    ui.label("Actor (optional, defaults to 'user:ui'):").classes("font-bold text-slate-300 mb-1")
                    actor_input = ui.input(value="user:ui").classes("w-full mb-6")

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Cancel", on_click=dialog.close).props("outline")
                        ui.button("Create", on_click=lambda: create_plan(
                            season_input.value,
                            risk_input.value,
                            items_input.value,
                            reason_input.value,
                            actor_input.value,
                            dialog
                        )).props("color=primary")

                dialog.open()

            create_button.on("click", open_create_dialog)


def render_snapshot_content(snapshot: ExecutionStateSnapshot) -> None:
    """Render execution snapshot content."""
    # Summary cards
    with ui.row().classes("w-full gap-4 mb-8"):
        with ui.card().classes("fish-card flex-1 p-4 border-cyber-500/30"):
            ui.label("Season").classes("font-bold text-slate-300")
            ui.label(snapshot.season_id).classes("text-2xl font-bold text-cyber-glow")
            ui.label("Governance season").classes("text-sm text-slate-500")

        with ui.card().classes("fish-card flex-1 p-4 border-blue-500/30"):
            ui.label("Plans").classes("font-bold text-slate-300")
            ui.label(str(len(snapshot.plans))).classes("text-2xl font-bold text-blue-400")
            ui.label("Execution plans").classes("text-sm text-slate-500")

        with ui.card().classes("fish-card flex-1 p-4 border-purple-500/30"):
            ui.label("Events").classes("font-bold text-slate-300")
            ui.label(str(len(snapshot.events))).classes("text-2xl font-bold text-purple-400")
            ui.label("Total events").classes("text-sm text-slate-500")

        with ui.card().classes("fish-card flex-1 p-4 border-green-500/30"):
            ui.label("COMMITTED").classes("font-bold text-slate-300")
            committed_count = sum(1 for p in snapshot.plans if p.state == "COMMITTED")
            ui.label(str(committed_count)).classes("text-2xl font-bold text-green-400")
            ui.label("Committed plans").classes("text-sm text-slate-500")

    # Plans table
    ui.label("Execution Plans").classes("text-2xl font-bold mb-4 text-cyber-400")
    if not snapshot.plans:
        with ui.card().classes("fish-card w-full p-6 border-amber-500/30"):
            ui.label("No execution plans").classes("text-slate-500")
            ui.label("Create a plan to get started.").classes("text-sm text-slate-600")
    else:
        with ui.card().classes("fish-card w-full p-6 border-purple-500/30"):
            # Table headers
            with ui.row().classes("w-full font-bold text-slate-300 border-b border-nexus-800 pb-2 mb-2"):
                ui.label("Plan ID").classes("flex-1")
                ui.label("State").classes("flex-1")
                ui.label("Risk Profile").classes("flex-1")
                ui.label("Items").classes("flex-1")
                ui.label("Actions").classes("flex-1 text-right")

            # Table rows
            for plan in snapshot.plans:
                with ui.row().classes("w-full py-3 border-b border-nexus-800 last:border-0 items-center"):
                    ui.label(plan.plan_id[:8]).classes("flex-1 font-mono text-sm")
                    # State badge
                    state_color = {
                        "DRAFT": "text-slate-400",
                        "REVIEWED": "text-blue-400",
                        "APPROVED": "text-amber-400",
                        "COMMITTED": "text-green-400",
                        "CANCELLED": "text-red-400",
                    }.get(plan.state, "text-slate-400")
                    ui.label(plan.state).classes(f"flex-1 font-bold {state_color}")
                    ui.label(plan.risk_profile_id).classes("flex-1 font-mono text-sm")
                    ui.label(str(len(plan.portfolio_item_ids))).classes("flex-1 font-mono text-sm")
                    with ui.row().classes("flex-1 justify-end gap-2"):
                        if plan.state not in ("COMMITTED", "CANCELLED"):
                            ui.button("Review", on_click=lambda p=plan: open_transition_dialog(p, "REVIEW")).props("outline size=sm").classes("bg-blue-900/30 text-blue-300")
                            ui.button("Approve", on_click=lambda p=plan: open_transition_dialog(p, "APPROVE")).props("outline size=sm").classes("bg-amber-900/30 text-amber-300")
                            ui.button("Commit", on_click=lambda p=plan: open_transition_dialog(p, "COMMIT")).props("outline size=sm").classes("bg-green-900/30 text-green-300")
                            ui.button("Cancel", on_click=lambda p=plan: open_transition_dialog(p, "CANCEL")).props("outline size=sm").classes("bg-red-900/30 text-red-300")
                        else:
                            ui.label("Terminal").classes("text-xs text-slate-500")

    # Events history
    ui.label("Event History").classes("text-2xl font-bold mb-4 text-cyber-400 mt-8")
    if not snapshot.events:
        with ui.card().classes("fish-card w-full p-6 border-amber-500/30"):
            ui.label("No event history").classes("text-slate-500")
            ui.label("Events will appear here after plan creation or transition.").classes("text-sm text-slate-600")
    else:
        with ui.card().classes("fish-card w-full p-6 border-blue-500/30"):
            # Show last 10 events
            recent = list(reversed(snapshot.events))[:10]
            for ev in recent:
                with ui.row().classes("w-full py-3 border-b border-nexus-800 last:border-0 items-center"):
                    ui.label(ev.action).classes("w-24 font-bold text-slate-300")
                    ui.label(ev.plan_id[:8]).classes("flex-1 font-mono text-sm")
                    ui.label(f"{ev.from_state}→{ev.to_state}").classes("w-32 text-sm text-slate-400")
                    ui.label(ev.reason).classes("flex-2 text-sm text-slate-400 truncate")
                    ui.label(ev.actor).classes("w-32 text-xs text-slate-500")
                    ui.label(ev.created_at_utc[:19]).classes("w-48 text-xs text-slate-600")


def open_transition_dialog(plan: ExecutionPlan, action: str) -> None:
    """Open transition dialog for an execution plan."""
    with ui.dialog() as dialog, ui.card().classes("fish-card w-[500px] p-6"):
        ui.label(f"{action} Plan {plan.plan_id[:8]}").classes("text-xl font-bold text-cyber-400 mb-4")
        ui.label(f"Current state: {plan.state}").classes("text-sm text-slate-400 mb-2")
        ui.label("Reason (required):").classes("font-bold text-slate-300 mb-2")
        reason_input = ui.textarea(placeholder="Explain why this transition is needed...").classes("w-full mb-4")
        reason_input.props("autogrow")
        ui.label("Actor (optional, defaults to 'user:ui'):").classes("font-bold text-slate-300 mb-2")
        actor_input = ui.input(value="user:ui").classes("w-full mb-6")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("outline")
            ui.button("Submit", on_click=lambda: submit_transition(plan, action, reason_input.value, actor_input.value, dialog)).props("color=primary")


def create_plan(season_id: str, risk_profile_id: str, items_text: str, reason: str, actor: str, dialog) -> None:
    """Create execution plan via ExecutionBridge."""
    if not reason.strip():
        ui.notify("Reason is required", type="negative")
        return
    if not actor.strip():
        actor = "user:ui"
    portfolio_item_ids = [line.strip() for line in items_text.strip().splitlines() if line.strip()]
    if not portfolio_item_ids:
        ui.notify("At least one portfolio item ID is required", type="negative")
        return

    try:
        bridge = get_execution_bridge()
        plan = bridge.create_plan_from_portfolio(
            season_id=season_id,
            portfolio_item_ids=portfolio_item_ids,
            risk_profile_id=risk_profile_id,
            reason=reason,
            actor=actor,
        )
        ui.notify(f"Plan {plan.plan_id[:8]} created", type="positive")
        dialog.close()
        # Refresh snapshot (by simulating a click on refresh button)
        # We'll just reload the page for simplicity
        ui.navigate.to("/execution-governance", reload=True)
    except Exception as e:
        ui.notify(f"Creation failed: {e}", type="negative")


def submit_transition(plan: ExecutionPlan, action: str, reason: str, actor: str, dialog) -> None:
    """Submit transition via ExecutionBridge."""
    if not reason.strip():
        ui.notify("Reason is required", type="negative")
        return
    if not actor.strip():
        actor = "user:ui"

    try:
        bridge = get_execution_bridge()
        updated_plan = bridge.transition_plan(
            season_id=plan.season_id,
            plan_id=plan.plan_id,
            action=action,
            reason=reason,
            actor=actor,
        )
        ui.notify(f"Plan {plan.plan_id[:8]} transitioned to {updated_plan.state}", type="positive")
        dialog.close()
        ui.navigate.to("/execution-governance", reload=True)
    except Exception as e:
        ui.notify(f"Transition failed: {e}", type="negative")


def register() -> None:
    """Register execution governance page route."""

    @ui.page("/execution-governance")
    def execution_governance_page() -> None:
        """Execution governance page."""
        render_execution_overview()