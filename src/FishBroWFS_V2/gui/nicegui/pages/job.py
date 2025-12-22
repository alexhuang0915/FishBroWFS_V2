
"""任務監控頁面 - Job Monitor"""

from nicegui import ui

from ..api import list_recent_jobs, get_job
from ..state import app_state
from ..layout import render_topbar


def register() -> None:
    """註冊任務監控頁面路由"""
    
    @ui.page("/jobs")
    def jobs_page() -> None:
        """渲染任務列表頁面"""
        ui.page_title("FishBroWFS V2 - 任務監控")
        render_topbar("Job Monitor")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 任務列表容器
            job_list_container = ui.column().classes("w-full")
            
            def refresh_job_list() -> None:
                """刷新任務列表"""
                job_list_container.clear()
                
                try:
                    jobs = list_recent_jobs(limit=50)
                    
                    if not jobs:
                        with job_list_container:
                            ui.label("目前沒有任務").classes("text-gray-500 text-center p-8")
                        return
                    
                    for job in jobs:
                        card = ui.card().classes("w-full mb-4 cursor-pointer hover:bg-gray-50")
                        card.on("click", lambda e, j=job: ui.navigate.to(f"/results/{j.job_id}"))
                        with card:
                            with ui.row().classes("w-full items-center"):
                                # 狀態指示器
                                status_color = {
                                    "PENDING": "bg-yellow-100 text-yellow-800",
                                    "RUNNING": "bg-green-100 text-green-800",
                                    "COMPLETED": "bg-blue-100 text-blue-800",
                                    "FAILED": "bg-red-100 text-red-800",
                                }.get(job.status, "bg-gray-100 text-gray-800")
                                
                                ui.badge(job.status, color=status_color).classes("mr-4")
                                
                                # 任務資訊
                                with ui.column().classes("flex-1"):
                                    ui.label(f"任務 ID: {job.job_id[:8]}...").classes("font-mono text-sm")
                                    ui.label(f"建立時間: {job.created_at}").classes("text-xs text-gray-600")
                                
                                # 進度條（如果有的話）
                                if job.progress is not None:
                                    ui.linear_progress(job.progress, show_value=False).classes("w-32 mr-4")
                                    ui.label(f"{job.progress*100:.1f}%").classes("text-sm")
                                
                                ui.icon("chevron_right").classes("text-gray-400")
                
                except Exception as e:
                    with job_list_container:
                        ui.label(f"載入失敗: {e}").classes("text-red-600")
            
            # 標題與導航
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=refresh_job_list).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_job_list()
    
    @ui.page("/job/{job_id}")
    def job_page(job_id: str) -> None:
        """渲染單一任務詳細頁面"""
        ui.page_title(f"FishBroWFS V2 - 任務 {job_id[:8]}...")
        render_topbar(f"Job Details: {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 任務詳細資訊容器
            job_details_container = ui.column().classes("w-full")
            
            # 日誌容器
            log_container = ui.column().classes("w-full mt-6")
            
            def refresh_job_details(jid: str) -> None:
                """刷新任務詳細資訊"""
                job_details_container.clear()
                
                try:
                    job = get_job(jid)
                    
                    with job_details_container:
                        # 基本資訊卡片
                        with ui.card().classes("w-full mb-4"):
                            ui.label("基本資訊").classes("text-lg font-bold mb-4")
                            
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                ui.label("任務 ID:").classes("font-bold")
                                ui.label(job.job_id).classes("font-mono")
                                
                                ui.label("狀態:").classes("font-bold")
                                status_color = {
                                    "PENDING": "text-yellow-600",
                                    "RUNNING": "text-green-600",
                                    "COMPLETED": "text-blue-600",
                                    "FAILED": "text-red-600",
                                }.get(job.status, "text-gray-600")
                                ui.label(job.status).classes(f"{status_color} font-bold")
                                
                                ui.label("建立時間:").classes("font-bold")
                                ui.label(job.created_at)
                                
                                ui.label("更新時間:").classes("font-bold")
                                ui.label(job.updated_at)
                                
                                if job.progress is not None:
                                    ui.label("進度:").classes("font-bold")
                                    with ui.row().classes("items-center w-full"):
                                        ui.linear_progress(job.progress, show_value=False).classes("flex-1")
                                        ui.label(f"{job.progress*100:.1f}%").classes("ml-2")
                                
                                if job.outputs_path:
                                    ui.label("輸出路徑:").classes("font-bold")
                                    ui.label(job.outputs_path).classes("font-mono text-sm")
                        
                        # 操作按鈕 - 根據 Phase 6.5 規範，未完成功能必須 disabled
                        with ui.row().classes("w-full gap-2 mb-6"):
                            # 任務控制按鈕（DEV MODE - 未實作）
                            if job.status == "PENDING":
                                ui.button("開始任務", icon="play_arrow", color="green").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                            elif job.status == "RUNNING":
                                ui.button("暫停任務", icon="pause", color="yellow").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                                ui.button("停止任務", icon="stop", color="red").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                            
                            # 導航按鈕
                            ui.button("查看結果", icon="insights", on_click=lambda: ui.navigate.to(f"/results/{jid}")).props("outline")
                            ui.button("查看圖表", icon="show_chart", on_click=lambda: ui.navigate.to(f"/charts/{jid}")).props("outline")
                            ui.button("部署", icon="download", on_click=lambda: ui.navigate.to(f"/deploy/{jid}")).props("outline")
                    
                    # 刷新日誌
                    refresh_log(jid)
                    
                except Exception as e:
                    with job_details_container:
                        with ui.card().classes("w-full bg-red-50 border-red-200"):
                            ui.label("任務載入失敗").classes("text-red-800 font-bold mb-2")
                            ui.label(f"錯誤: {e}").classes("text-red-700 mb-2")
                            ui.label("可能原因:").classes("text-red-700 font-bold mb-1")
                            ui.label("• Control API 未啟動").classes("text-red-700 text-sm")
                            ui.label("• 任務 ID 不存在").classes("text-red-700 text-sm")
                            ui.label("• 網路連線問題").classes("text-red-700 text-sm")
                            with ui.row().classes("mt-4"):
                                ui.button("返回任務列表", on_click=lambda: ui.navigate.to("/jobs"), icon="arrow_back").props("outline")
                                ui.button("重試", on_click=lambda: refresh_job_details(jid), icon="refresh").props("outline")
            
            def refresh_log(jid: str) -> None:
                """刷新日誌顯示 - 誠實顯示真實狀態"""
                log_container.clear()
                
                with log_container:
                    ui.label("任務日誌").classes("text-lg font-bold mb-4")
                    
                    # 日誌顯示區域
                    log_display = ui.textarea("").classes("w-full h-64 font-mono text-sm").props("readonly")
                    
                    # 誠實顯示：如果沒有真實日誌，顯示 DEV MODE 訊息
                    try:
                        # 嘗試從 API 獲取真實日誌
                        job = get_job(jid)
                        if job.latest_log_tail:
                            log_display.value = job.latest_log_tail
                        else:
                            log_display.value = f"DEV MODE: 日誌系統尚未實作\n\n"
                            log_display.value += f"任務 ID: {jid}\n"
                            log_display.value += f"狀態: {job.status}\n"
                            log_display.value += f"建立時間: {job.created_at}\n"
                            log_display.value += f"更新時間: {job.updated_at}\n\n"
                            log_display.value += "真實日誌將在任務執行時顯示。"
                    except Exception as e:
                        log_display.value = f"載入日誌時發生錯誤: {e}"
            
            # 標題與導航
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=lambda: refresh_job_details(job_id)).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_job_details(job_id)
            
            # 自動刷新計時器（如果任務正在運行）
            def auto_refresh() -> None:
                # TODO: 根據任務狀態決定是否自動刷新
                pass
            
            ui.timer(5.0, auto_refresh)


