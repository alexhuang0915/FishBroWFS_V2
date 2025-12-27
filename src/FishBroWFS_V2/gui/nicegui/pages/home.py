"""
首頁 - Dashboard/Home (UI‑1/2 Determinism‑Safe Dark Ops Dashboard)

UI‑1/2 合約：無自動輪詢、無 websocket、無客戶端衍生 ETA、無頁面載入自動刷新。
所有資料透過 DashboardBridge 取得快照，手動刷新按鈕觸發。
"""

from nicegui import ui

from ..state import app_state
from ..layout import render_build_fingerprint, NAV
from ..bridge.dashboard_bridge import get_dashboard_bridge
from ...contracts.dashboard_dto import (
    DashboardSnapshotDTO,
    PortfolioStatusDTO,
    DeployStatusDTO,
    ActiveOpDTO,
    CandidateDTO,
    OperationSummaryDTO,
    PortfolioDeployStateDTO,
    BuildInfoDTO,
)


def register() -> None:
    """註冊首頁路由"""
    
    @ui.page("/")
    def home_page() -> None:
        """渲染首頁 (UI‑1/2 Dark Ops)"""
        ui.page_title("FishBroWFS V2 - 儀表板")
        
        # Build fingerprint banner (UI truth)
        render_build_fingerprint()
        
        # 建立全域狀態容器（將由 refresh_dashboard 填充）
        snapshot_container = ui.column().classes("w-full max-w-7xl mx-auto p-6")
        
        # 刷新按鈕（手動刷新，無自動輪詢）
        with ui.row().classes("w-full max-w-7xl mx-auto px-6 pt-6 justify-end"):
            refresh_button = ui.button("🔄 刷新儀表板", on_click=lambda: refresh_dashboard(snapshot_container))
            refresh_button.props("icon=refresh outline")
            refresh_button.classes("bg-cyber-900 hover:bg-cyber-800 text-cyber-300")
        
        # 初始載入（空狀態）－ UI‑1/2 合約禁止頁面載入自動刷新
        with snapshot_container:
            ui.label("儀表板就緒").classes("text-xl font-bold text-cyber-400 mb-2")
            ui.label("點擊「刷新儀表板」按鈕以載入最新狀態").classes("text-slate-500")
            ui.label("UI‑1/2 合約：無自動輪詢、無頁面載入自動刷新").classes("text-sm text-slate-600 mt-4")
    
    # 刷新儀表板（核心邏輯）
    def refresh_dashboard(container: ui.column) -> None:
        """從 DashboardBridge 取得快照並重新渲染所有 UI 區塊"""
        container.clear()
        
        try:
            bridge = get_dashboard_bridge()
            snapshot = bridge.get_snapshot()
        except Exception as e:
            with container:
                ui.label(f"無法載入儀表板快照：{e}").classes("text-red-400")
                ui.label("請檢查 Control API 是否運行中。").classes("text-slate-500")
            return
        
        # 渲染儀表板網格
        with container:
            # 1. 頂部狀態列（全域狀態）
            render_topbar_status(snapshot)
            
            # 2. 主要操作按鈕
            render_primary_cta()
            
            # 3. 活動操作 / 進度
            render_active_ops(snapshot)
            
            # 4. 最新候選人（含 intelligence）
            render_latest_candidates(snapshot.top_candidates)
            
            # 5. 操作摘要
            render_operation_summary(snapshot.operation_summary)
            
            # 6. 系統日誌
            render_system_logs(snapshot.log_lines)
            
            # 7. 導航標籤（快速連結）
            render_navigation_tabs()
            
            # 8. 憲法級原則提醒（保留原有）
            render_constitution_reminder()
    
    # 渲染函數
    def render_topbar_status(snapshot: DashboardSnapshotDTO) -> None:
        """頂部狀態列（季節、系統狀態、運行計數、投資組合狀態、部署狀態）"""
        ui.label("全域狀態").classes("text-2xl font-bold mb-4 text-cyber-400")
        
        with ui.row().classes("w-full gap-4 mb-8"):
            # 季節
            with ui.card().classes("fish-card flex-1 p-4 border-cyber-500/30"):
                ui.label("季節").classes("font-bold text-slate-300")
                ui.label(snapshot.season_id).classes("text-2xl font-bold text-cyber-glow")
                ui.label("當前研究季度").classes("text-sm text-slate-500")
            
            # 系統線上狀態
            with ui.card().classes(f"fish-card flex-1 p-4 border-{'green' if snapshot.system_online else 'red'}-500/30"):
                ui.label("系統狀態").classes("font-bold text-slate-300")
                status_text = "✅ 線上" if snapshot.system_online else "❌ 離線"
                ui.label(status_text).classes("text-xl font-bold text-green-400" if snapshot.system_online else "text-red-400")
                ui.label("Control API 可達性").classes("text-sm text-slate-500")
            
            # 總運行數
            with ui.card().classes("fish-card flex-1 p-4 border-blue-500/30"):
                ui.label("總運行數").classes("font-bold text-slate-300")
                ui.label(str(snapshot.runs_count)).classes("text-2xl font-bold text-blue-400")
                ui.label("本季節任務總數").classes("text-sm text-slate-500")
            
            # 有效 Worker
            with ui.card().classes("fish-card flex-1 p-4 border-purple-500/30"):
                ui.label("有效 Worker").classes("font-bold text-slate-300")
                ui.label(str(snapshot.worker_effective)).classes("text-2xl font-bold text-purple-400")
                ui.label("活動中 Worker 數量").classes("text-sm text-slate-500")
            
            # 操作狀態
            with ui.card().classes("fish-card flex-1 p-4 border-amber-500/30"):
                ui.label("操作狀態").classes("font-bold text-slate-300")
                ui.label(snapshot.ops_status).classes("text-xl font-bold text-amber-300")
                if snapshot.ops_progress_pct is not None:
                    ui.label(f"進度 {snapshot.ops_progress_pct}%").classes("text-sm text-slate-500")
                else:
                    ui.label("無進度資料").classes("text-sm text-slate-500")
    
    def render_primary_cta() -> None:
        """主要操作按鈕"""
        ui.label("主要操作").classes("text-2xl font-bold mb-4 text-cyber-400")
        
        with ui.row().classes("w-full gap-4 mb-8"):
            with ui.card().classes("fish-card flex-1 p-6 cursor-pointer glow border-cyber-500/50"):
                ui.icon("rocket_launch", size="xl").classes("text-cyber-500 mb-4")
                ui.label("新增研究任務").classes("text-xl font-bold text-white mb-2")
                ui.label("設定 dataset/symbols/TF/strategy 等參數").classes("text-slate-400 mb-4")
                ui.button("前往 Wizard", on_click=lambda e: ui.navigate.to("/wizard")).props("outline").classes("w-full")
            
            with ui.card().classes("fish-card flex-1 p-6 cursor-pointer border-green-500/50"):
                ui.icon("portfolio", size="xl").classes("text-green-500 mb-4")
                ui.label("前往投資組合").classes("text-xl font-bold text-white mb-2")
                ui.label("檢視候選人、權重、部署狀態").classes("text-slate-400 mb-4")
                ui.button("前往 Portfolio", on_click=lambda e: ui.navigate.to("/portfolio")).props("outline").classes("w-full")
    
    def render_active_ops(snapshot: DashboardSnapshotDTO) -> None:
        """活動操作 / 進度"""
        ui.label("活動操作").classes("text-2xl font-bold mb-4 text-cyber-400")
        
        with ui.card().classes("fish-card w-full p-6 border-blue-500/30"):
            if snapshot.worker_effective > 0:
                ui.label(f"目前有 {snapshot.worker_effective} 個活動 Worker").classes("font-bold mb-4")
                ui.label(f"操作狀態：{snapshot.ops_status}").classes("text-slate-300 mb-2")
                if snapshot.ops_progress_pct is not None:
                    ui.linear_progress(snapshot.ops_progress_pct / 100).classes("w-full mb-4")
                    ui.label(f"整體進度 {snapshot.ops_progress_pct}%").classes("text-sm text-slate-400")
                if snapshot.ops_eta_seconds is not None:
                    eta_min = snapshot.ops_eta_seconds // 60
                    ui.label(f"預計剩餘時間：{eta_min} 分鐘").classes("text-sm text-amber-400")
            else:
                ui.label("目前沒有活動任務").classes("text-slate-500")
                ui.label("所有任務已完成或尚未開始").classes("text-sm text-slate-600")
    
    def render_latest_candidates(candidates: tuple[CandidateDTO, ...]) -> None:
        """最新候選人（含 intelligence）"""
        ui.label("最新候選人（含 Intelligence）").classes("text-2xl font-bold mb-4 text-cyber-400")
        
        if not candidates:
            with ui.card().classes("fish-card w-full p-6 border-purple-500/30"):
                ui.label("暫無候選人").classes("text-slate-500")
                ui.label("請執行研究任務以產生候選人").classes("text-sm text-slate-600")
            return
        
        # 候選人網格（每行最多 2 個）
        with ui.row().classes("w-full gap-6 flex-wrap"):
            for cand in candidates:
                with ui.card().classes("fish-card flex-1 min-w-[400px] p-6 border-purple-500/30"):
                    # 標題列
                    with ui.row().classes("w-full items-center mb-4"):
                        ui.label(f"#{cand.rank}").classes("text-2xl font-bold text-cyber-glow mr-4")
                        ui.label(cand.candidate_id).classes("font-mono text-sm flex-1")
                        ui.label(f"{cand.score:.3f}").classes("px-3 py-1 rounded text-xs bg-purple-500/20 text-purple-300")
                    
                    # Stability flag
                    with ui.row().classes("w-full mb-3"):
                        ui.label("Stability:").classes("font-bold text-slate-300 mr-2")
                        flag_color = {
                            "OK": "text-green-400",
                            "WARN": "text-amber-400",
                            "DROP": "text-red-400",
                        }.get(cand.stability_flag, "text-slate-400")
                        ui.label(cand.stability_flag).classes(f"font-bold {flag_color}")
                    
                    # Plateau hint
                    with ui.row().classes("w-full mb-3"):
                        ui.label("Plateau:").classes("font-bold text-slate-300 mr-2")
                        ui.label(cand.plateau_hint).classes("text-sm text-slate-400")
                    
                    # Explanations
                    ui.label("Explanations:").classes("font-bold text-slate-300 mb-2")
                    with ui.column().classes("w-full pl-4"):
                        for exp in cand.explanations:
                            ui.label(f"• {exp}").classes("text-sm text-slate-400")
    
    def render_operation_summary(summary: OperationSummaryDTO) -> None:
        """操作摘要"""
        ui.label("操作摘要").classes("text-2xl font-bold mb-4 text-cyber-400")
        
        with ui.card().classes("fish-card w-full p-6 border-green-500/30"):
            with ui.row().classes("w-full gap-6"):
                with ui.column().classes("flex-1"):
                    ui.label("已掃描策略").classes("font-bold text-slate-300")
                    ui.label(str(summary.scanned_strategies)).classes("text-3xl font-bold text-green-400")
                    ui.label("策略數量").classes("text-sm text-slate-500")
                with ui.column().classes("flex-1"):
                    ui.label("已評估參數").classes("font-bold text-slate-300")
                    ui.label(str(summary.evaluated_params)).classes("text-3xl font-bold text-blue-400")
                    ui.label("參數組合數").classes("text-sm text-slate-500")
                with ui.column().classes("flex-1"):
                    ui.label("跳過指標").classes("font-bold text-slate-300")
                    ui.label(str(summary.skipped_metrics)).classes("text-3xl font-bold text-amber-400")
                    ui.label("跳過指標數").classes("text-sm text-slate-500")
            
            if summary.notes:
                ui.label("備註").classes("font-bold text-slate-300 mt-6 mb-2")
                with ui.column().classes("w-full pl-4"):
                    for note in summary.notes:
                        ui.label(f"• {note}").classes("text-sm text-slate-400")
    
    def render_system_logs(logs: tuple[str, ...]) -> None:
        """系統日誌（最新 10 行）"""
        ui.label("系統日誌").classes("text-2xl font-bold mb-4 text-cyber-400")
        
        with ui.card().classes("fish-card w-full p-6 border-amber-500/30"):
            if logs:
                ui.label("最新系統日誌").classes("font-bold mb-4")
                log_display = ui.column().classes("w-full font-mono text-xs bg-nexus-900 p-4 rounded-lg max-h-64 overflow-y-auto")
                with log_display:
                    for line in logs:
                        ui.label(line).classes("py-1 border-b border-nexus-800 last:border-0")
            else:
                ui.label("暫無系統日誌").classes("text-slate-500")
                ui.label("日誌檔案可能不存在或無法讀取").classes("text-sm text-slate-600")
    
    def render_navigation_tabs() -> None:
        """導航標籤（快速連結）"""
        ui.label("快速導航").classes("text-2xl font-bold mb-4 text-cyber-400")
        
        with ui.card().classes("fish-card w-full p-6 border-nexus-700"):
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for name, path in NAV:
                    ui.link(name, path).classes(
                        "px-4 py-3 rounded-lg no-underline transition-colors "
                        "hover:bg-nexus-800 text-slate-300 border border-nexus-700"
                    )
    
    def render_constitution_reminder() -> None:
        """憲法級原則提醒（保留原有）"""
        with ui.card().classes("fish-card w-full mt-8 border-cyber-500/30"):
            ui.label("憲法級總原則").classes("font-bold text-cyber-400 mb-2")
            ui.label("1. NiceGUI 永遠是薄客戶端：只做「填單/看單/拿貨/畫圖」").classes("text-sm text-slate-300")
            ui.label("2. 唯一真相在 outputs + job state：UI refresh/斷線不影響任務").classes("text-sm text-slate-300")
            ui.label("3. Worker 是唯一執行者：只有 Worker 可呼叫 Research Runner").classes("text-sm text-slate-300")
            ui.label("4. WFS core 仍然 no-IO：run_wfs_with_features() 不得碰任何 IO").classes("text-sm text-slate-300")
            ui.label("5. 所有視覺化資料必須由 Research/Portfolio 產出 artifact：UI 只渲染").classes("text-sm text-slate-300")
