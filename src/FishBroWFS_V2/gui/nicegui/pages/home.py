
"""首頁 - Dashboard/Home"""

from nicegui import ui

from ..state import app_state
from ..layout import render_topbar


def register() -> None:
    """註冊首頁路由"""
    
    @ui.page("/")
    def home_page() -> None:
        """渲染首頁"""
        ui.page_title("FishBroWFS V2 - 儀表板")
        render_topbar("FishBroWFS V2 Dashboard")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 標題區
            ui.label("🐟 FishBroWFS V2 研究控制面板").classes("text-3xl font-bold mb-2")
            ui.label("唯一 UI = NiceGUI（Submit job / Monitor / Results / Deploy / Charts）").classes("text-lg text-gray-600 mb-8")
            
            # 快速操作卡片
            ui.label("快速操作").classes("text-xl font-bold mb-4")
            
            with ui.row().classes("w-full gap-4 mb-8"):
                card1 = ui.card().classes("w-1/3 p-4 cursor-pointer hover:bg-gray-50")
                card1.on("click", lambda e: ui.navigate.to("/new-job"))
                with card1:
                    ui.icon("add_circle", size="lg").classes("text-blue-500 mb-2")
                    ui.label("新增研究任務").classes("font-bold")
                    ui.label("設定 dataset/symbols/TF/strategy 等參數").classes("text-sm text-gray-600")
                
                card2 = ui.card().classes("w-1/3 p-4 cursor-pointer hover:bg-gray-50")
                card2.on("click", lambda e: ui.navigate.to("/jobs"))
                with card2:
                    ui.icon("monitoring", size="lg").classes("text-green-500 mb-2")
                    ui.label("任務監控").classes("font-bold")
                    ui.label("查看任務狀態、進度、日誌").classes("text-sm text-gray-600")
                
                card3 = ui.card().classes("w-1/3 p-4 cursor-pointer hover:bg-gray-50")
                card3.on("click", lambda e: ui.notify("請先選擇一個任務", type="info"))
                with card3:
                    ui.icon("insights", size="lg").classes("text-purple-500 mb-2")
                    ui.label("查看結果").classes("font-bold")
                    ui.label("rolling summary 表格與詳細報告").classes("text-sm text-gray-600")
            
            # 最近任務區
            ui.label("最近任務").classes("text-xl font-bold mb-4")
            
            # 任務列表（暫時為空）
            with ui.card().classes("w-full p-4"):
                ui.label("載入中...").classes("text-gray-500")
                # TODO: 實作動態載入任務列表
            
            # 系統狀態區
            ui.label("系統狀態").classes("text-xl font-bold mb-4 mt-8")
            
            with ui.row().classes("w-full gap-4"):
                with ui.card().classes("flex-1 p-4"):
                    ui.label("Control API").classes("font-bold")
                    ui.label("✅ 運行中").classes("text-green-600")
                    ui.label("localhost:8000").classes("text-sm text-gray-600")
                
                with ui.card().classes("flex-1 p-4"):
                    ui.label("Worker").classes("font-bold")
                    ui.label("🟡 待檢查").classes("text-yellow-600")
                    ui.label("需要啟動 worker daemon").classes("text-sm text-gray-600")
                
                with ui.card().classes("flex-1 p-4"):
                    ui.label("資料集").classes("font-bold")
                    ui.label("📊 可用").classes("text-blue-600")
                    ui.label("從 registry 載入").classes("text-sm text-gray-600")
            
            # 憲法級原則提醒
            with ui.card().classes("w-full mt-8 bg-blue-50 border-blue-200"):
                ui.label("憲法級總原則").classes("font-bold text-blue-800 mb-2")
                ui.label("1. NiceGUI 永遠是薄客戶端：只做「填單/看單/拿貨/畫圖」").classes("text-sm text-blue-700")
                ui.label("2. 唯一真相在 outputs + job state：UI refresh/斷線不影響任務").classes("text-sm text-blue-700")
                ui.label("3. Worker 是唯一執行者：只有 Worker 可呼叫 Research Runner").classes("text-sm text-blue-700")
                ui.label("4. WFS core 仍然 no-IO：run_wfs_with_features() 不得碰任何 IO").classes("text-sm text-blue-700")
                ui.label("5. 所有視覺化資料必須由 Research/Portfolio 產出 artifact：UI 只渲染").classes("text-sm text-blue-700")


