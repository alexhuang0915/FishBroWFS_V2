"""NiceGUI app for B5-C Mission Control."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from nicegui import ui

from FishBroWFS_V2.core.config_hash import stable_config_hash
from FishBroWFS_V2.core.config_snapshot import make_config_snapshot

# API base URL (default to localhost)
API_BASE = "http://localhost:8000"


def create_job_from_config(cfg: dict) -> str:
    """
    Create job from config dict.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Job ID
    """
    
    # Sanitize config
    cfg_snapshot = make_config_snapshot(cfg)
    config_hash = stable_config_hash(cfg_snapshot)
    
    # Prepare request
    req = {
        "season": cfg.get("season", "default"),
        "dataset_id": cfg.get("dataset_id", "default"),
        "outputs_root": str(Path("outputs").absolute()),
        "config_snapshot": cfg_snapshot,
        "config_hash": config_hash,
        "created_by": "b5c",
    }
    
    # POST to API
    resp = requests.post(f"{API_BASE}/jobs", json=req)
    resp.raise_for_status()
    return resp.json()["job_id"]


def get_preflight_result(job_id: str) -> dict:
    """Get preflight result for a job."""
    
    resp = requests.post(f"{API_BASE}/jobs/{job_id}/check")
    resp.raise_for_status()
    return resp.json()


def list_jobs_api() -> list[dict]:
    """List jobs from API."""
    
    resp = requests.get(f"{API_BASE}/jobs")
    resp.raise_for_status()
    return resp.json()


@ui.page("/")
def main_page() -> None:
    """Main B5-C Mission Control page."""
    ui.page_title("B5-C Mission Control")
    
    with ui.row().classes("w-full"):
        # Left: Job List
        with ui.column().classes("w-1/3"):
            ui.label("Job List").classes("text-xl font-bold")
            job_list = ui.column().classes("w-full")
            
            def refresh_job_list() -> None:
                """Refresh job list."""
                job_list.clear()
                try:
                    jobs = list_jobs_api()
                    for job in jobs[:50]:  # Limit to 50
                        status = job["status"]
                        status_color = {
                            "QUEUED": "blue",
                            "RUNNING": "green",
                            "PAUSED": "yellow",
                            "DONE": "gray",
                            "FAILED": "red",
                            "KILLED": "red",
                        }.get(status, "gray")
                        
                        with ui.card().classes("w-full mb-2"):
                            ui.label(f"Job: {job['job_id'][:8]}...").classes("font-mono")
                            ui.label(f"Status: {status}").classes(f"text-{status_color}-600")
                            ui.label(f"Season: {job['spec']['season']}").classes("text-sm")
                            ui.label(f"Dataset: {job['spec']['dataset_id']}").classes("text-sm")
                            
                            # Show Open Report and Open Outputs Folder for DONE jobs
                            if job["status"] == "DONE":
                                with ui.row().classes("w-full mt-2"):
                                    if job.get("report_link"):
                                        def open_report(jid: str = job["job_id"]) -> None:
                                            """Open report link."""
                                            try:
                                                resp = requests.get(f"{API_BASE}/jobs/{jid}/report_link")
                                                resp.raise_for_status()
                                                data = resp.json()
                                                if data.get("ok") and data.get("report_link"):
                                                    b5_base = os.getenv("FISHBRO_B5_BASE_URL", "http://localhost:8502")
                                                    report_url = f"{b5_base}{data['report_link']}"
                                                    ui.open(report_url, new_tab=True)
                                                else:
                                                    ui.notify("Report not ready", type="warning")
                                            except Exception as e:
                                                ui.notify(f"Error: {e}", type="negative")
                                        
                                        ui.button("✅ Open Report", on_click=lambda: open_report()).classes("bg-blue-500 text-white")
                                    
                                    # Show outputs folder path
                                    if job.get("spec", {}).get("outputs_root"):
                                        outputs_path = job["spec"]["outputs_root"]
                                        ui.label(f"📁 {outputs_path}").classes("text-xs text-gray-600 ml-2")
                except Exception as e:
                    ui.label(f"Error: {e}").classes("text-red-600")
            
            ui.button("Refresh", on_click=refresh_job_list)
            refresh_job_list()
        
        # Right: Config Composer + Control
        with ui.column().classes("w-2/3"):
            ui.label("Config Composer").classes("text-xl font-bold")
            
            # Config inputs
            season_input = ui.input("Season", value="default").classes("w-full")
            dataset_input = ui.input("Dataset ID", value="default").classes("w-full")
            outputs_root_input = ui.input("Outputs Root", value="outputs").classes("w-full")
            
            subsample_slider = ui.slider(
                min=0.01, max=1.0, value=0.1, step=0.01
            ).classes("w-full")
            ui.label().bind_text_from(subsample_slider, "value", lambda v: f"Subsample: {v:.2f}")
            
            mem_limit_input = ui.number("Memory Limit (MB)", value=6000.0).classes("w-full")
            allow_auto_switch = ui.switch("Allow Auto-Downsample", value=True).classes("w-full")
            
            # CHECK Panel
            ui.label("CHECK Panel").classes("text-xl font-bold mt-4")
            check_result = ui.column().classes("w-full")
            
            def run_check() -> None:
                """Run preflight check."""
                check_result.clear()
                try:
                    # Create temp job for check
                    cfg = {
                        "season": season_input.value,
                        "dataset_id": dataset_input.value,
                        "outputs_root": outputs_root_input.value,
                        "bars": 1000,  # Default
                        "params_total": 100,  # Default
                        "param_subsample_rate": subsample_slider.value,
                        "mem_limit_mb": mem_limit_input.value,
                        "allow_auto_downsample": allow_auto_switch.value,
                    }
                    
                    # Create job and check
                    job_id = create_job_from_config(cfg)
                    result = get_preflight_result(job_id)
                    
                    # Display result
                    action = result["action"]
                    action_color = {
                        "PASS": "green",
                        "BLOCK": "red",
                        "AUTO_DOWNSAMPLE": "yellow",
                    }.get(action, "gray")
                    
                    ui.label(f"Action: {action}").classes(f"text-{action_color}-600 font-bold")
                    ui.label(f"Reason: {result['reason']}")
                    ui.label(f"Estimated MB: {result['estimated_mb']:.2f}")
                    ui.label(f"Memory Limit MB: {result['mem_limit_mb']:.2f}")
                    ui.label(f"Ops Est: {result['estimates']['ops_est']:,}")
                    ui.label(f"Time Est (s): {result['estimates']['time_est_s']:.2f}")
                except Exception as e:
                    ui.label(f"Error: {e}").classes("text-red-600")
            
            ui.button("CHECK", on_click=run_check).classes("mt-2")
            
            # Control Buttons
            ui.label("Control").classes("text-xl font-bold mt-4")
            
            current_job_id = ui.label("No job selected").classes("font-mono text-sm")
            
            def start_job() -> None:
                """Start current job."""
                try:
                    # Get latest job
                    jobs = list_jobs_api()
                    if jobs:
                        job_id = jobs[0]["job_id"]
                        resp = requests.post(f"{API_BASE}/jobs/{job_id}/start")
                        resp.raise_for_status()
                        ui.notify("Job started")
                    else:
                        ui.notify("No jobs available", type="warning")
                except Exception as e:
                    ui.notify(f"Error: {e}", type="negative")
            
            def pause_job() -> None:
                """Pause current job."""
                try:
                    jobs = list_jobs_api()
                    if jobs:
                        job_id = jobs[0]["job_id"]
                        resp = requests.post(
                            f"{API_BASE}/jobs/{job_id}/pause", json={"pause": True}
                        )
                        resp.raise_for_status()
                        ui.notify("Job paused")
                except Exception as e:
                    ui.notify(f"Error: {e}", type="negative")
            
            def stop_job_soft() -> None:
                """Stop job (soft)."""
                try:
                    jobs = list_jobs_api()
                    if jobs:
                        job_id = jobs[0]["job_id"]
                        resp = requests.post(
                            f"{API_BASE}/jobs/{job_id}/stop", json={"mode": "SOFT"}
                        )
                        resp.raise_for_status()
                        ui.notify("Job stopped (soft)")
                except Exception as e:
                    ui.notify(f"Error: {e}", type="negative")
            
            def stop_job_kill() -> None:
                """Stop job (kill)."""
                try:
                    jobs = list_jobs_api()
                    if jobs:
                        job_id = jobs[0]["job_id"]
                        resp = requests.post(
                            f"{API_BASE}/jobs/{job_id}/stop", json={"mode": "KILL"}
                        )
                        resp.raise_for_status()
                        ui.notify("Job killed")
                except Exception as e:
                    ui.notify(f"Error: {e}", type="negative")
            
            with ui.row().classes("w-full"):
                ui.button("START", on_click=start_job).classes("bg-green-500")
                ui.button("PAUSE", on_click=pause_job).classes("bg-yellow-500")
                ui.button("STOP (soft)", on_click=stop_job_soft).classes("bg-orange-500")
                ui.button("STOP (kill)", on_click=stop_job_kill).classes("bg-red-500")
            
            # Log Panel
            ui.label("Live Log").classes("text-xl font-bold mt-4")
            log_textarea = ui.textarea("").classes("w-full h-64 font-mono text-sm").props("readonly")
            
            def refresh_log() -> None:
                """Refresh log tail."""
                try:
                    jobs = list_jobs_api()
                    if jobs:
                        job_id = jobs[0]["job_id"]
                        resp = requests.get(f"{API_BASE}/jobs/{job_id}/log_tail?n=200")
                        resp.raise_for_status()
                        data = resp.json()
                        if data["ok"]:
                            log_textarea.value = "\n".join(data["lines"])
                        else:
                            log_textarea.value = f"Error: {data.get('error', 'Unknown error')}"
                    else:
                        log_textarea.value = "No jobs available"
                except Exception as e:
                    log_textarea.value = f"Error: {e}"
            
            ui.button("Refresh Log", on_click=refresh_log).classes("mt-2")
            


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(port=8080, title="B5-C Mission Control")

