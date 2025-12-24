"""
Portfolio 頁面 - 顯示 portfolio summary 和 manifest，提供 Build Portfolio 按鈕。

Phase 4: UI wiring for portfolio builder.
Phase 5: Respect season freeze state.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from nicegui import ui

from ..layout import render_shell
from ...services.actions import build_portfolio_from_research
from FishBroWFS_V2.core.season_context import (
    current_season,
    portfolio_dir,
    portfolio_summary_path,
    portfolio_manifest_path,
)

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


def load_portfolio_summary(season: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """載入 portfolio_summary.json"""
    summary_path = portfolio_summary_path(season)
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_portfolio_manifest(season: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """載入 portfolio_manifest.json"""
    manifest_path = portfolio_manifest_path(season)
    if not manifest_path.exists():
        return None
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "entries" in data:
                return data["entries"]
            else:
                return []
    except (json.JSONDecodeError, OSError):
        return None


def list_portfolio_runs(season: Optional[str] = None) -> List[Path]:
    """列出 portfolio 目錄中的 run 子目錄"""
    pdir = portfolio_dir(season)
    if not pdir.exists():
        return []
    
    runs = []
    for item in pdir.iterdir():
        if item.is_dir() and len(item.name) == 12:  # portfolio_id pattern (12 chars)
            runs.append(item)
    
    return sorted(runs, key=lambda x: x.name, reverse=True)


def render_portfolio_summary_card(summary: Dict[str, Any]) -> None:
    """渲染 portfolio summary 卡片"""
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Summary").classes("text-xl font-bold mb-4 text-cyber-400")
        
        # 基本資訊
        with ui.grid(columns=2).classes("w-full gap-4"):
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Portfolio ID").classes("text-sm text-slate-400 mb-1")
                ui.label(summary.get("portfolio_id", "N/A")).classes("text-lg font-mono text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Created At").classes("text-sm text-slate-400 mb-1")
                ui.label(summary.get("created_at", "N/A")[:19]).classes("text-lg text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Total Decisions").classes("text-sm text-slate-400 mb-1")
                ui.label(str(summary.get("total_decisions", 0))).classes("text-2xl font-bold text-cyber-400")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("KEEP Decisions").classes("text-sm text-slate-400 mb-1")
                ui.label(str(summary.get("keep_decisions", 0))).classes("text-2xl font-bold text-cyber-400")
        
        # 額外資訊
        if "symbols" in summary:
            with ui.card().classes("p-3 bg-nexus-800 mt-4"):
                ui.label("Symbols").classes("text-sm text-slate-400 mb-1")
                symbols = summary["symbols"]
                if isinstance(symbols, list):
                    ui.label(", ".join(symbols)).classes("text-sm text-slate-300")
                else:
                    ui.label(str(symbols)).classes("text-sm text-slate-300")


def render_portfolio_manifest_table(manifest: List[Dict[str, Any]]) -> None:
    """渲染 portfolio manifest 表格"""
    if not manifest:
        ui.label("No manifest entries found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left"},
        {"name": "decision", "label": "Decision", "field": "decision", "align": "left"},
        {"name": "score_final", "label": "Score", "field": "score_final", "align": "right", "format": lambda val: f"{val:.3f}"},
        {"name": "net_profit", "label": "Net Profit", "field": "net_profit", "align": "right", "format": lambda val: f"{val:.2f}"},
    ]
    
    rows = []
    for entry in manifest:
        rows.append({
            "run_id": entry.get("run_id", "")[:12] + "..." if len(entry.get("run_id", "")) > 12 else entry.get("run_id", ""),
            "strategy_id": entry.get("strategy_id", ""),
            "symbol": entry.get("symbol", ""),
            "decision": entry.get("decision", ""),
            "score_final": entry.get("score_final", 0.0),
            "net_profit": entry.get("net_profit", 0.0),
        })
    
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Manifest").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered pagination rows-per-page=10")


def render_portfolio_runs_list(runs: List[Path]) -> None:
    """渲染 portfolio runs 列表"""
    if not runs:
        return
    
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Runs").classes("text-xl font-bold mb-4 text-cyber-400")
        
        for run_dir in runs[:10]:  # 顯示最多 10 個
            run_id = run_dir.name
            with ui.card().classes("p-3 mb-2 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center"):
                        ui.icon("folder", color="cyan").classes("mr-2")
                        ui.label(run_id).classes("font-mono text-cyber-300")
                    
                    # 檢查檔案
                    spec_file = run_dir / "portfolio_spec.json"
                    manifest_file = run_dir / "portfolio_manifest.json"
                    
                    with ui.row().classes("gap-2"):
                        if spec_file.exists():
                            ui.badge("spec", color="green").props("dense")
                        if manifest_file.exists():
                            ui.badge("manifest", color="blue").props("dense")


def render_portfolio_page() -> None:
    """渲染 portfolio 頁面內容"""
    ui.page_title("FishBroWFS V2 - Portfolio")
    
    # 使用 shell 佈局
    with render_shell("/portfolio", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Portfolio Builder").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                
                # 動作按鈕容器
                action_container = ui.row().classes("gap-2")
            
            # 檢查 season freeze 狀態
            is_frozen = False
            frozen_reason = ""
            if SEASON_STATE_AVAILABLE and load_season_state is not None:
                try:
                    state = load_season_state(current_season())
                    if state and state.get("state") == "FROZEN":
                        is_frozen = True
                        frozen_reason = state.get("reason", "Season is frozen")
                except Exception:
                    # 如果載入失敗，忽略錯誤（保持未凍結狀態）
                    pass
            
            # 顯示 freeze 警告（如果 season 被凍結）
            if is_frozen:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-red-900/30 border-l-4 border-red-500"):
                    with ui.row().classes("items-center"):
                        ui.icon("lock", color="red").classes("text-xl mr-3")
                        with ui.column().classes("flex-1"):
                            ui.label("Season Frozen (治理鎖)").classes("font-bold text-lg text-red-300")
                            ui.label(frozen_reason).classes("text-red-200")
                            ui.label("Portfolio building is disabled while season is frozen.").classes("text-sm text-red-300/80")
            
            # 檢查 portfolio 檔案是否存在
            current_season_str = current_season()
            summary_exists = portfolio_summary_path(current_season_str).exists()
            manifest_exists = portfolio_manifest_path(current_season_str).exists()
            portfolio_exists = summary_exists or manifest_exists
            
            # 說明文字
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("🏦 Portfolio Builder").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label(f"This page displays portfolio artifacts from outputs/seasons/{current_season_str}/portfolio/").classes("text-slate-300 mb-1")
                ui.label(f"Source: outputs/seasons/{current_season_str}/portfolio/portfolio_summary.json & portfolio_manifest.json").classes("text-sm text-slate-400")
                
                # 顯示檔案狀態
                if not portfolio_exists:
                    with ui.row().classes("items-center mt-3 p-3 bg-amber-900/30 rounded-lg"):
                        ui.icon("warning", color="amber").classes("text-lg")
                        ui.label("Portfolio artifacts not found for this season.").classes("ml-2 text-amber-300")
                        ui.label("Build portfolio from research results using the button above.").classes("ml-2 text-amber-300 text-sm")
            
            # 載入資料
            portfolio_summary = load_portfolio_summary(current_season_str)
            portfolio_manifest = load_portfolio_manifest(current_season_str)
            portfolio_runs = list_portfolio_runs(current_season_str)
            
            # 統計卡片
            with ui.row().classes("w-full gap-4 mb-6"):
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Summary").classes("text-sm text-slate-400 mb-1")
                    if portfolio_summary:
                        ui.label("Available").classes("text-2xl font-bold text-cyber-400")
                        ui.label("✓ Loaded").classes("text-xs text-green-500")
                    else:
                        ui.label("Missing").classes("text-2xl font-bold text-amber-400")
                        if not summary_exists:
                            ui.label("File not found").classes("text-xs text-amber-500")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Manifest").classes("text-sm text-slate-400 mb-1")
                    if portfolio_manifest:
                        ui.label(f"{len(portfolio_manifest)}").classes("text-2xl font-bold text-cyber-400")
                        ui.label("entries").classes("text-xs text-slate-500")
                    else:
                        ui.label("Missing").classes("text-2xl font-bold text-amber-400")
                        if not manifest_exists:
                            ui.label("File not found").classes("text-xs text-amber-500")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Runs").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(portfolio_runs))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("runs").classes("text-xs text-slate-500")
            
            # 動作按鈕功能
            def build_portfolio_action():
                """觸發 Build Portfolio 動作"""
                # 檢查 season 是否被凍結（額外防護）
                if is_frozen:
                    ui.notify("Cannot build portfolio: season is frozen", type="negative")
                    return
                
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Building portfolio...").classes("text-sm text-slate-400")
                
                # 執行 Build Portfolio 動作
                result = build_portfolio_from_research(current_season_str)
                
                # 顯示結果
                if result.ok:
                    artifacts_count = len(result.artifacts_written)
                    ui.notify(f"Portfolio built successfully! {artifacts_count} artifacts created.", type="positive")
                else:
                    error_msg = result.stderr_tail[-1] if result.stderr_tail else "Unknown error"
                    ui.notify(f"Portfolio build failed: {error_msg}", type="negative")
                
                # 重新載入頁面
                ui.navigate.to("/portfolio", reload=True)
            
            # 更新動作按鈕
            with action_container:
                if not portfolio_exists:
                    if is_frozen:
                        # Season frozen: disable button with tooltip
                        ui.button("Build Portfolio", icon="build").props("outline disabled").tooltip(f"Season is frozen: {frozen_reason}")
                    else:
                        ui.button("Build Portfolio", icon="build", on_click=build_portfolio_action).props("outline color=positive")
                ui.button("Refresh", icon="refresh", on_click=lambda: ui.navigate.to("/portfolio", reload=True)).props("outline")
            
            # 分隔線
            ui.separator().classes("my-6")
            
            # 如果沒有資料，顯示提示
            if not portfolio_summary and not portfolio_manifest and not portfolio_runs:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("account_balance", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No portfolio data available").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label(f"Portfolio artifacts not found for season {current_season_str}").classes("text-slate-400 mb-4")
                    ui.label("Build portfolio from research results to create portfolio artifacts.").classes("text-slate-400 mb-6")
                    if not portfolio_exists:
                        ui.button("Build Portfolio Now", icon="build", on_click=build_portfolio_action).props("color=positive")
                return
            
            # Portfolio Summary 區塊
            if portfolio_summary:
                ui.label("Portfolio Summary").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_summary_card(portfolio_summary)
            
            # Portfolio Manifest 區塊
            if portfolio_manifest:
                ui.label("Portfolio Manifest").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_manifest_table(portfolio_manifest)
            
            # Portfolio Runs 區塊
            if portfolio_runs:
                ui.label("Portfolio Runs").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_runs_list(portfolio_runs)
            
            # 底部說明
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Portfolio Summary: High-level overview of portfolio decisions and metrics").classes("text-slate-300 mb-1")
                ui.label("• Portfolio Manifest: Detailed list of candidate runs with keep/drop decisions").classes("text-slate-300 mb-1")
                ui.label("• Portfolio Runs: Individual portfolio run directories with spec and manifest files").classes("text-slate-300 mb-1")
                ui.label(f"• Data Source: outputs/seasons/{current_season_str}/portfolio/ directory").classes("text-slate-300 mb-1")
                if not portfolio_exists:
                    ui.label("• Build: Click 'Build Portfolio' to create portfolio from research results").classes("text-slate-300 text-amber-300")


def register() -> None:
    """註冊 portfolio 頁面路由"""
    
    @ui.page("/portfolio")
    def portfolio_page() -> None:
        """Portfolio 頁面"""
        render_portfolio_page()