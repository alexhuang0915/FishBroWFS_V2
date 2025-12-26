"""M1 Wizard - Five-step wizard for job creation.

Step1: DATA1 (dataset / symbols / timeframes)
Step2: DATA2 (optional; single filter)
Step3: Strategies (schema-driven)
Step4: Cost
Step5: Summary (must show Units formula and number)
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from datetime import date

from nicegui import ui

# Use intent-based system for Attack #9 - Headless Intent-State Contract
from FishBroWFS_V2.gui.adapters.intent_bridge import (
    migrate_ui_imports,
    ValidationError,
    SeasonFrozenError,
)

# Migrate imports to use intent bridge
migrate_ui_imports()

# The migrate_ui_imports() function replaces the following imports
# with intent-based implementations:
# - create_job_from_wizard
# - calculate_units
# - check_season_not_frozen
# - get_dataset_catalog
# - get_strategy_catalog
# - ValidationError (re-exported)
# - SeasonFrozenError (re-exported)


class M1WizardState:
    """State management for M1 wizard."""
    
    def __init__(self):
        # Step 1: DATA1
        self.season: str = "2024Q1"
        self.dataset_id: str = ""
        self.symbols: List[str] = []
        self.timeframes: List[str] = []
        self.start_date: Optional[date] = None
        self.end_date: Optional[date] = None
        
        # Step 2: DATA2
        self.enable_data2: bool = False
        self.data2_dataset_id: str = ""
        self.data2_filters: List[str] = []
        self.selected_filter: str = ""
        
        # Step 3: Strategies
        self.strategy_id: str = ""
        self.params: Dict[str, Any] = {}
        
        # Step 4: Cost (calculated)
        self.units: int = 0
        
        # Step 5: Summary
        self.job_id: Optional[str] = None
        
        # UI references
        self.step_containers: Dict[int, Any] = {}
        self.current_step: int = 1


def create_step_indicator(state: M1WizardState) -> None:
    """Create step indicator UI."""
    with ui.row().classes("w-full mb-8 gap-2"):
        steps = [
            (1, "DATA1", state.current_step == 1),
            (2, "DATA2", state.current_step == 2),
            (3, "Strategies", state.current_step == 3),
            (4, "Cost", state.current_step == 4),
            (5, "Summary", state.current_step == 5),
        ]
        
        for step_num, label, active in steps:
            with ui.column().classes("items-center"):
                ui.label(str(step_num)).classes(
                    f"w-8 h-8 rounded-full flex items-center justify-center font-bold "
                    f"{'bg-blue-500 text-white' if active else 'bg-gray-200 text-gray-600'}"
                )
                ui.label(label).classes(
                    f"text-sm mt-1 {'font-bold text-blue-600' if active else 'text-gray-500'}"
                )


def create_step1_data1(state: M1WizardState) -> None:
    """Create Step 1: DATA1 UI."""
    with state.step_containers[1]:
        ui.label("Step 1: DATA1 Configuration").classes("text-xl font-bold mb-4")
        
        # Season input
        from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_input, labeled_select, labeled_date
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Season")
            season_input = ui.input(
                value=state.season,
                placeholder="e.g., 2024Q1, 2024Q2"
            ).classes("w-full")
            season_input.bind_value(state, 'season')
        
        # Dataset selection
        catalog = get_dataset_catalog()
        datasets = catalog.list_datasets()
        dataset_options = {d.id: f"{d.symbol} ({d.timeframe}) {d.start_date}-{d.end_date}"
                          for d in datasets}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Dataset")
            dataset_select = ui.select(
                options=dataset_options,
                with_input=True
            ).classes("w-full")
            dataset_select.bind_value(state, 'dataset_id')
        
        # Symbols input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Symbols (comma separated)")
            symbols_input = ui.input(
                value="MNQ, MXF",
                placeholder="e.g., MNQ, MXF, MES"
            ).classes("w-full")
            symbols_input.bind_value(state, 'symbols')
        
        # Timeframes input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Timeframes (comma separated)")
            timeframes_input = ui.input(
                value="60m, 120m",
                placeholder="e.g., 60m, 120m, 240m"
            ).classes("w-full")
            timeframes_input.bind_value(state, 'timeframes')
        
        # Date range
        with ui.row().classes("w-full"):
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("Start Date")
                start_date = ui.date(
                    value=date(2020, 1, 1)
                ).classes("w-full")
                start_date.bind_value(state, 'start_date')
            
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("End Date")
                end_date = ui.date(
                    value=date(2024, 12, 31)
                ).classes("w-full")
                end_date.bind_value(state, 'end_date')
        
        # Initialize state with parsed values
        def parse_initial_values():
            if isinstance(state.symbols, str):
                state.symbols = [s.strip() for s in state.symbols.split(",") if s.strip()]
            elif not isinstance(state.symbols, list):
                state.symbols = []
            
            if isinstance(state.timeframes, str):
                state.timeframes = [t.strip() for t in state.timeframes.split(",") if t.strip()]
            elif not isinstance(state.timeframes, list):
                state.timeframes = []
        
        parse_initial_values()


def create_step2_data2(state: M1WizardState) -> None:
    """Create Step 2: DATA2 UI (optional, single filter)."""
    with state.step_containers[2]:
        ui.label("Step 2: DATA2 Configuration (Optional)").classes("text-xl font-bold mb-4")
        
        # Enable DATA2 toggle
        enable_toggle = ui.switch("Enable DATA2 (single filter validation)")
        enable_toggle.bind_value(state, 'enable_data2')
        
        # DATA2 container (initially hidden)
        data2_container = ui.column().classes("w-full mt-4")
        
        def update_data2_visibility(enabled: bool):
            data2_container.clear()
            if not enabled:
                state.data2_dataset_id = ""
                state.data2_filters = []
                state.selected_filter = ""
                return
            
            with data2_container:
                # Dataset selection for DATA2
                catalog = get_dataset_catalog()
                datasets = catalog.list_datasets()
                dataset_options = {d.id: f"{d.symbol} ({d.timeframe})" for d in datasets}
                
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("DATA2 Dataset")
                    dataset_select = ui.select(
                        options=dataset_options,
                        with_input=True
                    ).classes("w-full")
                    dataset_select.bind_value(state, 'data2_dataset_id')
                
                # Filter selection (single filter)
                filter_options = ["momentum", "volatility", "trend", "mean_reversion"]
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("Filter")
                    filter_select = ui.select(
                        options=filter_options,
                        value=filter_options[0] if filter_options else ""
                    ).classes("w-full")
                    filter_select.bind_value(state, 'selected_filter')
                
                # Initialize state
                state.data2_filters = filter_options
                if not state.selected_filter and filter_options:
                    state.selected_filter = filter_options[0]
        
        # Use timer to update visibility when enable_data2 changes
        def update_visibility_from_state():
            update_data2_visibility(state.enable_data2)
        
        ui.timer(0.2, update_visibility_from_state)
        
        # Initial visibility
        update_data2_visibility(state.enable_data2)


def create_step3_strategies(state: M1WizardState) -> None:
    """Create Step 3: Strategies UI (schema-driven)."""
    with state.step_containers[3]:
        ui.label("Step 3: Strategy Selection").classes("text-xl font-bold mb-4")
        
        # Strategy selection
        catalog = get_strategy_catalog()
        strategies = catalog.list_strategies()
        strategy_options = {s.strategy_id: s.strategy_id for s in strategies}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Strategy")
            strategy_select = ui.select(
                options=strategy_options,
                with_input=True
            ).classes("w-full")
            strategy_select.bind_value(state, 'strategy_id')
        
        # Parameters container (dynamic)
        param_container = ui.column().classes("w-full mt-4")
        
        def update_strategy_ui(selected_id: str):
            param_container.clear()
            state.strategy_id = selected_id
            state.params = {}
            
            if not selected_id:
                return
            
            strategy = catalog.get_strategy(selected_id)
            if not strategy:
                return
            
            ui.label("Parameters").classes("font-bold mt-2 mb-2")
            
            # Create UI for each parameter
            for param in strategy.params:
                with ui.row().classes("w-full items-center mb-3"):
                    ui.label(f"{param.name}:").classes("w-1/3 font-medium")
                    
                    if param.type == "int" or param.type == "float":
                        # Number input
                        min_val = param.min if param.min is not None else 0
                        max_val = param.max if param.max is not None else 100
                        step = param.step if param.step is not None else (1 if param.type == "int" else 0.1)
                        
                        input_field = ui.number(
                            value=param.default,
                            min=min_val,
                            max=max_val,
                            step=step
                        ).classes("w-2/3")
                        
                        # Use on('update:model-value') for immediate updates
                        def make_param_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        input_field.on('update:model-value', make_param_handler(param.name, input_field))
                        state.params[param.name] = param.default
                        
                    elif param.type == "enum" and param.choices:
                        # Dropdown for enum
                        dropdown = ui.select(
                            options=param.choices,
                            value=param.default
                        ).classes("w-2/3")
                        
                        def make_enum_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        dropdown.on('update:model-value', make_enum_handler(param.name, dropdown))
                        state.params[param.name] = param.default
                        
                    elif param.type == "bool":
                        # Switch for boolean
                        switch = ui.switch(value=param.default).classes("w-2/3")
                        
                        def make_bool_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        switch.on('update:model-value', make_bool_handler(param.name, switch))
                        state.params[param.name] = param.default
                    
                    # Help text
                    if param.help:
                        ui.tooltip(param.help).classes("ml-2")
        
        # Use timer to update UI when strategy_id changes
        def update_strategy_from_state():
            if state.strategy_id != getattr(update_strategy_from_state, '_last_strategy', None):
                update_strategy_ui(state.strategy_id)
                update_strategy_from_state._last_strategy = state.strategy_id
        
        ui.timer(0.2, update_strategy_from_state)
        
        # Initialize if strategy is selected
        if state.strategy_id:
            update_strategy_ui(state.strategy_id)
        elif strategies:
            # Select first strategy by default
            first_strategy = strategies[0].strategy_id
            state.strategy_id = first_strategy
            update_strategy_ui(first_strategy)


def create_step4_cost(state: M1WizardState) -> None:
    """Create Step 4: Cost UI (Units calculation)."""
    with state.step_containers[4]:
        ui.label("Step 4: Cost Estimation").classes("text-xl font-bold mb-4")
        
        # Units formula explanation
        with ui.card().classes("w-full mb-4 bg-blue-50"):
            ui.label("Units Formula").classes("font-bold text-blue-800")
            ui.label("Units = |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|").classes("font-mono text-sm text-blue-700")
            ui.label("Where |strategies| = 1 (single strategy) and |DATA2.filters| = 1 if DATA2 disabled").classes("text-sm text-blue-600")
        
        # Current configuration summary
        config_card = ui.card().classes("w-full mb-4")
        
        # Units calculation result
        units_label = ui.label("Calculating units...").classes("text-2xl font-bold text-green-600")
        
        def update_cost_display():
            with config_card:
                config_card.clear()
                
                # Build payload for units calculation
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Calculate units
                try:
                    units = calculate_units(payload)
                    state.units = units
                    
                    # Display configuration
                    ui.label("Current Configuration:").classes("font-bold mb-2")
                    
                    with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                        ui.label("Season:").classes("font-medium")
                        ui.label(state.season)
                        
                        ui.label("DATA1 Dataset:").classes("font-medium")
                        ui.label(state.dataset_id if state.dataset_id else "Not selected")
                        
                        ui.label("Symbols:").classes("font-medium")
                        ui.label(f"{len(state.symbols)}: {', '.join(state.symbols)}" if state.symbols else "None")
                        
                        ui.label("Timeframes:").classes("font-medium")
                        ui.label(f"{len(state.timeframes)}: {', '.join(state.timeframes)}" if state.timeframes else "None")
                        
                        ui.label("Strategy:").classes("font-medium")
                        ui.label(state.strategy_id if state.strategy_id else "Not selected")
                        
                        ui.label("DATA2 Enabled:").classes("font-medium")
                        ui.label("Yes" if state.enable_data2 else "No")
                        
                        if state.enable_data2:
                            ui.label("DATA2 Filter:").classes("font-medium")
                            ui.label(state.selected_filter)
                    
                    # Update units display
                    units_label.set_text(f"Total Units: {units}")
                    
                    # Cost estimation (simplified)
                    if units > 100:
                        ui.label("⚠️ High cost warning: This job may take significant resources").classes("text-yellow-600 mt-2")
                    
                except Exception as e:
                    units_label.set_text(f"Error calculating units: {str(e)}")
                    state.units = 0
        
        # Update cost display periodically
        ui.timer(1.0, update_cost_display)


def create_step5_summary(state: M1WizardState) -> None:
    """Create Step 5: Summary and Submit UI."""
    with state.step_containers[5]:
        ui.label("Step 5: Summary & Submit").classes("text-xl font-bold mb-4")
        
        # Summary card
        summary_card = ui.card().classes("w-full mb-4")
        
        # Submit button
        submit_button = ui.button("Submit Job", icon="send", color="green")
        
        # Result container
        result_container = ui.column().classes("w-full mt-4")
        
        def update_summary():
            summary_card.clear()
            
            with summary_card:
                ui.label("Job Summary").classes("font-bold mb-2")
                
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Display payload
                ui.label("Final Payload:").classes("font-medium mt-2")
                payload_json = json.dumps(payload, indent=2)
                ui.textarea(payload_json).classes("w-full h-48 font-mono text-xs").props("readonly")
                
                # Units display
                units = calculate_units(payload)
                ui.label(f"Total Units: {units}").classes("font-bold text-lg mt-2")
                ui.label("Units = |symbols| × |timeframes| × |strategies| × |filters|").classes("text-sm text-gray-600")
                ui.label(f"= {len(state.symbols)} × {len(state.timeframes)} × 1 × {1 if state.enable_data2 else 1} = {units}").classes("text-sm font-mono")
        
        def submit_job():
            result_container.clear()
            
            try:
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Check season not frozen
                check_season_not_frozen(state.season, action="submit_job")
                
                # Submit job
                result = create_job_from_wizard(payload)
                state.job_id = result["job_id"]
                
                # Show success message
                with result_container:
                    with ui.card().classes("w-full bg-green-50 border-green-200"):
                        ui.label("✅ Job Submitted Successfully!").classes("text-green-800 font-bold mb-2")
                        ui.label(f"Job ID: {result['job_id']}").classes("font-mono text-sm mb-1")
                        ui.label(f"Units: {result['units']}").classes("text-sm mb-1")
                        ui.label(f"Season: {result['season']}").classes("text-sm mb-3")
                        
                        # Navigation button
                        ui.button(
                            "View Job Details",
                            on_click=lambda: ui.navigate.to(f"/jobs/{result['job_id']}"),
                            icon="visibility"
                        ).classes("bg-green-600 text-white")
                
                # Disable submit button
                submit_button.disable()
                submit_button.set_text("Submitted")
                
            except SeasonFrozenError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Season is Frozen").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Cannot submit job: {str(e)}").classes("text-red-700")
            except ValidationError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Validation Error").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Please check your inputs: {str(e)}").classes("text-red-700")
            except Exception as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Submission Failed").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Error: {str(e)}").classes("text-red-700")
        
        submit_button.on_click(submit_job)
        
        # Navigation buttons
        with ui.row().classes("w-full justify-between mt-4"):
            ui.button("Previous Step",
                     on_click=lambda: navigate_to_step(4),
                     icon="arrow_back").props("outline")
            
            ui.button("Save Configuration",
                     on_click=lambda: ui.notify("Save functionality not implemented in M1", type="info"),
                     icon="save").props("outline")
        
        # Initial update
        update_summary()
        
        # Auto-update summary
        ui.timer(2.0, update_summary)


def navigate_to_step(step: int, state: M1WizardState) -> None:
    """Navigate to specific step."""
    if 1 <= step <= 5:
        state.current_step = step
        for step_num, container in state.step_containers.items():
            container.set_visibility(step_num == step)


@ui.page("/wizard")
def wizard_page() -> None:
    """M1 Wizard main page."""
    ui.page_title("FishBroWFS V2 - M1 Wizard")
    
    state = M1WizardState()
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
        # Header
        ui.label("🧙‍♂️ M1 Wizard").classes("text-3xl font-bold mb-2")
        ui.label("Five-step job configuration wizard").classes("text-lg text-gray-600 mb-6")
        
        # Step indicator
        create_step_indicator(state)
        
        # Create step containers (all initially hidden except step 1)
        for step in range(1, 6):
            container = ui.column().classes("w-full")
            container.set_visibility(step == 1)
            state.step_containers[step] = container
        
        # Create step content
        create_step1_data1(state)
        create_step2_data2(state)
        create_step3_strategies(state)
        create_step4_cost(state)
        create_step5_summary(state)
        
        # Navigation buttons (global)
        with ui.row().classes("w-full justify-between mt-8"):
            prev_button = ui.button("Previous",
                                   on_click=lambda: navigate_to_step(state.current_step - 1, state),
                                   icon="arrow_back")
            prev_button.props("disabled" if state.current_step == 1 else "")
            
            next_button = ui.button("Next",
                                   on_click=lambda: navigate_to_step(state.current_step + 1, state),
                                   icon="arrow_forward")
            next_button.props("disabled" if state.current_step == 5 else "")
            
            # Update button states based on current step
            def update_nav_buttons():
                prev_button.props("disabled" if state.current_step == 1 else "")
                next_button.props("disabled" if state.current_step == 5 else "")
                next_button.set_text("Submit" if state.current_step == 4 else "Next")
            
            ui.timer(0.5, update_nav_buttons)
        
        # Quick links
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("Quick links:")
            ui.link("Jobs List", "/jobs").classes("ml-4 text-blue-500 hover:text-blue-700")
            ui.link("Dashboard", "/").classes("ml-4 text-blue-500 hover:text-blue-700")


# Also register at /wizard/m1 for testing
@ui.page("/wizard/m1")
def wizard_m1_page() -> None:
    """Alternative route for M1 wizard."""
    wizard_page()
