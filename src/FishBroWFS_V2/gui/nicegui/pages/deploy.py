"""Deploy List Page (Read-only) for M2.

Lists DONE jobs that are eligible for deployment (no actual deployment actions).
M4: Live-safety lock - shows banner when LIVE_EXECUTE is disabled.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Any

from nicegui import ui

from ..layout import render_shell
from FishBroWFS_V2.control.job_api import list_jobs_with_progress
from FishBroWFS_V2.core.season_context import current_season
from FishBroWFS_V2.core.season_state import load_season_state


def _check_live_execute_status() -> tuple[bool, str]:
    """檢查 LIVE_EXECUTE 是否啟用。
    
    Returns:
        tuple[bool, str]: (是否啟用, 原因訊息)
    """
    # 檢查環境變數
    if os.getenv("FISHBRO_ENABLE_LIVE") != "1":
        return False, "LIVE EXECUTION DISABLED (server-side). This UI is read-only."
    
    # 檢查 token 檔案
    token_path = Path("outputs/live_enable.token")
    if not token_path.exists():
        return False, "LIVE EXECUTION LOCKED: missing token outputs/live_enable.token"
    
    # 檢查 token 內容
    try:
        token_content = token_path.read_text(encoding="utf-8").strip()
        if token_content != "ALLOW_LIVE_EXECUTE":
            return False, "LIVE EXECUTION LOCKED: invalid token content in outputs/live_enable.token"
    except Exception:
        return False, "LIVE EXECUTION LOCKED: cannot read token file outputs/live_enable.token"
    
    return True, "LIVE EXECUTION ENABLED"


def render_deploy_list() -> None:
    """Render the deploy list page."""
    ui.page_title("FishBroWFS V2 - Deploy List")
    
    with render_shell("/deploy", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            ui.label("Deploy List (Read-only)").classes("text-3xl font-bold mb-6")
            
            # Season frozen banner
            season = current_season()
            season_state = load_season_state(season)
            is_frozen = season_state.is_frozen()
            if is_frozen:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-red-900/30 border-red-700"):
                    with ui.row().classes("items-center"):
                        ui.icon("lock", color="red").classes("text-2xl mr-3")
                        with ui.column():
                            ui.label("Season Frozen").classes("font-bold text-red-300 text-lg")
                            ui.label(f"This season is frozen. All deploy actions are disabled.").classes("text-red-200")
            
            # LIVE EXECUTE disabled banner
            live_enabled, live_reason = _check_live_execute_status()
            if not live_enabled:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-amber-900/30 border-amber-700"):
                    with ui.row().classes("items-center"):
                        ui.icon("warning", color="amber").classes("text-2xl mr-3")
                        with ui.column():
                            ui.label("Live Execution Disabled").classes("font-bold text-amber-300 text-lg")
                            ui.label(live_reason).classes("text-amber-200")
            
            # Explanation
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Lists DONE jobs that are eligible for deployment.").classes("text-slate-300 mb-1")
                ui.label("• This is a read‑only view; no deployment actions can be taken from this UI.").classes("text-slate-300 mb-1")
                ui.label("• Click a job to view its artifacts (if research index exists).").classes("text-slate-300")
                if is_frozen:
                    ui.label("• 🔒 Frozen season: All mutation buttons are disabled.").classes("text-red-300 mt-2")
                if not live_enabled:
                    ui.label("• 🚫 Live execution is disabled by server-side policy.").classes("text-amber-300 mt-2")
            
            # Fetch jobs and filter DONE
            jobs = list_jobs_with_progress(limit=100)
            done_jobs = [j for j in jobs if j.get("status", "").lower() == "done"]
            
            if not done_jobs:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("check_circle", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No DONE jobs found").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label("Jobs that have completed execution will appear here.").classes("text-slate-400")
                return
            
            # Table of DONE jobs
            columns = [
                {"name": "job_id", "label": "Job ID", "field": "job_id", "align": "left"},
                {"name": "season", "label": "Season", "field": "season", "align": "left"},
                {"name": "units_total", "label": "Units", "field": "units_total", "align": "right"},
                {"name": "created_at", "label": "Created", "field": "created_at", "align": "left"},
                {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
                {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
            ]
            
            rows = []
            for job in done_jobs:
                rows.append({
                    "job_id": job["job_id"],
                    "season": job.get("season", "N/A"),
                    "units_total": job.get("units_total", 0),
                    "created_at": job.get("created_at", "")[:19],
                    "updated_at": job.get("updated_at", "")[:19],
                })
            
            # Render each job as a card
            for row in rows:
                with ui.card().classes("w-full fish-card p-4 mb-4"):
                    with ui.grid(columns=6).classes("w-full items-center gap-4"):
                        ui.label(row["job_id"][:12] + "...").classes("font-mono text-sm")
                        ui.label(row["season"])
                        ui.label(str(row["units_total"])).classes("text-right")
                        ui.label(row["created_at"]).classes("text-sm text-gray-500")
                        ui.label(row["updated_at"]).classes("text-sm text-gray-500")
                        with ui.row().classes("gap-2"):
                            ui.button("Artifacts", icon="link",
                                     on_click=lambda r=row: ui.navigate.to(f"/artifacts/{r['job_id']}")).props("outline size=sm")
                            ui.button("Deploy", icon="rocket",
                                     on_click=lambda: ui.notify("Deploy actions are read-only", type="info")).props("outline disabled" if is_frozen else "outline").tooltip("Deployment is disabled in read-only mode")
            
            # Footer note
            with ui.card().classes("w-full fish-card p-4 mt-6"):
                ui.label("📌 Notes").classes("font-bold mb-2")
                ui.label("• Deploy list is automatically generated from DONE jobs.").classes("text-sm text-slate-400")
                ui.label("• To actually deploy a job, use the command-line interface or a separate deployment tool.").classes("text-sm text-slate-400")
                ui.label("• Frozen seasons prevent any deployment writes.").classes("text-sm text-slate-400")


def register() -> None:
    """Register deploy page."""
    
    @ui.page("/deploy")
    def deploy_page() -> None:
        render_deploy_list()
