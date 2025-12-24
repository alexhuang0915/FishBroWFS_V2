#!/usr/bin/env python3
"""測試 NiceGUI new_job 頁面提交功能"""

import os
import sys
import pytest
from pathlib import Path

# Module-level integration marker
pytestmark = pytest.mark.integration

# Skip entire module if integration flag not set
if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":
    pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1", allow_module_level=True)

# 添加 src 到路徑
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_nicegui_api_imports():
    """測試 NiceGUI API 導入"""
    try:
        from FishBroWFS_V2.gui.nicegui.api import (
            JobSubmitRequest,
            list_datasets,
            list_strategies,
            submit_job
        )
        
        # 檢查類別和函數是否存在
        assert JobSubmitRequest is not None
        assert callable(list_datasets)
        assert callable(list_strategies)
        assert callable(submit_job)
        
    except Exception as e:
        pytest.fail(f"NiceGUI API 導入失敗: {e}")


def test_list_datasets_and_strategies():
    """測試 datasets 和 strategies 列表功能"""
    try:
        from FishBroWFS_V2.gui.nicegui.api import list_datasets, list_strategies
        
        # 測試 datasets
        datasets = list_datasets(Path("outputs"))
        assert isinstance(datasets, list)
        
        # 測試 strategies
        strategies = list_strategies()
        assert isinstance(strategies, list)
        
    except Exception as e:
        pytest.fail(f"datasets/strategies 列表測試失敗: {e}")


def test_job_submit_request_structure():
    """測試 JobSubmitRequest 結構"""
    try:
        from FishBroWFS_V2.gui.nicegui.api import JobSubmitRequest
        from pathlib import Path
        
        # 建立請求物件
        req = JobSubmitRequest(
            outputs_root=Path("outputs"),
            dataset_id="test_dataset",
            symbols=["MNQ", "MES", "MXF"],
            timeframe_min=60,
            strategy_name="test_strategy",
            data2_feed=None,
            rolling=True,
            train_years=3,
            test_unit="quarter",
            enable_slippage_stress=True,
            slippage_levels=["S0", "S1", "S2", "S3"],
            gate_level="S2",
            stress_level="S3",
            topk=20,
            season="2026Q1"
        )
        
        # 檢查屬性
        assert req.dataset_id == "test_dataset"
        assert req.strategy_name == "test_strategy"
        assert req.symbols == ["MNQ", "MES", "MXF"]
        assert req.timeframe_min == 60
        assert req.season == "2026Q1"
        
    except Exception as e:
        pytest.fail(f"JobSubmitRequest 結構測試失敗: {e}")


def test_api_health():
    """測試 API 健康狀態"""
    import requests
    
    # 測試 Control API (如果運行中)
    try:
        resp = requests.get("http://127.0.0.1:8000/health", timeout=2)
        # 如果成功，檢查狀態碼
        assert resp.status_code == 200
    except requests.exceptions.ConnectionError:
        # 如果 API 未運行，跳過此測試部分
        pass
    except Exception as e:
        pytest.fail(f"Control API 健康檢查失敗: {e}")
    
    # 測試 NiceGUI (如果運行中)
    try:
        resp = requests.get("http://localhost:8080/health", timeout=2)
        # 如果成功，檢查狀態碼
        assert resp.status_code == 200
    except requests.exceptions.ConnectionError:
        # 如果 NiceGUI 未運行，跳過此測試部分
        pass
    except Exception as e:
        pytest.fail(f"NiceGUI 健康檢查失敗: {e}")


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
