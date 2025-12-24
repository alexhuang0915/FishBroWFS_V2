#!/usr/bin/env python3
"""測試 NiceGUI 應用程式啟動"""

import os
import sys
import pytest

# Module-level integration marker
pytestmark = pytest.mark.integration

# Skip entire module if integration flag not set
if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":
    pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def test_nicegui_import():
    """測試 NiceGUI 應用程式導入"""
    try:
        from FishBroWFS_V2.gui.nicegui.app import main
        # 檢查 main 函數是否存在且可呼叫
        assert callable(main)
    except Exception as e:
        pytest.fail(f"NiceGUI 應用程式導入失敗: {e}")


def test_nicegui_app_structure():
    """測試 NiceGUI 應用程式結構"""
    try:
        # 導入應用程式模組
        import FishBroWFS_V2.gui.nicegui.app as app_module
        
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


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
