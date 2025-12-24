"""
Candidates 頁面 - 顯示 canonical results 和 research index
根據 P0.5-1 要求：統一 UI 只讀 outputs/research/ 為官方彙整來源
"""

from nicegui import ui
from datetime import datetime
from typing import List, Dict, Any

from ..layout import render_shell
from ...services.candidates_reader import (
    load_canonical_results,
    load_research_index,
    CanonicalResult,
    ResearchIndexEntry,
    refresh_canonical_results,
    refresh_research_index,
)
from ...services.actions import generate_research
from FishBroWFS_V2.core.season_context import current_season, canonical_results_path, research_index_path
from FishBroWFS_V2.core.season_state import load_season_state


def render_canonical_results_table(results: List[CanonicalResult]) -> None:
    """渲染 canonical results 表格"""
    if not results:
        ui.label("No canonical results found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left"},
        {"name": "bars", "label": "Bars", "field": "bars", "align": "right"},
        {"name": "net_profit", "label": "Net Profit", "field": "net_profit", "align": "right", "format": lambda val: f"{val:.2f}"},
        {"name": "max_drawdown", "label": "Max DD", "field": "max_drawdown", "align": "right", "format": lambda val: f"{val:.2f}"},
        {"name": "score_final", "label": "Score Final", "field": "score_final", "align": "right", "format": lambda val: f"{val:.3f}"},
        {"name": "trades", "label": "Trades", "field": "trades", "align": "right"},
        {"name": "start_date", "label": "Start Date", "field": "start_date", "align": "left"},
    ]
    
    rows = []
    for result in results:
        rows.append({
            "run_id": result.run_id[:12] + "..." if len(result.run_id) > 12 else result.run_id,
            "strategy_id": result.strategy_id,
            "symbol": result.symbol,
            "bars": result.bars,
            "net_profit": result.net_profit,
            "max_drawdown": result.max_drawdown,
            "score_final": result.score_final,
            "trades": result.trades,
            "start_date": result.start_date[:10] if result.start_date else "",
        })
    
    # 使用 fish-card 樣式
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Canonical Results").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered")

def render_research_index_table(entries: List[ResearchIndexEntry]) -> None:
    """渲染 research index 表格"""
    if not entries:
        ui.label("No research index entries found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "season", "label": "Season", "field": "season", "align": "left"},
        {"name": "stage", "label": "Stage", "field": "stage", "align": "left"},
        {"name": "mode", "label": "Mode", "field": "mode", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "dataset_id", "label": "Dataset", "field": "dataset_id", "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "align": "left"},
        {"name": "created_at", "label": "Created At", "field": "created_at", "align": "left"},
    ]
    
    rows = []
    for entry in entries:
        rows.append({
            "run_id": entry.run_id[:12] + "..." if len(entry.run_id) > 12 else entry.run_id,
            "season": entry.season,
            "stage": entry.stage,
            "mode": entry.mode,
            "strategy_id": entry.strategy_id,
            "dataset_id": entry.dataset_id,
            "status": entry.status,
            "created_at": entry.created_at[:19] if entry.created_at else "",
        })
    
    # 使用 fish-card 樣式
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Research Index").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered")

def render_candidates_page() -> None:
    """渲染 candidates 頁面內容"""
    ui.page_title("FishBroWFS V2 - Candidates")
    
    # 使用 shell 佈局
    with render_shell("/candidates", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Candidates Dashboard").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                
                # 動作按鈕容器
                action_container = ui.row().classes("gap-2")
            
            # 檢查 research 檔案是否存在
            current_season_str = current_season()
            canonical_exists = canonical_results_path(current_season_str).exists()
            research_index_exists = research_index_path(current_season_str).exists()
            research_exists = canonical_exists and research_index_exists
            
            # 檢查 season freeze 狀態
            season_state = load_season_state(current_season_str)
            is_frozen = season_state.is_frozen()
            frozen_reason = season_state.reason if season_state.reason else "Season is frozen"
            
            # 說明文字
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("📊 Official Research Consolidation").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label(f"This page displays canonical results and research index from outputs/seasons/{current_season_str}/research/").classes("text-slate-300 mb-1")
                ui.label(f"Source: outputs/seasons/{current_season_str}/research/canonical_results.json & outputs/seasons/{current_season_str}/research/research_index.json").classes("text-sm text-slate-400")
                
                # 顯示檔案狀態
                if not research_exists:
                    with ui.row().classes("items-center mt-3 p-3 bg-amber-900/30 rounded-lg"):
                        ui.icon("warning", color="amber").classes("text-lg")
                        ui.label("Research artifacts not found for this season.").classes("ml-2 text-amber-300")
                
                # 顯示 freeze 狀態
                if is_frozen:
                    with ui.row().classes("items-center mt-3 p-3 bg-red-900/30 rounded-lg"):
                        ui.icon("lock", color="red").classes("text-lg")
                        ui.label(f"Season is frozen (reason: {frozen_reason})").classes("ml-2 text-red-300")
                        ui.label("All write actions are disabled.").classes("ml-2 text-red-300 text-sm")
            
            # 載入資料 - 使用當前 season
            canonical_results = load_canonical_results(current_season_str)
            research_index = load_research_index(current_season_str)
            
            # 統計卡片
            with ui.row().classes("w-full gap-4 mb-6"):
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Canonical Results").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(canonical_results))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("entries").classes("text-xs text-slate-500")
                    if not canonical_exists:
                        ui.label("File missing").classes("text-xs text-amber-500 mt-1")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Research Index").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(research_index))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("entries").classes("text-xs text-slate-500")
                    if not research_index_exists:
                        ui.label("File missing").classes("text-xs text-amber-500 mt-1")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Unique Strategies").classes("text-sm text-slate-400 mb-1")
                    strategies = {r.strategy_id for r in canonical_results}
                    ui.label(str(len(strategies))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("strategies").classes("text-xs text-slate-500")
            
            # 動作按鈕功能
            def generate_research_action():
                """觸發 Generate Research 動作"""
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Generating research...").classes("text-sm text-slate-400")
                
                # 執行 Generate Research 動作
                result = generate_research(current_season_str, legacy_copy=False)
                
                # 顯示結果
                if result.ok:
                    ui.notify(f"Research generated successfully! {len(result.artifacts_written)} artifacts created.", type="positive")
                else:
                    error_msg = result.stderr_tail[-1] if result.stderr_tail else "Unknown error"
                    ui.notify(f"Research generation failed: {error_msg}", type="negative")
                
                # 重新載入頁面
                ui.navigate.to("/candidates", reload=True)
            
            def refresh_all():
                """刷新所有資料"""
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Refreshing...").classes("text-sm text-slate-400")
                
                # 刷新資料 - 使用當前 season
                canonical_success = refresh_canonical_results(current_season_str)
                research_success = refresh_research_index(current_season_str)
                
                # 重新載入頁面
                ui.navigate.to("/candidates", reload=True)
            
            # 更新動作按鈕
            with action_container:
                if not research_exists:
                    if is_frozen:
                        # Season frozen: disable button with tooltip
                        ui.button("Generate Research", icon="play_arrow").props("outline disabled").tooltip(f"Season is frozen: {frozen_reason}")
                    else:
                        ui.button("Generate Research", icon="play_arrow", on_click=generate_research_action).props("outline color=positive")
                ui.button("Refresh Data", icon="refresh", on_click=refresh_all).props("outline")
            
            # 分隔線
            ui.separator().classes("my-6")
            
            # 如果沒有資料，顯示提示
            if not canonical_results and not research_index:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("insights", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No research data available").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label(f"Research artifacts not found for season {current_season_str}").classes("text-slate-400 mb-6")
                    if not research_exists:
                        ui.button("Generate Research Now", icon="play_arrow", on_click=generate_research_action).props("color=positive")
                return
            
            # Canonical Results 區塊
            ui.label("Canonical Results").classes("text-2xl font-bold mb-4 text-cyber-300")
            render_canonical_results_table(canonical_results)
            
            # Research Index 區塊
            ui.label("Research Index").classes("text-2xl font-bold mb-4 text-cyber-300")
            render_research_index_table(research_index)
            
            # 底部說明
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Canonical Results: Final performance metrics from research pipeline").classes("text-slate-300 mb-1")
                ui.label("• Research Index: Metadata about research runs (stage, mode, dataset, etc.)").classes("text-slate-300 mb-1")
                ui.label(f"• Data Source: outputs/seasons/{current_season_str}/research/ directory (single source of truth)").classes("text-slate-300 mb-1")
                ui.label("• Refresh: Click 'Refresh Data' to reload from disk").classes("text-slate-300")
                if not research_exists:
                    ui.label("• Generate: Click 'Generate Research' to create research artifacts for this season").classes("text-slate-300 text-amber-300")

def register() -> None:
    """註冊 candidates 頁面路由"""
    
    @ui.page("/candidates")
    def candidates_page() -> None:
        """Candidates 頁面"""
        render_candidates_page()