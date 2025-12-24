"""設定頁面 - Settings"""

from nicegui import ui

from ..api import get_system_settings, update_system_settings
from ..state import app_state


def register() -> None:
    """註冊設定頁面"""
    
    @ui.page("/settings")
    def settings_page() -> None:
        """設定頁面"""
        ui.page_title("FishBroWFS V2 - Settings")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 頁面標題
            ui.label("System Settings").classes("text-3xl font-bold mb-2 text-cyber-400")
            ui.label("Configure system parameters, environment variables, and API endpoints").classes("text-slate-400 mb-8")
            
            # 設定容器
            settings_container = ui.column().classes("w-full")
            
            def refresh_settings() -> None:
                """刷新設定資訊"""
                settings_container.clear()
                
                try:
                    # 獲取系統設定
                    settings = get_system_settings()
                    
                    with settings_container:
                        # 系統資訊卡片
                        with ui.card().classes("w-full mb-6"):
                            ui.label("System Information").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                ui.label("Season").classes("font-bold")
                                ui.label(app_state.season).classes("text-green-400")
                                
                                ui.label("Freeze Status").classes("font-bold")
                                if app_state.frozen:
                                    ui.label("FROZEN").classes("text-red-400 font-bold")
                                else:
                                    ui.label("ACTIVE").classes("text-green-400 font-bold")
                                
                                ui.label("API Endpoint").classes("font-bold")
                                ui.label(settings.get("api_endpoint", "http://localhost:8081")).classes("text-slate-300")
                                
                                ui.label("Dashboard Version").classes("font-bold")
                                ui.label(settings.get("version", "2.0.0")).classes("text-slate-300")
                        
                        # 環境變數設定
                        with ui.card().classes("w-full mb-6"):
                            ui.label("Environment Variables").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            # 顯示環境變數
                            env_vars = settings.get("environment", {})
                            if env_vars:
                                for key, value in env_vars.items():
                                    with ui.row().classes("w-full items-center mb-2"):
                                        ui.label(f"{key}:").classes("w-48 font-mono text-sm text-slate-400")
                                        ui.label(str(value)).classes("flex-1 font-mono text-sm bg-nexus-800 p-2 rounded")
                            else:
                                ui.label("No environment variables configured").classes("text-slate-500 italic")
                        
                        # API 端點設定
                        with ui.card().classes("w-full mb-6"):
                            ui.label("API Endpoints").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            endpoints = settings.get("endpoints", {})
                            if endpoints:
                                for name, url in endpoints.items():
                                    with ui.row().classes("w-full items-center mb-2"):
                                        ui.label(f"{name}:").classes("w-48 text-slate-400")
                                        ui.link(url, url, new_tab=True).classes("flex-1 font-mono text-sm text-cyber-400 hover:text-cyber-300")
                            else:
                                ui.label("No API endpoints configured").classes("text-slate-500 italic")
                        
                        # 系統設定選項
                        with ui.card().classes("w-full mb-6"):
                            ui.label("System Configuration").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            # 自動刷新設定
                            auto_refresh = ui.switch("Auto-refresh dashboard", value=settings.get("auto_refresh", True))
                            
                            # 通知設定
                            notifications = ui.switch("Enable notifications", value=settings.get("notifications", False))
                            
                            # 主題設定
                            theme = ui.select(["dark", "light", "auto"], value=settings.get("theme", "dark"), label="Theme")
                            
                            # 儲存按鈕
                            def save_settings() -> None:
                                """儲存設定"""
                                new_settings = {
                                    "auto_refresh": auto_refresh.value,
                                    "notifications": notifications.value,
                                    "theme": theme.value,
                                }
                                try:
                                    update_system_settings(new_settings)
                                    ui.notify("Settings saved successfully", type="positive")
                                except Exception as e:
                                    ui.notify(f"Failed to save settings: {e}", type="negative")
                            
                            ui.button("Save Settings", on_click=save_settings, icon="save").classes("mt-4 bg-cyber-500 hover:bg-cyber-400")
                        
                        # 系統操作
                        with ui.card().classes("w-full"):
                            ui.label("System Operations").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            with ui.row().classes("w-full gap-4"):
                                # 清除快取
                                def clear_cache() -> None:
                                    """清除系統快取"""
                                    ui.notify("Cache cleared (simulated)", type="info")
                                
                                ui.button("Clear Cache", on_click=clear_cache, icon="delete").classes("bg-amber-600 hover:bg-amber-500")
                                
                                # 重新載入設定
                                def reload_config() -> None:
                                    """重新載入設定"""
                                    refresh_settings()
                                    ui.notify("Settings reloaded", type="info")
                                
                                ui.button("Reload Settings", on_click=reload_config, icon="refresh").classes("bg-blue-600 hover:bg-blue-500")
                                
                                # 重啟服務
                                def restart_service() -> None:
                                    """重啟服務（模擬）"""
                                    ui.notify("Service restart initiated (simulated)", type="warning")
                                
                                ui.button("Restart Service", on_click=restart_service, icon="restart_alt").classes("bg-red-600 hover:bg-red-500")
                            
                            # 警告訊息
                            ui.separator().classes("my-4")
                            with ui.row().classes("w-full items-center p-4 bg-yellow-900/30 border border-yellow-700 rounded"):
                                ui.icon("warning", size="sm").classes("text-yellow-400 mr-2")
                                ui.label("System operations may affect running jobs. Use with caution.").classes("text-sm text-yellow-300")
                
                except Exception as e:
                    with settings_container:
                        ui.label(f"Failed to load settings: {e}").classes("text-red-400")
                        
                        # 顯示錯誤卡片
                        with ui.card().classes("w-full p-6 bg-red-900/20 border border-red-700"):
                            ui.icon("error", size="xl").classes("text-red-400 mx-auto mb-4")
                            ui.label("Settings API Not Available").classes("text-xl font-bold text-red-300 text-center mb-2")
                            ui.label("The system settings API is not currently available.").classes("text-red-200 text-center mb-4")
                            ui.label("This may be because the control API is not running or the endpoint is not configured.").classes("text-sm text-slate-400 text-center")
            
            # 初始載入
            refresh_settings()