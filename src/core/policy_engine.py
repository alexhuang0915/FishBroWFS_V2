"""Policy Engine - 實盤安全鎖

系統動作風險等級分類與強制執行政策。
"""

import os
from pathlib import Path
from typing import Optional

from core.action_risk import RiskLevel, ActionPolicyDecision
from core.season_state import load_season_state

# 常數定義
LIVE_TOKEN_PATH = Path("outputs/live_enable.token")
LIVE_TOKEN_MAGIC = "ALLOW_LIVE_EXECUTE"

# 動作白名單（硬編碼）
READ_ONLY = {
    "view_history",
    "list_jobs",
    "get_job_status",
    "get_artifacts",
    "health",
    "list_datasets",
    "list_strategies",
    "get_job",
    "list_recent_jobs",
    "get_rolling_summary",
    "get_season_report",
    "list_chart_artifacts",
    "load_chart_artifact",
    "get_jobs_for_deploy",
    "get_system_settings",
}

RESEARCH_MUTATE = {
    "submit_job",
    "run_job",
    "build_portfolio",
    "archive",
    "export",
    "freeze_season",
    "unfreeze_season",
    "generate_deploy_zip",
    "update_system_settings",
}

LIVE_EXECUTE = {
    "deploy_live",
    "send_orders",
    "broker_connect",
    "promote_to_live",
}


def classify_action(action: str) -> RiskLevel:
    """分類動作風險等級
    
    Args:
        action: 動作名稱
        
    Returns:
        RiskLevel: 風險等級
        
    Note:
        未知動作一律視為 LIVE_EXECUTE（fail-safe）
    """
    if action in READ_ONLY:
        return RiskLevel.READ_ONLY
    if action in RESEARCH_MUTATE:
        return RiskLevel.RESEARCH_MUTATE
    if action in LIVE_EXECUTE:
        return RiskLevel.LIVE_EXECUTE
    # 未知動作：fail-safe，視為最高風險
    return RiskLevel.LIVE_EXECUTE


def enforce_action_policy(action: str, season: Optional[str] = None) -> ActionPolicyDecision:
    """強制執行動作政策
    
    Args:
        action: 動作名稱
        season: 季節識別碼（可選）
        
    Returns:
        ActionPolicyDecision: 政策決策結果
    """
    risk = classify_action(action)

    # LIVE_EXECUTE: 需要雙重驗證（env + token）
    if risk == RiskLevel.LIVE_EXECUTE:
        if os.getenv("FISHBRO_ENABLE_LIVE") != "1":
            return ActionPolicyDecision(
                allowed=False,
                reason="LIVE_EXECUTE disabled: set FISHBRO_ENABLE_LIVE=1",
                risk=risk,
                action=action,
                season=season,
            )
        if not LIVE_TOKEN_PATH.exists():
            return ActionPolicyDecision(
                allowed=False,
                reason=f"LIVE_EXECUTE disabled: missing token {LIVE_TOKEN_PATH}",
                risk=risk,
                action=action,
                season=season,
            )
        try:
            token_content = LIVE_TOKEN_PATH.read_text(encoding="utf-8").strip()
            if token_content != LIVE_TOKEN_MAGIC:
                return ActionPolicyDecision(
                    allowed=False,
                    reason="LIVE_EXECUTE disabled: invalid token content",
                    risk=risk,
                    action=action,
                    season=season,
                )
        except Exception:
            return ActionPolicyDecision(
                allowed=False,
                reason="LIVE_EXECUTE disabled: cannot read token file",
                risk=risk,
                action=action,
                season=season,
            )
        return ActionPolicyDecision(
            allowed=True,
            reason="LIVE_EXECUTE enabled",
            risk=risk,
            action=action,
            season=season,
        )

    # RESEARCH_MUTATE: 檢查季節是否凍結
    if risk == RiskLevel.RESEARCH_MUTATE and season:
        try:
            state = load_season_state(season)
            if state.is_frozen():
                return ActionPolicyDecision(
                    allowed=False,
                    reason=f"Season {season} is frozen",
                    risk=risk,
                    action=action,
                    season=season,
                )
        except Exception:
            # 如果載入狀態失敗，假設季節未凍結（安全側）
            pass

    # READ_ONLY 或允許的 RESEARCH_MUTATE
    return ActionPolicyDecision(
        allowed=True,
        reason="OK",
        risk=risk,
        action=action,
        season=season,
    )