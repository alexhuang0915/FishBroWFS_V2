"""Wizard page (CORE).

Stepper with 5 steps:
1. Mode (single-select)
2. Universe (TF single, Instrument single, Regime multi with NONE rule)
3. Strategies (Long/Short multi-select, S1/S2/S3 each)
4. Scan / Compute (preview + limits)
5. Launch (intent preview + confirm)

Wizard is the ONLY place allowed to create a run.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from nicegui import ui
from .. import ui_compat as uic

from ..layout.cards import render_card
from ..layout.toasts import show_toast, ToastType
from ..state.wizard_state import WizardState
from ..state.app_state import AppState
from ..services.intent_service import write_intent, validate_intent
from ..services.derive_service import derive_and_write
from ..models.intent_models import IntentDocument
from ..services.strategy_catalog_service import list_real_strategy_ids
from ..services.run_launcher_service import launch_run_from_experiment_yaml, list_experiment_yamls
from ..constitution.page_shell import page_shell

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True


def render() -> None:
    """Render the Wizard page."""
    state = WizardState()
    app_state = AppState.get()
    
    def render_content():
        ui.label("Intent Wizard").classes("text-2xl font-bold text-primary mb-6")
        ui.label("Define your explicit intent. Machine will derive and execute.").classes("text-secondary mb-8")
        
        # Experiment YAML quick launch section
        ui.label("Quick Launch from Experiment YAML").classes("text-xl font-bold text-primary mt-8 mb-4")
        ui.label("Launch a pre-configured experiment from baseline_no_flip configurations.").classes("text-secondary mb-4")
        
        # Dropdown for experiment YAMLs
        yaml_files = list_experiment_yamls()
        yaml_options = [Path(p).name for p in yaml_files]
        yaml_paths = {Path(p).name: p for p in yaml_files}
        
        yaml_select = uic.select("Experiment YAML", yaml_options, value=None).classes("w-full")
        season_input = uic.input_text("Season", value=app_state.season).classes("w-1/3")
        
        result_label = ui.label("").classes("text-sm font-mono mt-2")
        run_dir_label = ui.label("").classes("text-sm font-mono mt-1")
        
        def launch_from_yaml():
            yaml_name = yaml_select.value
            if not yaml_name:
                show_toast("Please select an experiment YAML", ToastType.WARNING)
                return
            yaml_path = yaml_paths.get(yaml_name)
            if not yaml_path:
                show_toast(f"YAML file not found: {yaml_name}", ToastType.ERROR)
                return
            season = season_input.value.strip()
            if not season:
                show_toast("Season is required", ToastType.WARNING)
                return
            
            result_label.set_text("Launching...")
            run_dir_label.set_text("")
            
            # Call the launch service
            result = launch_run_from_experiment_yaml(yaml_path, season)
            
            if result.ok:
                show_toast(f"Run launched successfully: {result.run_id}", ToastType.SUCCESS)
                result_label.set_text(f"✓ Success: {result.message}")
                if result.run_dir:
                    run_dir_label.set_text(f"Run directory: {result.run_dir}")
                    # Add button to open run folder
                    ui.button("Open run folder", on_click=lambda: _open_run_folder(result.run_dir)).classes("mt-2")
            else:
                show_toast(f"Launch failed: {result.message}", ToastType.ERROR)
                result_label.set_text(f"✗ Failed: {result.message}")
        
        def _open_run_folder(run_dir: Path):
            import subprocess
            try:
                subprocess.run(["xdg-open", str(run_dir)], check=False)
            except Exception as e:
                logger.warning(f"Failed to open folder: {e}")
                show_toast(f"Cannot open folder: {e}", ToastType.WARNING)
        
        ui.button("Launch Run from YAML", on_click=launch_from_yaml, icon="rocket").classes("mt-4 mb-8")
        
        ui.separator().classes("my-8")
        
        # Stepper
        with ui.stepper().props("vertical").classes("w-full") as stepper:
            # Step 1: Mode
            with ui.step("Mode"):
                ui.label("Select run mode").classes("text-lg font-bold mb-2")
                mode_select = ui.radio(["SMOKE", "LITE", "FULL"], value=state.run_mode).props("inline")
                ui.label("SMOKE: quick validation, LITE: limited combos, FULL: exhaustive").classes("text-tertiary text-sm")
                
                def on_mode_change():
                    state.run_mode = mode_select.value
                    update_preview()
                
                mode_select.on("update:model-value", lambda e: on_mode_change())
                
                with ui.stepper_navigation():
                    uic.button("Next", on_click=stepper.next)
            
            # Step 2: Universe
            with ui.step("Universe"):
                ui.label("Market / Universe").classes("text-lg font-bold mb-2")
                with ui.row().classes("w-full gap-4"):
                    tf_select = uic.select("Timeframe", ["30m", "60m", "120m", "240m"], value=state.timeframe).classes("w-1/3")
                    instr_select = uic.select("Instrument", ["MNQ", "MES", "MYM", "M2K"], value=state.instrument).classes("w-1/3")
                
                ui.label("Regime Filters (optional)").classes("mt-4")
                regime_vars = {}
                regime_container = ui.row().classes("flex-wrap gap-2")
                with regime_container:
                    for reg in ["VX", "DX", "ZN", "6J"]:
                        cb = uic.checkbox(reg)
                        regime_vars[reg] = cb
                
                none_cb = uic.checkbox("NONE (disable regime filtering)", classes="mt-2 w-full")
                
                def on_universe_change():
                    state.timeframe = tf_select.value
                    state.instrument = instr_select.value
                    state.regime_none = none_cb.value
                    if state.regime_none:
                        state.regime_filters = []
                    else:
                        state.regime_filters = [reg for reg, cb in regime_vars.items() if cb.value]
                    update_preview()
                
                tf_select.on("update:model-value", lambda e: on_universe_change())
                instr_select.on("update:model-value", lambda e: on_universe_change())
                for cb in list(regime_vars.values()) + [none_cb]:
                    cb.on("update:model-value", lambda e: on_universe_change())
                
                with ui.stepper_navigation():
                    uic.button("Back", on_click=stepper.previous)
                    uic.button("Next", on_click=stepper.next)
            
            # Step 3: Strategies
            with ui.step("Strategies"):
                ui.label("Strategy Space").classes("text-lg font-bold mb-2")
                ui.label("Select real strategies for long and short sides (S1/S2/S3 only).").classes("text-tertiary text-sm mb-4")
                with ui.row().classes("w-full gap-8"):
                    with ui.column().classes("w-1/2"):
                        ui.label("Long Strategies").classes("font-bold")
                        long_checks = {}
                        for strategy_id in list_real_strategy_ids():
                            cb = uic.checkbox(strategy_id)
                            long_checks[strategy_id] = cb
                    with ui.column().classes("w-1/2"):
                        ui.label("Short Strategies").classes("font-bold")
                        short_checks = {}
                        for strategy_id in list_real_strategy_ids():
                            cb = uic.checkbox(strategy_id)
                            short_checks[strategy_id] = cb
                
                def on_strategy_change():
                    state.long_strategies = [id for id, cb in long_checks.items() if cb.value]
                    state.short_strategies = [id for id, cb in short_checks.items() if cb.value]
                    update_preview()
                
                for cb in list(long_checks.values()) + list(short_checks.values()):
                    cb.on("update:model-value", lambda e: on_strategy_change())
                
                with ui.stepper_navigation():
                    uic.button("Back", on_click=stepper.previous)
                    uic.button("Next", on_click=stepper.next)
            
            # Step 4: Scan / Compute
            with ui.step("Scan"):
                ui.label("Compute Intent").classes("text-lg font-bold mb-2")
                compute_select = uic.select("Compute Level", ["LOW", "MID", "HIGH"], value=state.compute_level).classes("w-1/3")
                max_comb_input = uic.input_number("Max Combinations", value=state.max_combinations, min=1, max=100000).classes("w-1/3")
                
                preview_card = render_card(
                    title="Preview",
                    content="",
                    icon="calculate",
                    color="warning",
                    width="w-full",
                )
                
                def on_compute_change():
                    state.compute_level = compute_select.value
                    state.max_combinations = max_comb_input.value
                    update_preview()
                
                compute_select.on("update:model-value", lambda e: on_compute_change())
                max_comb_input.on("update:model-value", lambda e: on_compute_change())
                
                with ui.stepper_navigation():
                    uic.button("Back", on_click=stepper.previous)
                    uic.button("Next", on_click=stepper.next)
            
            # Step 5: Launch
            with ui.step("Launch"):
                ui.label("Intent Preview & Confirm").classes("text-lg font-bold mb-2")
                intent_preview = ui.textarea("").props("readonly").classes("w-full h-64 font-mono text-sm")
                
                ui.label("Product / Risk Assumptions").classes("mt-4")
                margin_input = uic.input_text("Margin Model", value=state.margin_model).classes("w-full")
                contract_input = uic.input_text("Contract Specs (JSON)", value=json.dumps(state.contract_specs)).classes("w-full")
                risk_input = uic.input_text("Risk Budget", value=state.risk_budget).classes("w-full")
                
                def on_assumptions_change():
                    state.margin_model = margin_input.value
                    try:
                        state.contract_specs = json.loads(contract_input.value)
                    except json.JSONDecodeError:
                        # keep previous
                        pass
                    state.risk_budget = risk_input.value
                    update_preview()
                
                margin_input.on("update:model-value", lambda e: on_assumptions_change())
                contract_input.on("update:model-value", lambda e: on_assumptions_change())
                risk_input.on("update:model-value", lambda e: on_assumptions_change())
                
                with ui.stepper_navigation():
                    uic.button("Back", on_click=stepper.previous)
                    uic.button("Launch Run", on_click=lambda: launch_run(state, app_state, intent_preview))
        
        # Footer note
        ui.label("Wizard is the ONLY place allowed to create a run.").classes("text-xs text-muted mt-8")
        
        # Preview update logic
        def update_preview():
            """Update preview card and intent preview textarea."""
            # Update preview card content
            content_lines = []
            content_lines.append(f"Estimated combinations: {state.estimated_combinations}")
            content_lines.append(f"Risk class: {state.risk_class}")
            content_lines.append("Execution time: ~45 min")  # placeholder
            preview_card.content = "\n".join(content_lines)
            
            # Update intent preview JSON
            try:
                intent_dict = state.to_intent_dict()
                # Validate and maybe compute derived preview
                is_valid, errors = validate_intent(intent_dict)
                if is_valid:
                    intent_doc = IntentDocument.model_validate(intent_dict)
                    # TODO: call derive service to compute estimated_combinations and risk_class
                    # For now, dummy values
                    state.estimated_combinations = 240
                    state.risk_class = "MEDIUM"
                    content_lines[0] = f"Estimated combinations: {state.estimated_combinations}"
                    content_lines[1] = f"Risk class: {state.risk_class}"
                    preview_card.content = "\n".join(content_lines)
                else:
                    intent_dict["validation_errors"] = errors
                intent_preview.value = json.dumps(intent_dict, indent=2)
            except Exception as e:
                intent_preview.value = f"Error generating preview: {e}"
        
        # Initial preview update
        update_preview()
    
    # Wrap in page shell
    page_shell("Intent Wizard", render_content)


def launch_run(state: WizardState, app_state: AppState, preview_textarea) -> None:
    """Write intent.json, derive, create run directory."""
    try:
        intent_dict = state.to_intent_dict()
        is_valid, errors = validate_intent(intent_dict)
        if not is_valid:
            show_toast(f"Intent validation failed: {errors}", ToastType.ERROR)
            return
        
        intent_doc = IntentDocument.model_validate(intent_dict)
        # Write intent.json
        intent_path = write_intent(intent_doc, season=app_state.season)
        logger.info(f"Intent written to {intent_path}")
        
        # Derive derived.json
        derived_path = derive_and_write(intent_path)
        if derived_path is None:
            show_toast("Derivation failed", ToastType.ERROR)
            return
        
        # TODO: Trigger execution pipeline (call backend API maybe)
        
        show_toast(
            f"Run created! Intent: {intent_path.parent.name}",
            ToastType.SUCCESS
        )
        # Optionally reset wizard
        state.reset()
        
    except Exception as e:
        logger.exception("Launch failed")
        show_toast(f"Launch failed: {e}", ToastType.ERROR)
