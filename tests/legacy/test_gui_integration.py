#!/usr/bin/env python3
"""測試 GUI 整合"""

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


def test_gui_imports():
    """測試所有必要的導入"""
    # 測試 theme.py 導入
    try:
        from src.FishBroWFS_V2.gui.theme import inject_global_styles
        assert callable(inject_global_styles)
    except Exception as e:
        pytest.fail(f"theme.py 導入失敗: {e}")
    
    # 測試 runs_index.py 導入
    try:
        from src.FishBroWFS_V2.gui.services.runs_index import RunsIndex, RunIndexRow
        assert RunsIndex is not None
    except Exception as e:
        pytest.fail(f"runs_index.py 導入失敗: {e}")
    
    # 測試 archive.py 導入
    try:
        from src.FishBroWFS_V2.gui.services.archive import archive_run
        assert callable(archive_run)
    except Exception as e:
        pytest.fail(f"archive.py 導入失敗: {e}")
    
    # 測試 clone.py 導入
    try:
        from src.FishBroWFS_V2.gui.services.clone import build_wizard_prefill
        assert callable(build_wizard_prefill)
    except Exception as e:
        pytest.fail(f"clone.py 導入失敗: {e}")
    
    # 測試 path_picker.py 導入
    try:
        from src.FishBroWFS_V2.gui.services.path_picker import list_txt_candidates
        assert callable(list_txt_candidates)
    except Exception as e:
        pytest.fail(f"path_picker.py 導入失敗: {e}")
    
    # 測試 log_tail.py 導入
    try:
        from src.FishBroWFS_V2.gui.services.log_tail import tail_lines
        assert callable(tail_lines)
    except Exception as e:
        pytest.fail(f"log_tail.py 導入失敗: {e}")
    
    # 測試 stale.py 導入
    try:
        from src.FishBroWFS_V2.gui.services.stale import should_warn_stale
        assert callable(should_warn_stale)
    except Exception as e:
        pytest.fail(f"stale.py 導入失敗: {e}")
    
    # 測試 command_builder.py 導入
    try:
        from src.FishBroWFS_V2.gui.services.command_builder import build_research_command
        assert callable(build_research_command)
    except Exception as e:
        pytest.fail(f"command_builder.py 導入失敗: {e}")


def test_runs_index():
    """測試 RunsIndex"""
    try:
        from src.FishBroWFS_V2.gui.services.runs_index import RunsIndex
        from pathlib import Path
        
        outputs_root = Path("outputs")
        index = RunsIndex(outputs_root, limit=5)
        index.build()
        
        runs = index.list()
        # 檢查返回的是列表
        assert isinstance(runs, list)
        
        # 如果有 runs，檢查結構
        if runs:
            run = runs[0]
            assert hasattr(run, 'run_id')
            assert hasattr(run, 'season')
        
    except Exception as e:
        pytest.fail(f"RunsIndex 測試失敗: {e}")


def test_stale_service():
    """測試 stale 服務功能"""
    try:
        from src.FishBroWFS_V2.gui.services.stale import StaleState, should_warn_stale
        import time
        
        # 測試超過 10 分鐘的情況
        state = StaleState(opened_at=time.time() - 700)  # 超過 10 分鐘
        should_warn = should_warn_stale(state)
        assert should_warn is True, f"超過 10 分鐘應警告，但 got {should_warn}"
        
        # 測試少於 10 分鐘的情況
        state2 = StaleState(opened_at=time.time() - 300)  # 5 分鐘
        should_warn2 = should_warn_stale(state2)
        assert should_warn2 is False, f"5 分鐘不應警告，但 got {should_warn2}"
        
    except Exception as e:
        pytest.fail(f"Stale 服務測試失敗: {e}")


def test_command_builder():
    """測試 command builder 服務功能"""
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


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))