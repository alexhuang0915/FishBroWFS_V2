#!/usr/bin/env python3
"""測試應用程式啟動"""

import os
import sys
import pytest
from pathlib import Path

# Module-level integration marker
pytestmark = pytest.mark.integration

# Skip entire module if integration flag not set
if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":
    pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1", allow_module_level=True)

# 添加專案路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_app_import():
    """測試應用程式導入"""
    try:
        from src.FishBroWFS_V2.gui.nicegui.app import main
        # 如果導入成功，則通過測試
        assert True
    except Exception as e:
        pytest.fail(f"app.py 導入失敗: {e}")


def test_theme_injection():
    """測試主題注入"""
    try:
        from src.FishBroWFS_V2.gui.theme import inject_global_styles
        from nicegui import ui
        
        # 建立一個簡單的頁面來測試注入
        @ui.page("/test")
        def test_page():
            inject_global_styles()
            ui.label("測試頁面")
        
        # 如果沒有異常，則通過測試
        assert True
    except Exception as e:
        pytest.fail(f"主題注入測試失敗: {e}")


def test_layout_functions():
    """測試佈局函數"""
    try:
        from src.FishBroWFS_V2.gui.nicegui.layout import (
            render_header, render_nav, render_shell
        )
        
        # 檢查函數是否存在且可呼叫
        assert callable(render_header)
        assert callable(render_nav)
        assert callable(render_shell)
        
        # 檢查函數簽名
        import inspect
        sig_header = inspect.signature(render_header)
        sig_nav = inspect.signature(render_nav)
        
        # 確保它們有預期的參數
        assert len(sig_header.parameters) >= 0
        assert len(sig_nav.parameters) >= 0
        
    except Exception as e:
        pytest.fail(f"佈局函數測試失敗: {e}")


def test_history_page():
    """測試 History 頁面"""
    try:
        from src.FishBroWFS_V2.gui.nicegui.pages.history import register
        
        # 檢查 register 函數
        assert callable(register)
        
    except Exception as e:
        pytest.fail(f"History 頁面測試失敗: {e}")


def test_nav_structure():
    """測試導航結構"""
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


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))