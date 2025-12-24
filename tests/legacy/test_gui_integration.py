#!/usr/bin/env python3
"""測試 GUI 整合"""

import os
import sys
import pytest
from pathlib import Path

# Module-level integration marker
pytestmark = pytest.mark.integration

# 添加專案路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ._integration_gate import require_integration


def test_gui_imports():
    """測試 GUI 相關導入"""
    require_integration()
    
    try:
        # 測試 GUI 服務導入
        from src.FishBroWFS_V2.gui.services import (
            command_builder,
            candidates_reader,
            audit_log,
            archive,
        )
        
        # 檢查模組是否存在
        assert command_builder is not None
        assert candidates_reader is not None
        assert audit_log is not None
        assert archive is not None
        
    except Exception as e:
        pytest.fail(f"GUI 導入測試失敗: {e}")


def test_runs_index():
    """測試 runs index 服務"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.services.runs_index import (
            list_runs,
            get_run_details,
        )
        
        # 檢查函數是否存在
        assert callable(list_runs)
        assert callable(get_run_details)
        
        # 測試 list_runs 返回列表
        runs = list_runs(Path("outputs"))
        assert isinstance(runs, list)
        
    except Exception as e:
        pytest.fail(f"Runs index 測試失敗: {e}")


def test_stale_service():
    """測試 stale 服務"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.services.stale import (
            mark_stale,
            get_stale_runs,
        )
        
        # 檢查函數是否存在
        assert callable(mark_stale)
        assert callable(get_stale_runs)
        
    except Exception as e:
        pytest.fail(f"Stale 服務測試失敗: {e}")


def test_command_builder():
    """測試 command builder 服務功能"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.services.command_builder import build_research_command
        
        snapshot = {
            "season": "2026Q1",
            "dataset_id": "test_dataset",
            "strategy_id": "test_strategy",
            "mode": "smoke",
            "note": "測試命令",
        }
        
        result = build_research_command(snapshot)
        # 檢查返回的物件有 shell 屬性
        assert hasattr(result, 'shell')
        assert isinstance(result.shell, str)
        
    except Exception as e:
        pytest.fail(f"Command builder 測試失敗: {e}")


def test_candidates_reader():
    """測試 candidates reader 服務"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.services.candidates_reader import (
            load_candidates,
            filter_candidates,
        )
        
        # 檢查函數是否存在
        assert callable(load_candidates)
        assert callable(filter_candidates)
        
    except Exception as e:
        pytest.fail(f"Candidates reader 測試失敗: {e}")


def test_audit_log():
    """測試 audit log 服務"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.services.audit_log import (
            log_action,
            get_recent_actions,
        )
        
        # 檢查函數是否存在
        assert callable(log_action)
        assert callable(get_recent_actions)
        
    except Exception as e:
        pytest.fail(f"Audit log 測試失敗: {e}")


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))