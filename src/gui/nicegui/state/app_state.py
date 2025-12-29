"""Global application state."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppState:
    """Global UI state (in memory only)."""
    
    # Current season (default from env)
    season: str = "2026Q1"
    
    # Current active tab
    active_tab: str = "dashboard"
    
    # System status
    backend_online: bool = False
    worker_alive: bool = False
    
    # User preferences (non‑authoritative)
    default_compute_level: str = "MID"
    default_safety_limit: int = 500
    
    # Toast history (optional)
    toast_history: list = field(default_factory=list)
    
    # Singleton instance
    _instance: Optional["AppState"] = None
    
    @classmethod
    def get(cls) -> "AppState":
        """Return singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def reset(self) -> None:
        """Reset state to defaults (except season)."""
        self.active_tab = "dashboard"
        self.backend_online = False
        self.worker_alive = False
        # keep season and preferences