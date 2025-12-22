
"""部署頁面 - Deploy"""

from nicegui import ui

from ..api import generate_deploy_zip, get_rolling_summary
from ..state import app_state
from ..layout import render_topbar


def register() -> None:
    """註冊部署頁面"""
    
    @ui.page("/deploy/{job_id}")
    def deploy_page(job_id: str) -> None:
        """部署頁面"""
        ui.page_title(f"FishBroWFS V2 - Deploy {job_id[:8]}...")
        render_topbar(f"Deploy: {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # DEV MODE banner - 醒目的誠實化標示
            with ui.card().classes("w-full mb-6 bg-red-50 border-red-300"):
                with ui.row().classes("w-full items-center"):
                    ui.icon("error", size="lg").classes("text-red-600 mr-2")
                    ui.label("DEV MODE: Deploy system NOT WIRED").classes("text-red-800 font-bold text-lg")
                ui.label("Deploy gate checking and ZIP generation are currently NOT IMPLEMENTED.").classes("text-sm text-red-700 mb-2")
                ui.label("Constitutional principle: Deploy gate must be double-checked (UI + Control layer).").classes("text-xs text-red-600")
                ui.label("Expected workflow: Control layer validates survive_s2 and generates deploy artifacts.").classes("font-mono text-xs text-gray-600")
            
            # 部署資訊容器
            deploy_container = ui.column().classes("w-full")
            
            def refresh_deploy_info(jid: str) -> None:
                """刷新部署資訊"""
                deploy_container.clear()
                
                try:
                    # 獲取滾動摘要來檢查 gate 條件
                    rolling_summary = get_rolling_summary(jid)
                    
                    with deploy_container:
                        # 檢查 latest season 的 survive_s2
                        latest_season_survive_s2 = False
                        latest_season_info = {}
                        
                        if rolling_summary and "seasons" in rolling_summary and rolling_summary["seasons"]:
                            latest_season = rolling_summary["seasons"][-1]
                            latest_season_survive_s2 = latest_season.get("survive_s2", False)
                            latest_season_info = latest_season
                        
                        # Gate 檢查卡片 - 誠實顯示狀態
                        with ui.card().classes("w-full mb-6"):
                            ui.label("Deploy Gate Check (NOT WIRED)").classes("text-xl font-bold mb-4 text-red-700")
                            
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                # 條件 1: latest season 檢查
                                ui.label("Condition 1: Latest Season").classes("font-bold")
                                if latest_season_info:
                                    ui.label(f"✅ Present (Season: {latest_season_info.get('season', 'N/A')})").classes("text-green-600")
                                else:
                                    ui.label("❌ No latest season data").classes("text-red-600")
                                
                                # 條件 2: survive_s2 == True
                                ui.label("Condition 2: survive_s2 == True").classes("font-bold")
                                if latest_season_survive_s2:
                                    ui.label("✅ Passed").classes("text-green-600 font-bold")
                                else:
                                    ui.label("❌ Failed").classes("text-red-600 font-bold")
                                    if latest_season_info:
                                        ui.label(f"Reason: {latest_season_info.get('fail_reason', 'Unknown')}").classes("text-red-600 text-sm")
                            
                            # 總體檢查結果 - 誠實顯示 NOT WIRED
                            ui.separator().classes("my-4")
                            
                            with ui.row().classes("w-full items-center justify-center p-4 bg-yellow-50 rounded border-yellow-300"):
                                ui.icon("warning", size="xl").classes("text-yellow-600 mr-2")
                                ui.label("DEV MODE: Deploy gate checking NOT WIRED").classes("text-yellow-800 font-bold")
                            
                            ui.label("Note: This gate check is for display only. Real gate validation must be performed by Control layer.").classes("text-sm text-gray-600 mt-2")
                        
                        # 部署操作區 - 永遠顯示 NOT WIRED
                        with ui.card().classes("w-full mb-6 bg-gray-50 border-gray-300"):
                            ui.label("Generate Deployment Package (NOT WIRED)").classes("text-xl font-bold mb-4 text-gray-700")
                            
                            ui.label("Deployment ZIP generation is not yet implemented.").classes("text-gray-600 mb-4")
                            
                            # 預期的工作流程
                            with ui.card().classes("w-full p-4 mb-4 bg-white border-gray-300"):
                                ui.label("Expected workflow:").classes("font-bold mb-2")
                                with ui.column().classes("ml-2 text-sm text-gray-700"):
                                    ui.label("1. Control layer validates survive_s2 == True")
                                    ui.label("2. Control layer generates deploy artifacts (config, reports, manifest)")
                                    ui.label("3. Control layer creates ZIP with manifest_sha256")
                                    ui.label("4. UI downloads ZIP via Control API")
                                    ui.label("5. Double-check: UI + Control both validate gate")
                            
                            # 產生按鈕 - 永遠 disabled
                            def generate_deploy() -> None:
                                """產生部署 ZIP - NOT WIRED"""
                                ui.notify("Deployment generation NOT IMPLEMENTED. Control API endpoint returns 'not_implemented'.", type="warning")
                            
                            ui.button("Generate Deploy Zip (NOT WIRED)", on_click=generate_deploy, icon="archive",
                                     props="disabled").classes("bg-gray-300 text-gray-600 w-full py-3").tooltip("DEV MODE: ZIP generation not implemented")
                        
                        # 檢查清單 - 誠實顯示真實狀態
                        with ui.card().classes("w-full"):
                            ui.label("Deployment Checklist (NOT WIRED)").classes("text-xl font-bold mb-4 text-gray-700")
                            
                            # 誠實的檢查清單，所有項目都為 False
                            checklist_items = [
                                {"item": "S1 recommended parameters verified", "checked": False, "note": "NOT IMPLEMENTED: Parameter validation not wired"},
                                {"item": "Commission settings correct", "checked": False, "note": "NOT IMPLEMENTED: Commission validation not wired"},
                                {"item": "Slippage stress test passed", "checked": False, "note": "NOT IMPLEMENTED: Stress test validation not wired"},
                                {"item": "Max drawdown within acceptable range", "checked": False, "note": "NOT IMPLEMENTED: Drawdown range validation not wired"},
                                {"item": "Sufficient number of trades", "checked": False, "note": "NOT IMPLEMENTED: Trade count validation not wired"},
                                {"item": "manifest_sha256 calculated", "checked": False, "note": "NOT IMPLEMENTED: Manifest generation not wired"},
                                {"item": "All dependencies packaged", "checked": False, "note": "NOT IMPLEMENTED: Dependency packaging not wired"},
                            ]
                            
                            for check in checklist_items:
                                with ui.row().classes("w-full items-center mb-2"):
                                    ui.icon("radio_button_unchecked").classes("text-gray-400 mr-2")
                                    ui.label(check["item"]).classes("flex-1 text-gray-600")
                                    ui.icon("info").classes("text-gray-400 ml-2").tooltip(check["note"])
                            
                            # 總體狀態 - 永遠 0%
                            ui.separator().classes("my-4")
                            ui.label("Completion: 0/7 (0%) - NOT WIRED").classes("font-bold text-red-600")
                            ui.linear_progress(0, show_value=False).classes("w-full bg-gray-200")
                        
                        # 憲法級原則提醒
                        with ui.card().classes("w-full mt-6 bg-blue-50 border-blue-300"):
                            ui.label("Constitutional Principles").classes("font-bold text-blue-800 mb-2")
                            with ui.column().classes("ml-2 text-sm text-blue-700"):
                                ui.label("• Deploy gate must be double-checked: UI checks once, control layer also checks (anti-bypass)")
                                ui.label("• UI cannot bypass gate - must rely on Control layer validation")
                                ui.label("• ZIP generation must be performed by Control layer, not UI")
                                ui.label("• UI only displays real system state, no fake success")
                                ui.label("• All validation must be performed by the system, not UI")
                
                except Exception as e:
                    with deploy_container:
                        ui.label(f"Load failed: {e}").classes("text-red-600")
                        # 顯示 NOT WIRED 訊息
                        with ui.card().classes("w-full p-6 bg-red-50 border-red-300"):
                            ui.icon("error", size="xl").classes("text-red-600 mx-auto mb-4")
                            ui.label("Deploy system NOT WIRED").classes("text-xl font-bold text-red-800 text-center mb-2")
                            ui.label("The deploy gate checking and ZIP generation system is not yet implemented.").classes("text-red-700 text-center")
            
            def download_zip(zip_path: str) -> None:
                """模擬下載 ZIP 檔案"""
                ui.notify(f"Starting download: {zip_path}", type="info")
                # 實際應用中這裡會提供檔案下載
            
            # 初始載入
            refresh_deploy_info(job_id)


