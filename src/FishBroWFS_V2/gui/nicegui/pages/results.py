
"""結果頁面 - Results"""

from nicegui import ui

from ..api import get_season_report, generate_deploy_zip
from ..state import app_state
from ..layout import render_topbar


def register() -> None:
    """註冊結果頁面路由"""
    
    @ui.page("/results/{job_id}")
    def results_page(job_id: str) -> None:
        """渲染結果頁面"""
        ui.page_title(f"FishBroWFS V2 - 任務結果 {job_id[:8]}...")
        render_topbar(f"Results: {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 結果容器
            results_container = ui.column().classes("w-full")
            
            def refresh_results(jid: str) -> None:
                """刷新結果顯示"""
                results_container.clear()
                
                try:
                    with results_container:
                        # 顯示 DEV MODE Banner
                        with ui.card().classes("w-full bg-blue-50 border-blue-200 mb-6"):
                            ui.label("Phase 6.5 - UI 誠實化").classes("text-blue-800 font-bold mb-1")
                            ui.label("此頁面只顯示真實資料 (SSOT)，不渲染假表格").classes("text-blue-700 text-sm")
                        
                        # Rolling Summary 區塊 - 誠實顯示 "Not wired yet (Phase 7)"
                        ui.separator()
                        ui.label("Rolling Summary").classes("font-bold text-xl mb-2")
                        ui.label("Not wired yet (Phase 7)").classes("text-gray-500 mb-6")
                        
                        # 顯示任務基本資訊
                        with ui.card().classes("w-full bg-gray-50 border-gray-200 p-6 mb-6"):
                            ui.label("任務基本資訊").classes("font-bold mb-2")
                            ui.label(f"任務 ID: {jid}").classes("text-sm")
                            ui.label("狀態: 請查看 Job Monitor 頁面").classes("text-sm")
                        
                        # 操作按鈕 - 誠實顯示功能狀態
                        with ui.row().classes("w-full gap-2 mt-6"):
                            ui.button("View Charts", icon="show_chart", on_click=lambda: ui.navigate.to(f"/charts/{jid}")).props("outline")
                            ui.button("Deploy", icon="download", on_click=lambda: ui.navigate.to(f"/deploy/{jid}")).props("outline")
                            
                            # Generate Deploy Zip 按鈕 - 誠實顯示未實作
                            def generate_deploy_handler():
                                """處理 Generate Deploy Zip 按鈕點擊"""
                                ui.notify("Deploy zip generation not implemented yet (Phase 7)", type="warning")
                            
                            ui.button("Generate Deploy Zip", icon="archive", color="gray", on_click=generate_deploy_handler).props("disabled").tooltip("Not implemented yet (Phase 7)")
                    
                except Exception as e:
                    with results_container:
                        with ui.card().classes("w-full bg-red-50 border-red-200 p-6"):
                            ui.label("載入結果失敗").classes("text-red-800 font-bold mb-2")
                            ui.label(f"錯誤: {e}").classes("text-red-700 mb-2")
                            ui.label("可能原因:").classes("text-red-700 font-bold mb-1")
                            ui.label("• Control API 未啟動").classes("text-red-700 text-sm")
                            ui.label("• 任務 ID 不存在").classes("text-red-700 text-sm")
                            ui.label("• 網路連線問題").classes("text-red-700 text-sm")
                            with ui.row().classes("mt-4"):
                                ui.button("返回任務列表", on_click=lambda: ui.navigate.to("/jobs"), icon="arrow_back").props("outline")
                                ui.button("重試", on_click=lambda: refresh_results(jid), icon="refresh").props("outline")
            
            # 刷新按鈕
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=lambda: refresh_results(job_id)).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_results(job_id)


