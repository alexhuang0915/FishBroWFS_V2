
"""NiceGUI 應用程式狀態管理"""

from typing import Dict, Any, Optional


class AppState:
    """應用程式全域狀態"""
    
    _instance: Optional["AppState"] = None
    
    def __new__(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """初始化狀態"""
        self.current_job_id: Optional[str] = None
        self.user_preferences: Dict[str, Any] = {
            "theme": "dark",
            "refresh_interval": 5,  # 秒
            "default_outputs_root": "outputs",
        }
        self.notifications: list = []
    
    def set_current_job(self, job_id: str) -> None:
        """設定當前選中的任務"""
        self.current_job_id = job_id
    
    def get_current_job(self) -> Optional[str]:
        """取得當前選中的任務"""
        return self.current_job_id
    
    def add_notification(self, message: str, level: str = "info") -> None:
        """新增通知訊息"""
        self.notifications.append({
            "message": message,
            "level": level,
            "timestamp": "now"  # 實際應用中應使用 datetime
        })
        # 限制通知數量
        if len(self.notifications) > 10:
            self.notifications.pop(0)
    
    def clear_notifications(self) -> None:
        """清除所有通知"""
        self.notifications.clear()


# 全域狀態實例
app_state = AppState()


