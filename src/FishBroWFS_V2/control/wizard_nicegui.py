
"""Research Job Wizard (Phase 12) - NiceGUI interface.

Phase 12: Config-only wizard that outputs JobSpec JSON.
GUI → POST /jobs (JobSpec) only, no worker calls, no filesystem access.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
from nicegui import ui

from FishBroWFS_V2.control.job_spec import DataSpec, JobSpec, WFSSpec
from FishBroWFS_V2.control.param_grid import GridMode, ParamGridSpec
from FishBroWFS_V2.control.job_expand import JobTemplate, expand_job_template, estimate_total_jobs
from FishBroWFS_V2.control.batch_submit import BatchSubmitRequest, BatchSubmitResponse
from FishBroWFS_V2.data.dataset_registry import DatasetRecord
from FishBroWFS_V2.strategy.param_schema import ParamSpec
from FishBroWFS_V2.strategy.registry import StrategySpecForGUI

# API base URL
API_BASE = "http://localhost:8000"


class WizardState:
    """State management for wizard steps."""
    
    def __init__(self) -> None:
        self.season: str = ""
        self.data1: Optional[DataSpec] = None
        self.data2: Optional[DataSpec] = None
        self.strategy_id: str = ""
        self.params: Dict[str, Any] = {}
        self.wfs = WFSSpec()
        
        # Phase 13: Batch mode
        self.batch_mode: bool = False
        self.param_grid_specs: Dict[str, ParamGridSpec] = {}
        self.job_template: Optional[JobTemplate] = None
        
        # UI references
        self.data1_widgets: Dict[str, Any] = {}
        self.data2_widgets: Dict[str, Any] = {}
        self.param_widgets: Dict[str, Any] = {}
        self.wfs_widgets: Dict[str, Any] = {}
        self.batch_widgets: Dict[str, Any] = {}


def fetch_datasets() -> List[DatasetRecord]:
    """Fetch dataset registry from API."""
    try:
        resp = requests.get(f"{API_BASE}/meta/datasets", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [DatasetRecord.model_validate(d) for d in data["datasets"]]
    except Exception as e:
        ui.notify(f"Failed to load datasets: {e}", type="negative")
        return []


def fetch_strategies() -> List[StrategySpecForGUI]:
    """Fetch strategy registry from API."""
    try:
        resp = requests.get(f"{API_BASE}/meta/strategies", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [StrategySpecForGUI.model_validate(s) for s in data["strategies"]]
    except Exception as e:
        ui.notify(f"Failed to load strategies: {e}", type="negative")
        return []


def create_data_section(
    state: WizardState,
    section_name: str,
    is_primary: bool = True
) -> Dict[str, Any]:
    """Create dataset selection UI section."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label(f"{section_name} Dataset").classes("text-lg font-bold")
        
        # Dataset dropdown
        datasets = fetch_datasets()
        dataset_options = {d.id: f"{d.symbol} ({d.timeframe}) {d.start_date}-{d.end_date}" 
                          for d in datasets}
        
        dataset_select = ui.select(
            label="Dataset",
            options=dataset_options,
            with_input=True
        ).classes("w-full")
        widgets["dataset_select"] = dataset_select
        
        # Date range inputs
        with ui.row().classes("w-full"):
            start_date = ui.date(
                label="Start Date",
                value=date(2020, 1, 1)
            ).classes("w-1/2")
            widgets["start_date"] = start_date
            
            end_date = ui.date(
                label="End Date",
                value=date(2024, 12, 31)
            ).classes("w-1/2")
            widgets["end_date"] = end_date
        
        # Update date limits when dataset changes
        def update_date_limits(selected_id: str) -> None:
            dataset = next((d for d in datasets if d.id == selected_id), None)
            if dataset:
                start_date.value = dataset.start_date
                end_date.value = dataset.end_date
                start_date._props["min"] = dataset.start_date.isoformat()
                start_date._props["max"] = dataset.end_date.isoformat()
                end_date._props["min"] = dataset.start_date.isoformat()
                end_date._props["max"] = dataset.end_date.isoformat()
                start_date.update()
                end_date.update()
        
        dataset_select.on_change(lambda e: update_date_limits(e.value))
        
        # Set initial limits if dataset is selected
        if dataset_select.value:
            update_date_limits(dataset_select.value)
    
    return widgets


def create_strategy_section(state: WizardState) -> Dict[str, Any]:
    """Create strategy selection and parameter UI section."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label("Strategy").classes("text-lg font-bold")
        
        # Strategy dropdown
        strategies = fetch_strategies()
        strategy_options = {s.strategy_id: s.strategy_id for s in strategies}
        
        strategy_select = ui.select(
            label="Strategy",
            options=strategy_options,
            with_input=True
        ).classes("w-full")
        widgets["strategy_select"] = strategy_select
        
        # Parameter container (dynamic)
        param_container = ui.column().classes("w-full mt-4")
        widgets["param_container"] = param_container
        
        def update_parameters(selected_id: str) -> None:
            """Update parameter UI based on selected strategy."""
            param_container.clear()
            state.param_widgets.clear()
            
            strategy = next((s for s in strategies if s.strategy_id == selected_id), None)
            if not strategy:
                return
            
            ui.label("Parameters").classes("font-bold mt-2")
            
            for param in strategy.params:
                with ui.row().classes("w-full items-center"):
                    ui.label(f"{param.name}:").classes("w-1/3")
                    
                    if param.type == "int" or param.type == "float":
                        # Slider for numeric parameters
                        min_val = param.min if param.min is not None else 0
                        max_val = param.max if param.max is not None else 100
                        step = param.step if param.step is not None else 1
                        
                        slider = ui.slider(
                            min=min_val,
                            max=max_val,
                            value=param.default,
                            step=step
                        ).classes("w-2/3")
                        
                        value_label = ui.label().bind_text_from(
                            slider, "value", 
                            lambda v: f"{v:.2f}" if param.type == "float" else f"{int(v)}"
                        )
                        
                        state.param_widgets[param.name] = slider
                        
                    elif param.type == "enum" and param.choices:
                        # Dropdown for enum parameters
                        dropdown = ui.select(
                            options=param.choices,
                            value=param.default
                        ).classes("w-2/3")
                        state.param_widgets[param.name] = dropdown
                        
                    elif param.type == "bool":
                        # Switch for boolean parameters
                        switch = ui.switch(value=param.default).classes("w-2/3")
                        state.param_widgets[param.name] = switch
                    
                    # Help text
                    if param.help:
                        ui.tooltip(param.help).classes("ml-2")
        
        strategy_select.on_change(lambda e: update_parameters(e.value))
        
        # Initialize if strategy is selected
        if strategy_select.value:
            update_parameters(strategy_select.value)
    
    return widgets


def create_batch_mode_section(state: WizardState) -> Dict[str, Any]:
    """Create batch mode UI section (Phase 13)."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label("Batch Mode (Phase 13)").classes("text-lg font-bold")
        
        # Batch mode toggle
        batch_toggle = ui.switch("Enable Batch Mode (Parameter Grid)")
        widgets["batch_toggle"] = batch_toggle
        
        # Container for grid UI (hidden when batch mode off)
        grid_container = ui.column().classes("w-full mt-4")
        widgets["grid_container"] = grid_container
        
        # Cost preview label
        cost_label = ui.label("Total jobs: 0 | Risk: Low").classes("font-bold mt-2")
        widgets["cost_label"] = cost_label
        
        def update_batch_mode(enabled: bool) -> None:
            """Show/hide grid UI based on batch mode toggle."""
            grid_container.clear()
            state.batch_mode = enabled
            state.param_grid_specs.clear()
            
            if not enabled:
                cost_label.set_text("Total jobs: 0 | Risk: Low")
                return
            
            # Fetch current strategy parameters
            strategy_id = state.strategy_id
            strategies = fetch_strategies()
            strategy = next((s for s in strategies if s.strategy_id == strategy_id), None)
            if not strategy:
                ui.notify("No strategy selected", type="warning")
                return
            
            # Create grid UI for each parameter
            ui.label("Parameter Grid").classes("font-bold mt-2")
            
            for param in strategy.params:
                with ui.row().classes("w-full items-center mb-2"):
                    ui.label(f"{param.name}:").classes("w-1/4")
                    
                    # Grid mode selector
                    mode_select = ui.select(
                        options={
                            GridMode.SINGLE.value: "Single",
                            GridMode.RANGE.value: "Range",
                            GridMode.MULTI.value: "Multi Values"
                        },
                        value=GridMode.SINGLE.value
                    ).classes("w-1/4")
                    
                    # Value inputs (dynamic based on mode)
                    value_container = ui.row().classes("w-1/2")
                    
                    def make_param_updater(pname: str, mode_sel, val_container, param_spec):
                        def update_grid_ui():
                            mode = GridMode(mode_sel.value)
                            val_container.clear()
                            
                            if mode == GridMode.SINGLE:
                                # Single value input (same as default)
                                if param_spec.type == "int" or param_spec.type == "float":
                                    default = param_spec.default
                                    val = ui.number(value=default, min=param_spec.min, max=param_spec.max, step=param_spec.step or 1)
                                elif param_spec.type == "enum":
                                    val = ui.select(options=param_spec.choices, value=param_spec.default)
                                elif param_spec.type == "bool":
                                    val = ui.switch(value=param_spec.default)
                                else:
                                    val = ui.input(value=str(param_spec.default))
                                val_container.add(val)
                                # Store spec
                                state.param_grid_specs[pname] = ParamGridSpec(
                                    mode=mode,
                                    single_value=val.value
                                )
                            elif mode == GridMode.RANGE:
                                # Range: start, end, step
                                start = ui.number(value=param_spec.min or 0, label="Start")
                                end = ui.number(value=param_spec.max or 100, label="End")
                                step = ui.number(value=param_spec.step or 1, label="Step")
                                val_container.add(start)
                                val_container.add(end)
                                val_container.add(step)
                                # Store spec (will be updated on change)
                                state.param_grid_specs[pname] = ParamGridSpec(
                                    mode=mode,
                                    range_start=start.value,
                                    range_end=end.value,
                                    range_step=step.value
                                )
                            elif mode == GridMode.MULTI:
                                # Multi values: comma-separated input
                                default_vals = ",".join([str(param_spec.default)])
                                val = ui.input(value=default_vals, label="Values (comma separated)")
                                val_container.add(val)
                                state.param_grid_specs[pname] = ParamGridSpec(
                                    mode=mode,
                                    multi_values=[param_spec.default]
                                )
                            # Trigger cost update
                            update_cost_preview()
                        return update_grid_ui
                    
                    # Initial creation
                    updater = make_param_updater(param.name, mode_select, value_container, param)
                    mode_select.on_change(lambda e: updater())
                    updater()  # call once to create initial UI
        
        batch_toggle.on_change(lambda e: update_batch_mode(e.value))
        
        def update_cost_preview():
            """Update cost preview label based on current grid specs."""
            if not state.batch_mode:
                cost_label.set_text("Total jobs: 0 | Risk: Low")
                return
            
            # Build a temporary JobTemplate to estimate total jobs
            try:
                # Collect base JobSpec from current UI (simplified)
                # We'll just use dummy values for estimation
                template = JobTemplate(
                    season=state.season,
                    dataset_id="dummy",
                    strategy_id=state.strategy_id,
                    param_grid=state.param_grid_specs.copy(),
                    wfs=state.wfs
                )
                total = estimate_total_jobs(template)
                # Risk heuristic
                risk = "Low"
                if total > 100:
                    risk = "Medium"
                if total > 1000:
                    risk = "High"
                cost_label.set_text(f"Total jobs: {total} | Risk: {risk}")
            except Exception:
                cost_label.set_text("Total jobs: ? | Risk: Unknown")
        
        # Update cost preview periodically
        ui.timer(2.0, update_cost_preview)
    
    return widgets


def create_wfs_section(state: WizardState) -> Dict[str, Any]:
    """Create WFS configuration UI section."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label("WFS Configuration").classes("text-lg font-bold")
        
        # Stage0 subsample
        subsample_slider = ui.slider(
            label="Stage0 Subsample",
            min=0.01,
            max=1.0,
            value=state.wfs.stage0_subsample,
            step=0.01
        ).classes("w-full")
        widgets["subsample"] = subsample_slider
        ui.label().bind_text_from(subsample_slider, "value", lambda v: f"{v:.2f}")
        
        # Top K
        top_k_input = ui.number(
            label="Top K",
            value=state.wfs.top_k,
            min=1,
            max=1000,
            step=10
        ).classes("w-full")
        widgets["top_k"] = top_k_input
        
        # Memory limit
        mem_input = ui.number(
            label="Memory Limit (MB)",
            value=state.wfs.mem_limit_mb,
            min=1024,
            max=32768,
            step=1024
        ).classes("w-full")
        widgets["mem_limit"] = mem_input
        
        # Auto-downsample switch
        auto_downsample = ui.switch(
            "Allow Auto Downsample",
            value=state.wfs.allow_auto_downsample
        ).classes("w-full")
        widgets["auto_downsample"] = auto_downsample
    
    return widgets


def create_preview_section(state: WizardState) -> ui.textarea:
    """Create JobSpec preview section."""
    with ui.card().classes("w-full mb-4"):
        ui.label("JobSpec Preview").classes("text-lg font-bold")
        
        preview = ui.textarea("").classes("w-full h-64 font-mono text-sm").props("readonly")
        
        def update_preview() -> None:
            """Update JobSpec preview."""
            try:
                # Collect data from UI
                dataset_id = None
                if state.data1_widgets:
                    dataset_id = state.data1_widgets["dataset_select"].value
                    start_date = state.data1_widgets["start_date"].value
                    end_date = state.data1_widgets["end_date"].value
                    
                    if dataset_id and start_date and end_date:
                        state.data1 = DataSpec(
                            dataset_id=dataset_id,
                            start_date=start_date,
                            end_date=end_date
                        )
                
                # Collect strategy parameters
                params = {}
                for param_name, widget in state.param_widgets.items():
                    if hasattr(widget, 'value'):
                        params[param_name] = widget.value
                
                # Collect WFS settings
                if state.wfs_widgets:
                    state.wfs = WFSSpec(
                        stage0_subsample=state.wfs_widgets["subsample"].value,
                        top_k=state.wfs_widgets["top_k"].value,
                        mem_limit_mb=state.wfs_widgets["mem_limit"].value,
                        allow_auto_downsample=state.wfs_widgets["auto_downsample"].value
                    )
                
                if state.batch_mode:
                    # Create JobTemplate
                    template = JobTemplate(
                        season=state.season,
                        dataset_id=dataset_id if dataset_id else "unknown",
                        strategy_id=state.strategy_id,
                        param_grid=state.param_grid_specs.copy(),
                        wfs=state.wfs
                    )
                    # Update preview with template JSON
                    preview.value = template.model_dump_json(indent=2)
                else:
                    # Create single JobSpec
                    jobspec = JobSpec(
                        season=state.season,
                        data1=state.data1,
                        data2=state.data2,
                        strategy_id=state.strategy_id,
                        params=params,
                        wfs=state.wfs
                    )
                    # Update preview
                    preview.value = jobspec.model_dump_json(indent=2)
                
            except Exception as e:
                preview.value = f"Error creating preview: {e}"
        
        # Update preview periodically
        ui.timer(1.0, update_preview)
        
        return preview


def submit_job(state: WizardState, preview: ui.textarea) -> None:
    """Submit JobSpec to API."""
    try:
        # Parse JobSpec from preview
        jobspec_data = json.loads(preview.value)
        jobspec = JobSpec.model_validate(jobspec_data)
        
        # Submit to API
        resp = requests.post(
            f"{API_BASE}/jobs",
            json=json.loads(jobspec.model_dump_json())
        )
        resp.raise_for_status()
        
        job_id = resp.json()["job_id"]
        ui.notify(f"Job submitted successfully! Job ID: {job_id}", type="positive")
        
    except Exception as e:
        ui.notify(f"Failed to submit job: {e}", type="negative")


def submit_batch_job(state: WizardState, preview: ui.textarea) -> None:
    """Submit batch of jobs via batch API."""
    try:
        # Parse JobTemplate from preview
        template_data = json.loads(preview.value)
        template = JobTemplate.model_validate(template_data)
        
        # Expand template to JobSpec list
        jobspecs = expand_job_template(template)
        
        # Build batch request
        batch_req = BatchSubmitRequest(jobs=list(jobspecs))
        
        # Submit to batch endpoint
        resp = requests.post(
            f"{API_BASE}/jobs/batch",
            json=json.loads(batch_req.model_dump_json())
        )
        resp.raise_for_status()
        
        batch_resp = BatchSubmitResponse.model_validate(resp.json())
        ui.notify(
            f"Batch submitted successfully! Batch ID: {batch_resp.batch_id}, "
            f"Total jobs: {batch_resp.total_jobs}",
            type="positive"
        )
        
    except Exception as e:
        ui.notify(f"Failed to submit batch: {e}", type="negative")


@ui.page("/wizard")
def wizard_page() -> None:
    """Research Job Wizard main page."""
    ui.page_title("Research Job Wizard (Phase 12)")
    
    state = WizardState()
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-4"):
        ui.label("Research Job Wizard").classes("text-2xl font-bold mb-6")
        ui.label("Phase 12: Config-only job specification").classes("text-gray-600 mb-8")
        
        # Season input
        with ui.card().classes("w-full mb-4"):
            ui.label("Season").classes("text-lg font-bold")
            season_input = ui.input(
                label="Season",
                value="2024Q1",
                placeholder="e.g., 2024Q1, 2024Q2"
            ).classes("w-full")
            
            def update_season() -> None:
                state.season = season_input.value
            
            season_input.on_change(lambda e: update_season())
            update_season()
        
        # Step 1: Data
        with ui.expansion("Step 1: Data", value=True).classes("w-full mb-4"):
            ui.label("Primary Dataset").classes("font-bold mt-2")
            state.data1_widgets = create_data_section(state, "Primary", is_primary=True)
            
            # Data2 toggle
            enable_data2 = ui.switch("Enable Secondary Dataset (for validation)")
            
            data2_container = ui.column().classes("w-full")
            
            def toggle_data2(enabled: bool) -> None:
                data2_container.clear()
                if enabled:
                    state.data2_widgets = create_data_section(state, "Secondary", is_primary=False)
                else:
                    state.data2 = None
                    state.data2_widgets = {}
            
            enable_data2.on_change(lambda e: toggle_data2(e.value))
        
        # Step 2: Strategy
        with ui.expansion("Step 2: Strategy", value=True).classes("w-full mb-4"):
            strategy_widgets = create_strategy_section(state)
            
            def update_strategy() -> None:
                state.strategy_id = strategy_widgets["strategy_select"].value
            
            strategy_widgets["strategy_select"].on_change(lambda e: update_strategy())
            if strategy_widgets["strategy_select"].value:
                update_strategy()
        
        # Step 3: Batch Mode (Phase 13)
        with ui.expansion("Step 3: Batch Mode (Optional)", value=True).classes("w-full mb-4"):
            state.batch_widgets = create_batch_mode_section(state)
        
        # Step 4: WFS
        with ui.expansion("Step 4: WFS Configuration", value=True).classes("w-full mb-4"):
            state.wfs_widgets = create_wfs_section(state)
        
        # Step 5: Preview & Submit
        with ui.expansion("Step 5: Preview & Submit", value=True).classes("w-full mb-4"):
            preview = create_preview_section(state)
            
            with ui.row().classes("w-full mt-4"):
                # Conditional button based on batch mode
                def submit_action():
                    if state.batch_mode:
                        submit_batch_job(state, preview)
                    else:
                        submit_job(state, preview)
                
                submit_btn = ui.button(
                    "Submit Batch" if state.batch_mode else "Submit Job",
                    on_click=submit_action
                ).classes("bg-green-500 text-white")
                
                # Update button label when batch mode changes
                def update_button_label():
                    submit_btn.set_text("Submit Batch" if state.batch_mode else "Submit Job")
                
                # Watch batch mode changes (simplified: we can't directly watch, but we can update via timer)
                ui.timer(1.0, update_button_label)
                
                ui.button("Copy JSON", on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText(`{preview.value}`)"
                )).classes("bg-blue-500 text-white")
        
        # Phase 12 Rules reminder
        with ui.card().classes("w-full mt-8 bg-yellow-50"):
            ui.label("Phase 12 Rules").classes("font-bold text-yellow-800")
            ui.label("✅ GUI only outputs JobSpec JSON").classes("text-sm text-yellow-700")
            ui.label("✅ No worker calls, no filesystem access").classes("text-sm text-yellow-700")
            ui.label("✅ Strategy params from registry, not hardcoded").classes("text-sm text-yellow-700")
            ui.label("✅ Dataset selection from registry, not filesystem").classes("text-sm text-yellow-700")




