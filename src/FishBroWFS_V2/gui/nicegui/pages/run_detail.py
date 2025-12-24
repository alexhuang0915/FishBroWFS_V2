"""
Run Detail 頁面 - 顯示單一 run 的詳細資訊、artifacts 和 audit trail。

Phase 4: Enhanced governance and observability.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from nicegui import ui

from ..layout import render_shell
from ...services.runs_index import get_global_index, RunIndexRow
from ...services.audit_log import get_audit_events_for_run_id
from FishBroWFS_V2.core.season_context import current_season


def load_run_manifest(run_dir: Path) -> Optional[Dict[str, Any]]:
    """載入 run 的 manifest.json"""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_run_summary(run_dir: Path) -> Optional[Dict[str, Any]]:
    """載入 run 的 summary.json"""
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_run_artifacts(run_dir: Path) -> List[Path]:
    """列出 run 目錄中的所有檔案"""
    if not run_dir.exists():
        return []
    artifacts = []
    for item in run_dir.rglob("*"):
        if item.is_file():
            artifacts.append(item)
    return sorted(artifacts, key=lambda x: x.name)


def render_run_info_card(run: RunIndexRow, manifest: Optional[Dict[str, Any]]) -> None:
    """渲染 run 基本資訊卡片"""
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Information").classes("text-xl font-bold mb-4 text-cyber-400")
        
        with ui.grid(columns=2).classes("w-full gap-4"):
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Run ID").classes("text-sm text-slate-400 mb-1")
                ui.label(run.run_id).classes("text-lg font-mono text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Season").classes("text-sm text-slate-400 mb-1")
                ui.label(run.season).classes("text-lg text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Stage").classes("text-sm text-slate-400 mb-1")
                stage_badge = run.stage or "unknown"
                color = {
                    "stage0": "bg-blue-500/20 text-blue-300",
                    "stage1": "bg-green-500/20 text-green-300",
                    "stage2": "bg-purple-500/20 text-purple-300",
                    "demo": "bg-yellow-500/20 text-yellow-300",
                }.get(stage_badge, "bg-slate-500/20 text-slate-300")
                ui.label(stage_badge).classes(f"px-3 py-1 rounded-full text-sm {color}")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Status").classes("text-sm text-slate-400 mb-1")
                status_badge = run.status
                status_color = {
                    "completed": "bg-green-500/20 text-green-300",
                    "running": "bg-blue-500/20 text-blue-300",
                    "failed": "bg-red-500/20 text-red-300",
                    "unknown": "bg-slate-500/20 text-slate-300",
                }.get(status_badge, "bg-slate-500/20 text-slate-300")
                ui.label(status_badge).classes(f"px-3 py-1 rounded-full text-sm {status_color}")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Created").classes("text-sm text-slate-400 mb-1")
                created_time = datetime.fromtimestamp(run.mtime).strftime("%Y-%m-%d %H:%M:%S")
                ui.label(created_time).classes("text-sm text-slate-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Directory").classes("text-sm text-slate-400 mb-1")
                ui.label(str(run.run_dir)).classes("text-xs font-mono text-slate-400 truncate")
        
        if manifest:
            with ui.card().classes("p-3 bg-nexus-800 mt-4"):
                ui.label("Manifest Info").classes("text-sm text-slate-400 mb-2")
                if "strategy_id" in manifest:
                    with ui.row().classes("items-center mb-1"):
                        ui.label("Strategy:").classes("text-sm text-slate-400 w-24")
                        ui.label(manifest["strategy_id"]).classes("text-sm text-cyber-300")
                if "symbol" in manifest:
                    with ui.row().classes("items-center mb-1"):
                        ui.label("Symbol:").classes("text-sm text-slate-400 w-24")
                        ui.label(manifest["symbol"]).classes("text-sm text-cyber-300")


def render_run_summary_card(summary: Dict[str, Any]) -> None:
    """渲染 run summary 卡片"""
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Summary").classes("text-xl font-bold mb-4 text-cyber-400")
        
        metrics = summary.get("metrics", {})
        if metrics:
            with ui.grid(columns=3).classes("w-full gap-4"):
                net_profit = metrics.get("net_profit", 0.0)
                profit_color = "text-green-400" if net_profit >= 0 else "text-red-400"
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Net Profit").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"${net_profit:.2f}").classes(f"text-2xl font-bold {profit_color}")
                
                win_rate = metrics.get("win_rate", 0.0)
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Win Rate").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"{win_rate:.1%}").classes("text-2xl font-bold text-cyber-400")
                
                sharpe = metrics.get("sharpe_ratio", 0.0)
                sharpe_color = "text-green-400" if sharpe >= 1.0 else "text-yellow-400" if sharpe >= 0 else "text-red-400"
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Sharpe Ratio").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"{sharpe:.2f}").classes(f"text-2xl font-bold {sharpe_color}")


def render_run_artifacts_list(artifacts: List[Path], run_dir: Path) -> None:
    """渲染 run artifacts 列表"""
    if not artifacts:
        ui.label("No artifacts found").classes("text-gray-500 italic")
        return
    
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Artifacts").classes("text-xl font-bold mb-4 text-cyber-400")
        
        json_files = [a for a in artifacts if a.suffix == ".json"]
        csv_files = [a for a in artifacts if a.suffix == ".csv"]
        other_files = [a for a in artifacts if a.suffix not in [".json", ".csv"]]
        
        if json_files:
            ui.label("JSON Files").classes("text-lg font-bold mb-2 text-cyber-300")
            for artifact in json_files[:5]:
                rel_path = artifact.relative_to(run_dir)
                size = artifact.stat().st_size if artifact.exists() else 0
                with ui.card().classes("p-2 mb-1 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                    with ui.row().classes("items-center justify-between"):
                        with ui.row().classes("items-center"):
                            ui.icon("description", color="green").classes("mr-2")
                            ui.label(str(rel_path)).classes("text-sm font-mono text-slate-300")
                        ui.label(f"{size:,} bytes").classes("text-xs text-slate-500")
        
        if csv_files:
            ui.label("CSV Files").classes("text-lg font-bold mb-2 text-cyber-300 mt-4")
            for artifact in csv_files[:3]:
                rel_path = artifact.relative_to(run_dir)
                size = artifact.stat().st_size if artifact.exists() else 0
                with ui.card().classes("p-2 mb-1 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                    with ui.row().classes("items-center justify-between"):
                        with ui.row().classes("items-center"):
                            ui.icon("table_chart", color="blue").classes("mr-2")
                            ui.label(str(rel_path)).classes("text-sm font-mono text-slate-300")
                        ui.label(f"{size:,} bytes").classes("text-xs text-slate-500")


def render_audit_trail_card(run_id: str, season: str) -> None:
    """渲染 run 的 audit trail 卡片"""
    audit_events = get_audit_events_for_run_id(run_id, season, max_lines=30)
    
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Audit Trail").classes("text-xl font-bold mb-4 text-cyber-400")
        
        if not audit_events:
            ui.label("No audit events found for this run").classes("text-gray-500 italic p-4")
            ui.label("UI actions will create audit events automatically").classes("text-sm text-slate-400")
            return
        
        for event in reversed(audit_events):
            with ui.card().classes("p-3 mb-3 bg-nexus-800"):
                with ui.row().classes("items-center justify-between mb-2"):
                    action_type = event.get("action", "unknown")
                    action_color = {
                        "generate_research": "text-green-400",
                        "build_portfolio": "text-blue-400",
                        "archive": "text-red-400",
                        "clone": "text-yellow-400",
                    }.get(action_type, "text-slate-400")
                    ui.label(f"Action: {action_type}").classes(f"font-bold {action_color}")
                    
                    ts = event.get("ts", "")
                    if ts:
                        display_ts = ts[:19].replace("T", " ")
                        ui.label(display_ts).classes("text-sm text-slate-400")
                
                with ui.column().classes("text-sm"):
                    status = "✓ Success" if event.get("ok", False) else "✗ Failed"
                    status_color = "text-green-400" if event.get("ok", False) else "text-red-400"
                    ui.label(f"Status: {status}").classes(f"mb-1 {status_color}")
                    
                    if "inputs" in event:
                        inputs = event["inputs"]
                        if isinstance(inputs, dict) and inputs:
                            ui.label("Inputs:").classes("text-slate-400 mb-1")
                            for key, value in inputs.items():
                                ui.label(f"  {key}: {value}").classes("text-xs text-slate-500 ml-2")


def render_run_detail_page(run_id: str) -> None:
    """渲染 run detail 頁面內容"""
    ui.page_title(f"FishBroWFS V2 - Run {run_id}")
    
    with render_shell("/history", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            with ui.row().classes("w-full items-center mb-6"):
                with ui.row().classes("items-center"):
                    ui.link("← Back to History", "/history").classes("text-cyber-400 hover:text-cyber-300 mr-4")
                    ui.label(f"Run Detail: {run_id}").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                ui.button("Refresh", icon="refresh", on_click=lambda: ui.navigate.to(f"/run/{run_id}", reload=True)).props("outline")
            
            index = get_global_index()
            index.refresh()
            run = index.get(run_id)
            
            if not run:
                with ui.card().classes("fish-card w-full p-8 text-center"):
                    ui.icon("error", size="xl").classes("text-red-500 mb-4")
                    ui.label(f"Run {run_id} not found").classes("text-2xl font-bold text-red-400 mb-2")
                    ui.label("The run may have been archived or deleted.").classes("text-slate-400 mb-4")
                    ui.link("Go back to History", "/history").classes("text-cyber-400 hover:text-cyber-300")
                return
            
            run_dir = Path(run.run_dir)
            if not run_dir.exists():
                with ui.card().classes("fish-card w-full p-8 text-center"):
                    ui.icon("folder_off", size="xl").classes("text-amber-500 mb-4")
                    ui.label(f"Run directory not found").classes("text-2xl font-bold text-amber-400 mb-2")
                    ui.label(f"Path: {run_dir}").classes("text-sm text-slate-400 mb-4")
                    ui.label("The run may have been moved or deleted.").classes("text-slate-400")
                return
            
            with ui.card().classes("fish-card p-4 mb-6 bg-nexus-900"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center gap-4"):
                        status_badge = run.status
                        status_color = {
                            "completed": "bg-green-500/20 text-green-300",
                            "running": "bg-blue-500/20 text-blue-300",
                            "failed": "bg-red-500/20 text-red-300",
                            "unknown": "bg-slate-500/20 text-slate-300",
                        }.get(status_badge, "bg-slate-500/20 text-slate-300")
                        ui.label(status_badge).classes(f"px-3 py-1 rounded-full text-sm {status_color}")
                        
                        if run.is_archived:
                            ui.badge("Archived", color="red").props("dense")
                    
                    with ui.row().classes("gap-2"):
                        ui.button("View in Files", icon="folder_open").props("outline")
                        ui.button("Clone Run", icon="content_copy").props("outline color=positive")
                        if not run.is_archived:
                            ui.button("Archive", icon="archive").props("outline color=negative")
            
            manifest = load_run_manifest(run_dir)
            summary = load_run_summary(run_dir)
            artifacts = list_run_artifacts(run_dir)
            
            render_run_info_card(run, manifest)
            
            if summary:
                render_run_summary_card(summary)
            
            render_run_artifacts_list(artifacts, run_dir)
            
            render_audit_trail_card(run_id, run.season)
            
            with ui.card().classes("fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Run Information: Basic metadata about the run").classes("text-slate-300 mb-1")
                ui.label("• Run Summary: Performance metrics and summary").classes("text-slate-300 mb-1")
                ui.label("• Run Artifacts: Files generated by the run").classes("text-slate-300 mb-1")
                ui.label("• Audit Trail: UI actions related to this run").classes("text-slate-300 mb-1")
                ui.label("• All UI actions are logged for governance and auditability").classes("text-slate-300 text-amber-300")


def register() -> None:
    """註冊 run detail 頁面路由"""
    
    @ui.page("/run/{run_id}")
    def run_detail_page(run_id: str) -> None:
        """Run Detail 頁面"""
        render_run_detail_page(run_id)