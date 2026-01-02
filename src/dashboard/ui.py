"""
FishBro Governance Console UI (Phase 9‑OMEGA).

Single‑truth UI backed ONLY by dashboard.service.PortfolioService.
No direct imports of portfolio.* modules allowed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Any, Optional

from nicegui import ui

from dashboard.service import PortfolioService

logger = logging.getLogger(__name__)

# Lazy singleton (no import‑time instantiation)
_SERVICE: Optional[PortfolioService] = None


def get_service(data_root: str = "outputs/portfolio_store") -> PortfolioService:
    """Return the singleton PortfolioService instance."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PortfolioService(data_root=data_root)
    return _SERVICE


# UI state
_current_state: Dict[str, Any] = {}
_strategy_table: Optional[ui.table] = None
_summary_label: Optional[ui.label] = None
_audit_log_area: Optional[ui.scroll_area] = None


async def refresh() -> None:
    """Refresh dashboard state and update UI components."""
    global _current_state
    try:
        service = get_service()
        _current_state = service.get_dashboard_state()
        logger.debug("Refreshed dashboard state, %d strategies", _current_state["total_count"])
    except Exception as e:
        logger.exception("Failed to refresh dashboard state")
        ui.notify(f"Refresh failed: {e}", type="negative")
        return

    # Update summary
    if _summary_label:
        total = _current_state["total_count"]
        live = _current_state["live_count"]
        updated = _current_state["updated_at"][:19]  # trim microseconds
        _summary_label.text = f"Strategies: {total} total, {live} LIVE · Updated: {updated}"

    # Update strategy table
    if _strategy_table:
        # Clear existing rows
        _strategy_table.rows.clear()
        # Add new rows
        for rec in _current_state["strategies"]:
            strategy_id = rec["strategy_id"]
            state = rec["state"]
            version_hash = rec.get("version_hash", "N/A")
            # Determine action button label and enabled state
            action_label = ""
            action_enabled = False
            action_callback = None
            if state == "INCUBATION":
                action_label = "Admit"
                action_enabled = True
                action_callback = lambda sid=strategy_id: admit_strategy(sid)
            elif state in ("CANDIDATE", "PAPER_TRADING"):
                # Check if activation is allowed by state machine
                # For simplicity, we allow activation from CANDIDATE or PAPER_TRADING
                action_label = "Activate"
                action_enabled = True
                action_callback = lambda sid=strategy_id: activate_strategy(sid)
            else:
                action_label = "—"
                action_enabled = False

            # Allocations display
            allocations = rec.get("allocations")
            alloc_text = "N/A"
            if allocations and isinstance(allocations, dict):
                # Format as simple string
                alloc_text = ", ".join(f"{k}:{v:.3f}" for k, v in allocations.items())

            _strategy_table.add_row(
                strategy_id,
                state,
                version_hash,
                alloc_text,
                ui.button(action_label, on_click=action_callback, color="primary" if action_enabled else "gray")
                .props("dense")
                .disable(not action_enabled),
            )

    # Update audit log
    if _audit_log_area:
        # Clear and rebuild
        _audit_log_area.clear()
        with _audit_log_area:
            for ev in _current_state["audit_log"][:20]:  # last 20 events
                ts = ev.get("ts_utc", "")[:19]
                etype = ev.get("event_type", "unknown")
                msg = ev.get("message", "")
                ui.code(f"{ts} {etype}: {msg}").classes("text-xs block")


def build_console() -> None:
    """Construct the main governance console UI."""
    global _strategy_table, _summary_label, _audit_log_area

    # Header row
    with ui.row().classes("w-full p-4 bg-primary text-white items-center"):
        ui.label("FishBro Governance Console").classes("text-2xl font-bold")
        ui.space()
        ui.button("Refresh", icon="refresh", on_click=lambda: asyncio.create_task(refresh())).props("flat")
        ui.button("Rebalance", icon="balance", on_click=lambda: asyncio.create_task(rebalance())).props("flat")
        ui.button("New Strategy", icon="add", on_click=open_register_dialog).props("flat")

    # Summary section
    with ui.row().classes("w-full p-4 bg-gray-100 rounded-lg m-4"):
        _summary_label = ui.label("Loading...").classes("text-lg")

    # Strategy table
    ui.label("Strategy Portfolio").classes("text-xl font-bold m-4")
    columns = [
        {"name": "strategy_id", "label": "Strategy ID", "field": "strategy_id", "align": "left"},
        {"name": "state", "label": "State", "field": "state", "align": "left"},
        {"name": "version_hash", "label": "Version Hash", "field": "version_hash", "align": "left"},
        {"name": "allocations", "label": "Allocations", "field": "allocations", "align": "left"},
        {"name": "action", "label": "Action", "field": "action", "align": "center"},
    ]
    _strategy_table = ui.table(columns=columns, rows=[], row_key="strategy_id").classes("w-full m-4")

    # Audit tail panel
    ui.label("Recent Audit Events").classes("text-xl font-bold m-4")
    _audit_log_area = ui.scroll_area().classes("w-full h-64 border rounded p-2 m-4 bg-gray-50")

    # Initial refresh
    asyncio.create_task(refresh())

    # Auto‑refresh timer (every 2 seconds)
    ui.timer(2.0, lambda: asyncio.create_task(refresh()))


# Action handlers
async def admit_strategy(strategy_id: str) -> None:
    """Admit an INCUBATION strategy."""
    try:
        service = get_service()
        result = await service.run_admission(strategy_id)
        ui.notify(f"Admission result: {result.get('allowed', False)}", type="info")
        await refresh()
    except Exception as e:
        logger.exception("Admission failed")
        ui.notify(f"Admission failed: {e}", type="negative")


async def activate_strategy(strategy_id: str) -> None:
    """Activate a CANDIDATE or PAPER_TRADING strategy."""
    try:
        service = get_service()
        result = await service.activate(strategy_id)
        ui.notify(f"Activated {strategy_id}", type="positive")
        await refresh()
    except Exception as e:
        logger.exception("Activation failed")
        ui.notify(f"Activation failed: {e}", type="negative")


async def rebalance() -> None:
    """Run portfolio rebalance."""
    try:
        service = get_service()
        allocations = await service.run_rebalance(total_capital=1.0)
        ui.notify(f"Rebalanced: {allocations}", type="info")
        await refresh()
    except Exception as e:
        logger.exception("Rebalance failed")
        ui.notify(f"Rebalance failed: {e}", type="negative")


def open_register_dialog() -> None:
    """Open dialog to register a new strategy."""
    with ui.dialog() as dialog, ui.card():
        ui.label("Register New Strategy").classes("text-xl font-bold mb-4")
        strategy_id_input = ui.input("Strategy ID").classes("w-full")
        config_textarea = ui.textarea("Config JSON").classes("w-full h-48").props('autogrow')
        config_textarea.value = '{"example": true}'

        async def do_register() -> None:
            strategy_id = strategy_id_input.value.strip()
            if not strategy_id:
                ui.notify("Strategy ID required", type="warning")
                return
            try:
                config = json.loads(config_textarea.value)
            except json.JSONDecodeError as e:
                ui.notify(f"Invalid JSON: {e}", type="negative")
                return

            try:
                service = get_service()
                await service.register_strategy(strategy_id, config)
                ui.notify(f"Registered {strategy_id}", type="positive")
                dialog.close()
                await refresh()
            except Exception as e:
                logger.exception("Registration failed")
                ui.notify(f"Registration failed: {e}", type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Register", on_click=lambda: asyncio.create_task(do_register())).props("flat color=primary")

    dialog.open()


# Page route
@ui.page("/")
def main_page() -> None:
    """Main page route."""
    build_console()


if __name__ == "__main__":
    # Direct execution for testing
    ui.run(title="FishBro Governance Console", port=8080, reload=False)
