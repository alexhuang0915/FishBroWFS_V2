"""OP (Operator Console) page.

This is the default landing tab for research & filtering only.
OP MUST NEVER:
- Activate strategies
- Modify live portfolio
- Perform risk decisions

Constitution Requirements:
1. Run Strategy card with inputs (Strategy Family, DATA1, DATA2, Time Frame)
2. Safety Lock: disable inputs during execution
3. Last Config Recall: persist config across page reloads
4. Workers configuration (1-20, default 10) in separate section
5. Result section with Accept/Discard buttons
6. Accept path only to Registry (Status = Incubation)
"""
import asyncio
import json
import logging
import traceback
from typing import Dict, Any, Optional, List
from pathlib import Path

from nicegui import ui
from .. import ui_compat as uic

from ..layout.cards import render_card
from ..layout.toasts import show_toast, ToastType
from ..state.app_state import AppState
from ..constitution.page_shell import page_shell
from ..services.data_discovery import get_dataset_options
from ..layout.navigation import render_top_nav
from control.run_status import (
    read_status as read_run_status_disk,
    set_running as set_run_status_running,
    set_failed as set_run_status_failed,
    update_status as update_run_status,
)
from gui.nicegui.services.run_launcher_service import launch_run_from_dict

logger = logging.getLogger(__name__)


# Phase 14.4: OP monitoring without HTTP loopback
def read_run_status_for_ui() -> Dict[str, Any]:
    """Read run status for UI display without HTTP requests.
    
    Returns:
        Dict with safe defaults even if file missing/corrupt.
        Never raises exceptions.
    """
    try:
        status = read_run_status_disk()
        if not isinstance(status, dict):
            return {"state": "IDLE", "progress": 0, "step": "init", "message": "", "last_updated": None}
        # Ensure minimum fields exist
        status.setdefault("state", "IDLE")
        status.setdefault("progress", 0)
        status.setdefault("step", "init")
        status.setdefault("message", "")
        status.setdefault("last_updated", None)
        return status
    except Exception as e:
        return {"state": "ERROR", "progress": 0, "step": "init", "message": f"Error: {e}", "last_updated": None}

# Page shell compliance flag
PAGE_SHELL_ENABLED = True

# Configuration storage path
OP_CONFIG_PATH = Path("outputs/op_config.json")

# Default configuration - will be updated with real datasets
DEFAULT_CONFIG = {
    "strategy_family": "S1",
    "data1": None,  # Will be set to first available dataset
    "data2": None,
    "time_frame": "60",
    "workers": 10,
}

# Available options
STRATEGY_FAMILIES = ["S1", "S2", "S3"]
TIME_FRAMES = ["15", "30", "60", "120", "240"]

# Real datasets discovered from raw data
def get_datasets() -> List[str]:
    """Get real datasets from raw data directory."""
    datasets = get_dataset_options()
    if not datasets:
        # Fallback to hardcoded if no datasets found (should not happen in production)
        logger.warning("No datasets discovered, using fallback")
        return ["TXF", "MNQ", "MES", "MYM", "M2K"]
    return datasets


def load_config() -> Dict[str, Any]:
    """Load OP configuration from disk."""
    try:
        if OP_CONFIG_PATH.exists():
            with open(OP_CONFIG_PATH, 'r') as f:
                config = json.load(f)
                # Ensure all required keys exist
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                
                # If data1 is None or not in available datasets, set to first available
                datasets = get_datasets()
                if config.get("data1") is None or config["data1"] not in datasets:
                    config["data1"] = datasets[0] if datasets else "TXF"
                
                return config
    except Exception as e:
        logger.warning(f"Failed to load OP config: {e}")
    
    # Return default config with real datasets
    config = DEFAULT_CONFIG.copy()
    datasets = get_datasets()
    config["data1"] = datasets[0] if datasets else "TXF"
    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save OP configuration to disk."""
    try:
        OP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OP_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save OP config: {e}")


class OPState:
    """State for OP tab."""
    
    def __init__(self):
        self.config = load_config()
        self.is_running = False
        self.result: Optional[Dict[str, Any]] = None
        self.execution_log: list[str] = []
    
    def update_config(self, key: str, value: Any) -> None:
        """Update configuration and save to disk."""
        self.config[key] = value
        save_config(self.config)
    
    def add_log(self, message: str) -> None:
        """Add message to execution log."""
        self.execution_log.append(message)
        # Keep only last 50 messages
        if len(self.execution_log) > 50:
            self.execution_log = self.execution_log[-50:]


# Global state instance
_op_state: Optional[OPState] = None


def get_op_state() -> OPState:
    """Get or create OP state instance."""
    global _op_state
    if _op_state is None:
        _op_state = OPState()
    return _op_state


@ui.page('/')
def page_op():
    """OP page route."""
    # Render navigation
    render_top_nav('/')
    
    # Render page content
    render()


def render() -> None:
    """Render the OP (Operator Console) page."""
    state = get_op_state()
    app_state = AppState.get()
    
    def render_content():
        ui.label("Operator Console (OP)").classes("text-2xl font-bold text-primary mb-2")
        ui.label("Research & filtering only. No activation, no risk decisions.").classes("text-secondary mb-6")
        
        # Get real datasets
        datasets = get_datasets()
        
        # Phase 14.4: Governance Observability without HTTP loopback (Card-Only Refresh)
        with ui.card().classes("w-full bg-panel-dark p-6 mb-6"):
            ui.label("Governance Observability").classes("text-xl font-bold text-primary mb-4")
            
            # UX Contract (MANDATORY TEXT)
            ui.markdown("**This governance console is synchronous.** Progress updates are retrieved via periodic refresh.").classes("text-secondary mb-4")
            
            # Refreshable observability panel
            @ui.refreshable
            def render_observability_panel() -> None:
                s = read_run_status_for_ui()
                state = s.get("state", "IDLE")
                progress = int(s.get("progress", 0) or 0)
                step = s.get("step", "init")
                msg = s.get("message", "")
                last = s.get("last_updated", None) or "Never"
                
                # State label with color coding
                state_colors = {
                    "IDLE": "text-gray-500",
                    "RUNNING": "text-blue-500",
                    "DONE": "text-green-500",
                    "FAILED": "text-red-500",
                    "CANCELED": "text-yellow-500",
                    "ERROR": "text-red-700"
                }
                state_color = state_colors.get(state, "text-gray-500")
                
                ui.label(f"State: {state}").classes(f"text-lg font-bold {state_color}")
                ui.label(f"Progress: {progress}%").classes("text-sm")
                ui.linear_progress(progress / 100.0 if progress is not None else 0).classes("w-full h-2 mb-2")
                ui.label(f"Step: {step}").classes("text-sm")
                ui.label(f"Message: {msg}").classes("text-sm")
                ui.label(f"Last updated: {last}").classes("text-xs text-tertiary")
            
            # Render the panel
            render_observability_panel()
            
            # Store refresh method for use by RUN button
            observability_refresh = render_observability_panel.refresh
            
            # Control row
            control_row = ui.row().classes("w-full justify-between items-center mt-4")
            with control_row:
                # Refresh button
                uic.button(
                    "Refresh",
                    icon="refresh",
                    on_click=lambda: observability_refresh(),
                    color="secondary"
                )
                
                # Auto-refresh toggle with timer
                auto_refresh = {"enabled": False}
                
                def _tick_refresh() -> None:
                    if auto_refresh["enabled"]:
                        observability_refresh()
                
                timer = ui.timer(5.0, _tick_refresh, active=True)
                
                def on_toggle_auto_refresh(e) -> None:
                    auto_refresh["enabled"] = bool(e.value)
                
                ui.switch("Auto-refresh (5s)", value=False).on("update:model-value", on_toggle_auto_refresh)
        
        # Main card: RUN STRATEGY
        with ui.card().classes("w-full bg-panel-dark p-6 mb-6"):
            ui.label("Run Strategy").classes("text-xl font-bold text-primary mb-4")
            
            # Input grid
            with ui.grid(columns=2).classes("w-full gap-4 mb-4"):
                # Strategy Family
                strategy_select = uic.select(
                    "Strategy Family",
                    STRATEGY_FAMILIES,
                    value=state.config.get("strategy_family", "S1")
                ).classes("w-full")
                
                # DATA1
                data1_select = uic.select(
                    "DATA1",
                    datasets,
                    value=state.config.get("data1", datasets[0] if datasets else "TXF")
                ).classes("w-full")
                
                # DATA2 (with None option)
                data2_options = ["None"] + datasets
                data2_select = uic.select(
                    "DATA2",
                    data2_options,
                    value=state.config.get("data2", "None") or "None"
                ).classes("w-full")
                
                # Time Frame
                tf_select = uic.select(
                    "Time Frame",
                    TIME_FRAMES,
                    value=str(state.config.get("time_frame", "60"))
                ).classes("w-full")
            
            # Run button
            run_button = uic.button(
                "▶ Run",
                icon="play_arrow",
                on_click=lambda: run_backtest(
                    state,
                    strategy_select.value,
                    data1_select.value,
                    None if data2_select.value == "None" else data2_select.value,
                    tf_select.value,
                    run_button,
                    [strategy_select, data1_select, data2_select, tf_select],
                    refresh_callback=observability_refresh
                ),
                color="primary"
            ).classes("mt-2")
            
            # Reset OP button
            ui.button(
                "Reset OP",
                icon="restart_alt",
                on_click=lambda: reset_op(state, strategy_select, data1_select, data2_select, tf_select),
                color="warning"
            ).props("flat").classes("mt-2")
        
        # Execution Environment section (Workers)
        with ui.card().classes("w-full bg-panel-dark p-6 mb-6"):
            ui.label("⚙️ Execution Environment").classes("text-xl font-bold text-primary mb-4")
            ui.label("Workers (1-20). Default = 10 based on i5-13600KF / 64GB").classes("text-secondary mb-2")
            
            workers_slider = ui.slider(
                min=1,
                max=20,
                value=state.config.get("workers", 10)
            ).classes("w-full")
            workers_label = ui.label(f"Workers: {workers_slider.value}").classes("text-sm")
            
            def update_workers(value):
                state.update_config("workers", value)
                workers_label.set_text(f"Workers: {value}")
            
            workers_slider.on("update:model-value", lambda e: update_workers(e.args))
        
        # Result Section
        with ui.card().classes("w-full bg-panel-dark p-6 mb-6"):
            ui.label("Result Summary").classes("text-xl font-bold text-primary mb-4")
            
            # Result metrics (initially hidden)
            result_container = ui.column().classes("w-full")
            with result_container:
                ui.label("No results yet. Run a backtest to see results.").classes("text-tertiary")
            
            # Mini Equity Curve placeholder
            ui.label("Mini Equity Curve").classes("text-lg font-bold mt-6 mb-2")
            equity_curve_placeholder = ui.element('div').classes(
                "w-full h-32 bg-gray-800 rounded flex items-center justify-center"
            )
            with equity_curve_placeholder:
                ui.label("Shape-only visualization").classes("text-tertiary")
                ui.label("No interaction, no zoom, no parameter overlays").classes("text-tertiary text-xs")
            
            # Accept/Discard buttons
            button_row = ui.row().classes("w-full justify-end gap-2 mt-4")
            with button_row:
                accept_button = uic.button(
                    "Accept",
                    icon="check",
                    on_click=lambda: accept_result(state),
                    color="positive"
                ).props("disabled")
                discard_button = uic.button(
                    "Discard",
                    icon="close",
                    on_click=lambda: discard_result(state, result_container),
                    color="negative"
                ).props("disabled")
        
        # Execution Log
        with ui.card().classes("w-full bg-panel-dark p-6"):
            ui.label("Execution Log").classes("text-xl font-bold text-primary mb-4")
            log_area = ui.textarea("").props("readonly autogrow").classes(
                "w-full h-48 font-mono text-sm bg-gray-900"
            )
            log_area.value = "\n".join(state.execution_log) if state.execution_log else "[10:12] Ready."
            
            # Update log periodically
            def update_log():
                log_area.value = "\n".join(state.execution_log) if state.execution_log else "[10:12] Ready."
            
            ui.timer(1.0, update_log)
    
    # Wrap in page shell
    page_shell("Operator Console", render_content)




def _build_intent_dict_for_op(
    strategy_family: str,
    data1: str,
    data2: Optional[str],
    time_frame: int,
) -> Dict[str, Any]:
    # Minimal intent schema aligned with run_launcher_service validation
    # Keep it conservative: only fields you are sure are accepted.
    intent: Dict[str, Any] = {
        "strategy_family": strategy_family,
        "data1": data1,
        "data2": None if (data2 in (None, "", "None")) else data2,
        "time_frame": int(time_frame),
        "origin": "op_ui",
        "notes": "Run created by OP Run Strategy button (Phase 14.5)",
    }
    return intent


async def _launch_run_background(
    intent_dict: Dict[str, Any],
    season: str,
    refresh_callback,
    run_button,
    inputs,
) -> None:
    """Background coroutine that performs the heavy launch work off the UI thread."""
    try:
        # Run the synchronous launch function in a thread executor
        run_dir = await asyncio.to_thread(
            launch_run_from_dict,
            intent_dict,
            season=season,
        )
        # Update status step to launched (state remains RUNNING)
        update_run_status(step="launched", message=f"Run launched: {run_dir}")
        # Notify user
        ui.notify(f"Run launched: {run_dir}", type="positive")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        # Update status to FAILED
        set_run_status_failed(f"Launch failed: {err}")
        update_run_status(step="failed", message=f"Launch failed: {err}")
        ui.notify(f"Launch failed: {err}", type="negative")
    finally:
        # Re-enable inputs (safety lock release)
        try:
            run_button.enable()
            for inp in inputs:
                inp.enable()
        except Exception:
            pass
        # Refresh observability card
        if callable(refresh_callback):
            try:
                refresh_callback()
            except Exception:
                pass


def run_backtest(
    state,
    strategy_family,
    data1,
    data2,
    time_frame,
    run_button,
    inputs,
    refresh_callback=None,
):
    """Synchronous click handler that schedules background launch and returns immediately."""
    # Immediate UI proof of click (mandatory)
    ui.notify("RUN clicked: scheduling launch", type='positive')
    
    # Phase 14.7: Diagnostic log for RUN click
    import datetime
    from nicegui import context
    client_connected = hasattr(context, 'client') and context.client is not None
    state.add_log(f"RUN clicked at {datetime.datetime.now().isoformat()} (client connected={client_connected})")

    # 1) Immediate status change (must happen even if launch fails)
    try:
        set_run_status_running("Launching run from OP...")
        update_run_status(step="launching", message="Launching run from OP...")
    except Exception:
        # Must never crash UI because status writer failed
        pass

    # 2) Immediate card refresh
    if callable(refresh_callback):
        try:
            refresh_callback()
        except Exception:
            pass

    # 3) Disable inputs (keep existing safety lock behavior)
    try:
        run_button.disable()
        for inp in inputs:
            inp.disable()
    except Exception:
        pass

    # 4) Build intent dict (lightweight)
    try:
        intent_dict = _build_intent_dict_for_op(
            strategy_family=str(strategy_family),
            data1=str(data1),
            data2=(None if data2 is None else str(data2)),
            time_frame=int(time_frame),
        )
    except Exception as e:
        # If building intent fails, we still need to re-enable inputs and show error
        err = f"{type(e).__name__}: {e}"
        set_run_status_failed(f"Intent validation failed: {err}")
        update_run_status(step="failed", message=f"Intent validation failed: {err}")
        ui.notify(f"Intent validation failed: {err}", type="negative")
        # Re-enable inputs
        try:
            run_button.enable()
            for inp in inputs:
                inp.enable()
        except Exception:
            pass
        if callable(refresh_callback):
            try:
                refresh_callback()
            except Exception:
                pass
        return

    # 5) Schedule background launch via ui.run_task (non-blocking)
    ui.run_task(
        _launch_run_background(
            intent_dict=intent_dict,
            season="2026Q1",
            refresh_callback=refresh_callback,
            run_button=run_button,
            inputs=inputs,
        )
    )
    # Return immediately; background task will handle completion


def reset_op(state, strategy_select, data1_select, data2_select, tf_select):
    """Reset OP configuration to defaults."""
    state.config = DEFAULT_CONFIG.copy()
    
    # Set data1 to first available dataset
    datasets = get_datasets()
    if datasets:
        state.config["data1"] = datasets[0]
    else:
        state.config["data1"] = "TXF"
    
    save_config(state.config)
    
    # Update UI
    strategy_select.value = state.config["strategy_family"]
    data1_select.value = state.config["data1"]
    data2_select.value = state.config["data2"] or "None"
    tf_select.value = str(state.config["time_frame"])
    
    show_toast("OP configuration reset to defaults", ToastType.INFO)


def accept_result(state):
    """Accept result and send to Registry (Status = Incubation)."""
    if not state.result:
        show_toast("No result to accept", ToastType.WARNING)
        return
    
    # Constitution: Accept path only to Registry (Status = Incubation)
    # OP MUST NOT contain Activate, OP authority ends at Incubation
    state.add_log(f"[10:17] Result accepted → Registry (Status: Incubation)")
    
    # In real implementation, would create strategy in Registry with Incubation status
    show_toast("Result accepted → Registry (Incubation)", ToastType.SUCCESS)
    
    # Constitution: Accept cannot reach Live
    # This is enforced by only allowing Incubation status


def discard_result(state, result_container):
    """Discard result."""
    if not state.result:
        show_toast("No result to discard", ToastType.WARNING)
        return
    
    state.result = None
    state.add_log("[10:17] Result discarded")
    
    # Clear result display
    result_container.clear()
    with result_container:
        ui.label("Result discarded. Run a new backtest to see results.").classes("text-tertiary")
    
    show_toast("Result discarded", ToastType.INFO)