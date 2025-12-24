
"""首頁 - Dashboard/Home"""

from nicegui import ui

from ..state import app_state


def register() -> None:
    """註冊首頁路由"""
    
    @ui.page("/")
    def home_page() -> None:
        """渲染首頁"""
        ui.page_title("FishBroWFS V2 - 儀表板")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 標題區
            ui.label("🐟 FishBroWFS V2 研究控制面板").classes("text-3xl font-bold mb-2 text-cyber-glow")
            ui.label("唯一 UI = NiceGUI（Submit job / Monitor / Results / Deploy / Charts）").classes("text-lg text-slate-400 mb-8")
            
            # 快速操作卡片
            ui.label("快速操作").classes("text-xl font-bold mb-4 text-cyber-400")
            
            with ui.row().classes("w-full gap-4 mb-8"):
                card1 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer glow")
                card1.on("click", lambda e: ui.navigate.to("/wizard"))
                with card1:
                    ui.icon("rocket_launch", size="lg").classes("text-cyber-500 mb-2")
                    ui.label("新增研究任務").classes("font-bold text-white")
                    ui.label("設定 dataset/symbols/TF/strategy 等參數").classes("text-sm text-slate-400")
                
                card2 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer")
                card2.on("click", lambda e: ui.navigate.to("/history"))
                with card2:
                    ui.icon("history", size="lg").classes("text-green-500 mb-2")
                    ui.label("Runs History").classes("font-bold text-white")
                    ui.label("查看任務狀態、進度、日誌").classes("text-sm text-slate-400")
                
                card3 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer")
                card3.on("click", lambda e: ui.notify("請先選擇一個任務", type="info"))
                with card3:
                    ui.icon("insights", size="lg").classes("text-purple-500 mb-2")
                    ui.label("查看結果").classes("font-bold text-white")
                    ui.label("rolling summary 表格與詳細報告").classes("text-sm text-slate-400")
            
            # 最近任務區
            ui.label("最近任務").classes("text-xl font-bold mb-4 text-cyber-400")
            
            # 任務列表（使用 RunsIndex）
            with ui.card().classes("fish-card w-full p-4"):
                from ...services.runs_index import get_global_index
                
                index = get_global_index()
                runs = index.list(season="2026Q1", include_archived=False)[:5]
                
                if runs:
                    ui.label(f"最新 {len(runs)} 個 runs:").classes("font-bold mb-2")
                    for run in runs:
                        with ui.row().classes("w-full py-2 border-b border-nexus-800 last:border-0"):
                            ui.label(run.run_id).classes("flex-1 font-mono text-sm")
                            status_class = {
                                'completed': 'bg-green-500/20 text-green-300',
                                'running': 'bg-blue-500/20 text-blue-300',
                                'failed': 'bg-red-500/20 text-red-300'
                            }.get(run.status, 'bg-slate-500/20 text-slate-300')
                            ui.label(run.status).classes(f"px-2 py-1 rounded text-xs {status_class}")
                else:
                    ui.label("沒有找到 runs").classes("text-slate-500")
                    ui.label("請確認 outputs 目錄結構正確").classes("text-sm text-slate-600")
            
            # 系統狀態區
            ui.label("系統狀態").classes("text-xl font-bold mb-4 mt-8 text-cyber-400")
            
            with ui.row().classes("w-full gap-4"):
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("Control API").classes("font-bold")
                    ui.label("✅ 運行中").classes("text-green-400")
                    ui.label("localhost:8000").classes("text-sm text-slate-400")
                
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("Worker").classes("font-bold")
                    ui.label("🟡 待檢查").classes("text-yellow-400")
                    ui.label("需要啟動 worker daemon").classes("text-sm text-slate-400")
                
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("資料集").classes("font-bold")
                    ui.label("📊 可用").classes("text-blue-400")
                    ui.label("從 registry 載入").classes("text-sm text-slate-400")
            
            # 憲法級原則提醒
            with ui.card().classes("fish-card w-full mt-8 border-cyber-500/30"):
                ui.label("憲法級總原則").classes("font-bold text-cyber-400 mb-2")
                ui.label("1. NiceGUI 永遠是薄客戶端：只做「填單/看單/拿貨/畫圖」").classes("text-sm text-slate-300")
                ui.label("2. 唯一真相在 outputs + job state：UI refresh/斷線不影響任務").classes("text-sm text-slate-300")
                ui.label("3. Worker 是唯一執行者：只有 Worker 可呼叫 Research Runner").classes("text-sm text-slate-300")
                ui.label("4. WFS core 仍然 no-IO：run_wfs_with_features() 不得碰任何 IO").classes("text-sm text-slate-300")
                ui.label("5. 所有視覺化資料必須由 Research/Portfolio 產出 artifact：UI 只渲染").classes("text-sm text-slate-300")


