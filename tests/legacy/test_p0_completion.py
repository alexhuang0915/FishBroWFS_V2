#!/usr/bin/env python3
"""最終測試 - 驗證 P0 任務完成"""

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


def test_p0_files_exist():
    """測試 P0 相關檔案是否存在"""
    # 檢查 GUI 服務檔案
    services_dir = project_root / "src/FishBroWFS_V2/gui/services"
    
    expected_files = [
        "theme.py",
        "runs_index.py",
        "archive.py",
        "clone.py",
        "path_picker.py",
        "log_tail.py",
        "stale.py",
        "command_builder.py",
    ]
    
    for filename in expected_files:
        file_path = services_dir / filename
        assert file_path.exists(), f"P0 檔案不存在: {file_path}"


def test_gui_layout_files_exist():
    """測試 GUI 佈局檔案是否存在"""
    # 檢查佈局檔案
    layout_dir = project_root / "src/FishBroWFS_V2/gui/nicegui"
    
    expected_files = [
        "app.py",
        "layout.py",
    ]
    
    for filename in expected_files:
        file_path = layout_dir / filename
        assert file_path.exists(), f"GUI 佈局檔案不存在: {file_path}"


def test_p0_pages_exist():
    """測試 P0 頁面檔案是否存在"""
    # 檢查頁面檔案
    pages_dir = project_root / "src/FishBroWFS_V2/gui/nicegui/pages"
    
    expected_files = [
        "history.py",
    ]
    
    for filename in expected_files:
        file_path = pages_dir / filename
        assert file_path.exists(), f"P0 頁面檔案不存在: {file_path}"


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