#!/usr/bin/env python3
"""測試 NiceGUI 應用程式啟動"""

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


def test_nicegui_import():
    """測試 NiceGUI 導入"""
    require_integration()
    
    try:
        # 測試導入 NiceGUI 模組
        import nicegui
        assert nicegui is not None
        
        # 測試導入我們的應用程式模組
        from src.FishBroWFS_V2.gui.nicegui import app
        assert app is not None
        
    except Exception as e:
        pytest.fail(f"NiceGUI 導入失敗: {e}")


def test_nicegui_app_structure():
    """測試 NiceGUI 應用程式結構"""
    require_integration()
    
    try:
        # 導入應用程式模組
        import src.FishBroWFS_V2.gui.nicegui.app as app_module
        
        # 檢查必要的屬性
        assert hasattr(app_module, 'main')
        assert callable(app_module.main)
        
        # 檢查是否有 ui 物件（NiceGUI 應用程式）
        if hasattr(app_module, 'ui'):
            ui = app_module.ui
            # ui 應該是一個 NiceGUI 應用程式實例
            assert hasattr(ui, 'run')
        
    except Exception as e:
        pytest.fail(f"NiceGUI 應用程式結構測試失敗: {e}")


def test_nicegui_pages():
    """測試 NiceGUI 頁面"""
    require_integration()
    
    try:
        # 測試頁面模組導入
        from src.FishBroWFS_V2.gui.nicegui.pages import (
            dashboard, wizard, history, candidates, portfolio, deploy, settings
        )
        
        # 檢查頁面模組是否可訪問
        assert dashboard is not None
        assert wizard is not None
        assert history is not None
        assert candidates is not None
        assert portfolio is not None
        assert deploy is not None
        assert settings is not None
        
    except Exception as e:
        pytest.fail(f"NiceGUI 頁面測試失敗: {e}")


def test_nicegui_layout():
    """測試 NiceGUI 佈局"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.nicegui.layout import NAV, create_navbar
        
        # 檢查 NAV 常數
        assert isinstance(NAV, list)
        assert len(NAV) > 0
        
        # 檢查導航欄函數
        assert callable(create_navbar)
        
    except Exception as e:
        pytest.fail(f"NiceGUI 佈局測試失敗: {e}")


def test_nicegui_api():
    """測試 NiceGUI API"""
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
        pytest.fail(f"NiceGUI API 測試失敗: {e}")


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
