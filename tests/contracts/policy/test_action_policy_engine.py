"""Unit tests for action policy engine (M4)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.action_risk import RiskLevel, ActionPolicyDecision
from core.policy_engine import (
    classify_action,
    enforce_action_policy,
    LIVE_TOKEN_PATH,
    LIVE_TOKEN_MAGIC,
)


def test_classify_action_read_only():
    """測試 READ_ONLY 動作分類"""
    assert classify_action("view_history") == RiskLevel.READ_ONLY
    assert classify_action("list_jobs") == RiskLevel.READ_ONLY
    assert classify_action("health") == RiskLevel.READ_ONLY
    assert classify_action("get_artifacts") == RiskLevel.READ_ONLY


def test_classify_action_research_mutate():
    """測試 RESEARCH_MUTATE 動作分類"""
    assert classify_action("submit_job") == RiskLevel.RESEARCH_MUTATE
    assert classify_action("run_job") == RiskLevel.RESEARCH_MUTATE
    assert classify_action("build_portfolio") == RiskLevel.RESEARCH_MUTATE
    assert classify_action("archive") == RiskLevel.RESEARCH_MUTATE


def test_classify_action_live_execute():
    """測試 LIVE_EXECUTE 動作分類"""
    assert classify_action("deploy_live") == RiskLevel.LIVE_EXECUTE
    assert classify_action("send_orders") == RiskLevel.LIVE_EXECUTE
    assert classify_action("broker_connect") == RiskLevel.LIVE_EXECUTE
    assert classify_action("promote_to_live") == RiskLevel.LIVE_EXECUTE


def test_classify_action_unknown_fail_safe():
    """測試未知動作的 fail-safe 分類（應視為 LIVE_EXECUTE）"""
    assert classify_action("unknown_action") == RiskLevel.LIVE_EXECUTE
    assert classify_action("some_random_action") == RiskLevel.LIVE_EXECUTE


def test_enforce_action_policy_read_only_always_allowed():
    """測試 READ_ONLY 動作永遠允許"""
    decision = enforce_action_policy("view_history", "2026Q1")
    assert decision.allowed is True
    assert decision.reason == "OK"
    assert decision.risk == RiskLevel.READ_ONLY
    assert decision.action == "view_history"
    assert decision.season == "2026Q1"


def test_enforce_action_policy_live_execute_blocked_by_default():
    """測試 LIVE_EXECUTE 動作預設被阻擋（無環境變數）"""
    # 確保環境變數未設置
    if "FISHBRO_ENABLE_LIVE" in os.environ:
        del os.environ["FISHBRO_ENABLE_LIVE"]
    
    decision = enforce_action_policy("deploy_live", "2026Q1")
    assert decision.allowed is False
    assert "LIVE_EXECUTE disabled: set FISHBRO_ENABLE_LIVE=1" in decision.reason
    assert decision.risk == RiskLevel.LIVE_EXECUTE


def test_enforce_action_policy_live_execute_env_1_but_token_missing():
    """測試 LIVE_EXECUTE：環境變數=1 但 token 檔案不存在"""
    os.environ["FISHBRO_ENABLE_LIVE"] = "1"
    
    # 確保 token 檔案不存在
    if LIVE_TOKEN_PATH.exists():
        LIVE_TOKEN_PATH.unlink()
    
    decision = enforce_action_policy("deploy_live", "2026Q1")
    assert decision.allowed is False
    assert "missing token" in decision.reason
    assert decision.risk == RiskLevel.LIVE_EXECUTE
    
    # 清理環境變數
    del os.environ["FISHBRO_ENABLE_LIVE"]


def test_enforce_action_policy_live_execute_env_1_token_wrong():
    """測試 LIVE_EXECUTE：環境變數=1 但 token 內容錯誤"""
    os.environ["FISHBRO_ENABLE_LIVE"] = "1"
    
    # 建立錯誤內容的 token 檔案
    with tempfile.TemporaryDirectory() as tmpdir:
        token_path = Path(tmpdir) / "live_enable.token"
        token_path.write_text("WRONG_TOKEN", encoding="utf-8")
        
        with patch("core.policy_engine.LIVE_TOKEN_PATH", token_path):
            decision = enforce_action_policy("deploy_live", "2026Q1")
            assert decision.allowed is False
            assert "invalid token content" in decision.reason
            assert decision.risk == RiskLevel.LIVE_EXECUTE
    
    # 清理環境變數
    del os.environ["FISHBRO_ENABLE_LIVE"]


def test_enforce_action_policy_live_execute_env_1_token_ok():
    """測試 LIVE_EXECUTE：環境變數=1 且 token 正確"""
    os.environ["FISHBRO_ENABLE_LIVE"] = "1"
    
    # 建立正確內容的 token 檔案
    with tempfile.TemporaryDirectory() as tmpdir:
        token_path = Path(tmpdir) / "live_enable.token"
        token_path.write_text(LIVE_TOKEN_MAGIC, encoding="utf-8")
        
        with patch("core.policy_engine.LIVE_TOKEN_PATH", token_path):
            decision = enforce_action_policy("deploy_live", "2026Q1")
            assert decision.allowed is True
            assert "LIVE_EXECUTE enabled" in decision.reason
            assert decision.risk == RiskLevel.LIVE_EXECUTE
    
    # 清理環境變數
    del os.environ["FISHBRO_ENABLE_LIVE"]


def test_enforce_action_policy_research_mutate_frozen_season():
    """測試 RESEARCH_MUTATE 動作在凍結季節被阻擋"""
    # Mock load_season_state 返回凍結的 SeasonState
    from core.season_state import SeasonState
    frozen_state = SeasonState(season="2026Q1", state="FROZEN")
    
    with patch("core.policy_engine.load_season_state", return_value=frozen_state):
        decision = enforce_action_policy("submit_job", "2026Q1")
        assert decision.allowed is False
        assert "Season 2026Q1 is frozen" in decision.reason
        assert decision.risk == RiskLevel.RESEARCH_MUTATE


def test_enforce_action_policy_research_mutate_not_frozen():
    """測試 RESEARCH_MUTATE 動作在未凍結季節允許"""
    # Mock load_season_state 返回未凍結的 SeasonState
    from core.season_state import SeasonState
    open_state = SeasonState(season="2026Q1", state="OPEN")
    
    with patch("core.policy_engine.load_season_state", return_value=open_state):
        decision = enforce_action_policy("submit_job", "2026Q1")
        assert decision.allowed is True
        assert decision.reason == "OK"
        assert decision.risk == RiskLevel.RESEARCH_MUTATE


def test_enforce_action_policy_unknown_action_blocked():
    """測試未知動作被阻擋（fail-safe）"""
    # 確保環境變數未設置
    if "FISHBRO_ENABLE_LIVE" in os.environ:
        del os.environ["FISHBRO_ENABLE_LIVE"]
    
    decision = enforce_action_policy("unknown_action", "2026Q1")
    assert decision.allowed is False
    assert decision.risk == RiskLevel.LIVE_EXECUTE
    assert "LIVE_EXECUTE disabled" in decision.reason




if __name__ == "__main__":
    pytest.main([__file__, "-v"])