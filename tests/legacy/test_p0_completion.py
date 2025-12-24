#!/usr/bin/env python3
"""最終測試 - 驗證 P0 任務完成"""

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


def test_p0_files_exist():
    """測試 P0 相關檔案是否存在"""
    require_integration()
    
    # 檢查關鍵檔案
    required_files = [
        "src/FishBroWFS_V2/gui/nicegui/pages/dashboard.py",
        "src/FishBroWFS_V2/gui/nicegui/pages/wizard.py",
        "src/FishBroWFS_V2/gui/nicegui/pages/history.py",
        "src/FishBroWFS_V2/gui/nicegui/pages/candidates.py",
        "src/FishBroWFS_V2/gui/nicegui/pages/portfolio.py",
        "src/FishBroWFS_V2/gui/nicegui/pages/deploy.py",
        "src/FishBroWFS_V2/gui/nicegui/pages/settings.py",
        "src/FishBroWFS_V2/gui/nicegui/layout.py",
        "src/FishBroWFS_V2/gui/nicegui/api.py",
    ]
    
    for file_path in required_files:
        full_path = project_root / file_path
        assert full_path.exists(), f"檔案不存在: {file_path}"


def test_gui_layout_files_exist():
    """測試 GUI 佈局檔案"""
    require_integration()
    
    # 檢查佈局檔案
    layout_files = [
        "src/FishBroWFS_V2/gui/nicegui/layout.py",
        "src/FishBroWFS_V2/gui/nicegui/__init__.py",
    ]
    
    for file_path in layout_files:
        full_path = project_root / file_path
        assert full_path.exists(), f"佈局檔案不存在: {file_path}"


def test_p0_pages_exist():
    """測試 P0 頁面存在"""
    require_integration()
    
    try:
        # 嘗試導入頁面模組
        from src.FishBroWFS_V2.gui.nicegui.pages import (
            dashboard, wizard, history, candidates, portfolio, deploy, settings
        )
        
        # 檢查模組是否可訪問
        assert dashboard is not None
        assert wizard is not None
        assert history is not None
        assert candidates is not None
        assert portfolio is not None
        assert deploy is not None
        assert settings is not None
        
    except Exception as e:
        pytest.fail(f"頁面導入失敗: {e}")


def test_nav_structure():
    """測試導航結構"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.nicegui.layout import NAV
        
        expected_nav = [
            ("Dashboard", "/"),
            ("Wizard", "/wizard"),
            ("History", "/history"),
            ("Candidates", "/candidates"),
            ("Portfolio", "/portfolio"),
            ("Deploy", "/deploy"),
            ("Settings", "/settings"),
        ]
        
        # 檢查 NAV 長度
        assert len(NAV) == len(expected_nav), f"NAV 長度不正確: 預期 {len(expected_nav)}，實際 {len(NAV)}"
        
        # 檢查項目
        for i, (expected_name, expected_path) in enumerate(expected_nav):
            actual_name, actual_path = NAV[i]
            assert actual_name == expected_name, f"項目 {i} 名稱不匹配: 預期 {expected_name}，實際 {actual_name}"
            assert actual_path == expected_path, f"項目 {i} 路徑不匹配: 預期 {expected_path}，實際 {actual_path}"
        
    except Exception as e:
        pytest.fail(f"導航結構測試失敗: {e}")


def test_api_functions():
    """測試 API 函數"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.nicegui.api import (
            get_jobs_for_deploy,
            get_system_settings,
            list_datasets,
            list_strategies,
            submit_job,
        )
        
        # 檢查函數是否存在
        assert callable(get_jobs_for_deploy)
        assert callable(get_system_settings)
        assert callable(list_datasets)
        assert callable(list_strategies)
        assert callable(submit_job)
        
    except Exception as e:
        pytest.fail(f"API 函數測試失敗: {e}")


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))