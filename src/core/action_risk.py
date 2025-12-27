"""Action Risk Levels - 資料契約

定義系統動作的風險等級，用於實盤安全鎖。
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class RiskLevel(str, Enum):
    """動作風險等級"""
    READ_ONLY = "READ_ONLY"
    RESEARCH_MUTATE = "RESEARCH_MUTATE"
    LIVE_EXECUTE = "LIVE_EXECUTE"


@dataclass(frozen=True)
class ActionPolicyDecision:
    """政策決策結果"""
    allowed: bool
    reason: str
    risk: RiskLevel
    action: str
    season: Optional[str] = None