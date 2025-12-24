"""Stale Warning 服務 - UI 開著超過 10 分鐘顯示警告"""

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class StaleState:
    """Stale 狀態"""
    opened_at: float
    warned: bool = False
    last_check: float = 0.0
    warning_shown_at: Optional[float] = None


def should_warn_stale(state: StaleState, seconds: int = 600) -> bool:
    """
    檢查是否應該顯示 stale warning
    
    Args:
        state: StaleState 物件
        seconds: 警告閾值（秒），預設 600 秒（10 分鐘）
    
    Returns:
        bool: 是否應該顯示警告
    """
    if state.warned:
        return False
    
    elapsed = time.time() - state.opened_at
    return elapsed >= seconds


def update_stale_state(state: StaleState) -> dict:
    """
    更新 stale 狀態並返回狀態資訊
    
    Args:
        state: StaleState 物件
    
    Returns:
        dict: 狀態資訊
    """
    current_time = time.time()
    elapsed = current_time - state.opened_at
    
    state.last_check = current_time
    
    # 檢查是否應該警告
    should_warn = should_warn_stale(state)
    
    if should_warn and not state.warned:
        state.warned = True
        state.warning_shown_at = current_time
    
    return {
        "opened_at": state.opened_at,
        "opened_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.opened_at)),
        "elapsed_seconds": elapsed,
        "elapsed_minutes": elapsed / 60,
        "elapsed_hours": elapsed / 3600,
        "should_warn": should_warn,
        "warned": state.warned,
        "warning_shown_at": state.warning_shown_at,
        "warning_shown_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.warning_shown_at)) if state.warning_shown_at else None,
        "last_check": state.last_check,
    }


class StaleMonitor:
    """Stale 監視器"""
    
    def __init__(self, warning_threshold_seconds: int = 600):
        """
        初始化 StaleMonitor
        
        Args:
            warning_threshold_seconds: 警告閾值（秒）
        """
        self.warning_threshold = warning_threshold_seconds
        self._states = {}  # client_id -> StaleState
        self._start_time = time.time()
    
    def register_client(self, client_id: str) -> StaleState:
        """
        註冊客戶端
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            StaleState: 新建立的狀態
        """
        state = StaleState(opened_at=time.time())
        self._states[client_id] = state
        return state
    
    def unregister_client(self, client_id: str) -> None:
        """取消註冊客戶端"""
        if client_id in self._states:
            del self._states[client_id]
    
    def get_client_state(self, client_id: str) -> Optional[StaleState]:
        """獲取客戶端狀態"""
        return self._states.get(client_id)
    
    def update_client(self, client_id: str) -> Optional[dict]:
        """
        更新客戶端狀態
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            Optional[dict]: 狀態資訊，如果客戶端不存在則返回 None
        """
        state = self.get_client_state(client_id)
        if state is None:
            return None
        
        return update_stale_state(state)
    
    def check_all_clients(self) -> dict:
        """
        檢查所有客戶端
        
        Returns:
            dict: 所有客戶端的狀態摘要
        """
        results = {}
        warnings = []
        
        for client_id, state in self._states.items():
            info = update_stale_state(state)
            results[client_id] = info
            
            if info["should_warn"] and not state.warned:
                warnings.append({
                    "client_id": client_id,
                    "elapsed_minutes": info["elapsed_minutes"],
                    "opened_at": info["opened_at_iso"],
                })
        
        return {
            "total_clients": len(self._states),
            "clients": results,
            "warnings": warnings,
            "has_warnings": len(warnings) > 0,
            "monitor_uptime": time.time() - self._start_time,
        }
    
    def reset_client(self, client_id: str) -> Optional[StaleState]:
        """
        重置客戶端狀態（重新計時）
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            Optional[StaleState]: 新的狀態，如果客戶端不存在則返回 None
        """
        if client_id not in self._states:
            return None
        
        self._states[client_id] = StaleState(opened_at=time.time())
        return self._states[client_id]


# 全域監視器實例
_global_monitor: Optional[StaleMonitor] = None

def get_global_monitor() -> StaleMonitor:
    """獲取全域 StaleMonitor 實例"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = StaleMonitor()
    return _global_monitor


def create_stale_warning_message(state_info: dict) -> str:
    """
    建立 stale warning 訊息
    
    Args:
        state_info: 狀態資訊
    
    Returns:
        str: 警告訊息
    """
    elapsed_minutes = state_info["elapsed_minutes"]
    
    if elapsed_minutes < 60:
        time_str = f"{elapsed_minutes:.1f} 分鐘"
    else:
        time_str = f"{elapsed_minutes/60:.1f} 小時"
    
    return (
        f"⚠️  UI 已開啟 {time_str}，資料可能已過期。\n"
        f"建議重新整理頁面以獲取最新資料。\n"
        f"（開啟時間: {state_info['opened_at_iso']})"
    )


def create_stale_warning_ui_state(state_info: dict) -> dict:
    """
    建立 stale warning UI 狀態
    
    Args:
        state_info: 狀態資訊
    
    Returns:
        dict: UI 狀態
    """
    return {
        "show_warning": state_info["should_warn"],
        "message": create_stale_warning_message(state_info) if state_info["should_warn"] else "",
        "severity": "warning",
        "elapsed_minutes": state_info["elapsed_minutes"],
        "opened_at": state_info["opened_at_iso"],
        "can_dismiss": True,
        "auto_refresh_suggested": state_info["elapsed_minutes"] > 20,  # 超過 20 分鐘建議自動重新整理
    }