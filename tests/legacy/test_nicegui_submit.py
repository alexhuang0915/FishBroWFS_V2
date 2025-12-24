#!/usr/bin/env python3
"""測試 NiceGUI new_job 頁面提交功能"""

import os
import sys
import pytest
from pathlib import Path

# Module-level integration marker
pytestmark = pytest.mark.integration

# 添加 src 到路徑
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ._integration_gate import require_integration, require_dashboard_health, require_control_api_health


def test_nicegui_api_imports():
    """測試 NiceGUI API 導入"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.nicegui.api import (
            JobSubmitRequest, JobRecord, submit_job, list_datasets, list_strategies
        )
        # 檢查類型
        assert JobSubmitRequest is not None
        assert JobRecord is not None
        assert callable(submit_job)
        assert callable(list_datasets)
        assert callable(list_strategies)
    except Exception as e:
        pytest.fail(f"NiceGUI API 導入失敗: {e}")


def test_list_datasets_and_strategies():
    """測試 datasets 和 strategies 列表功能"""
    # 需要 Control API 和 dashboard
    require_dashboard_health()
    require_control_api_health()
    
    from src.FishBroWFS_V2.gui.nicegui.api import list_datasets, list_strategies

    # 測試 datasets
    datasets = list_datasets(Path("outputs"))
    assert isinstance(datasets, list)

    # 測試 strategies
    strategies = list_strategies()
    assert isinstance(strategies, list)


def test_job_submit_request_structure():
    """測試 JobSubmitRequest 結構"""
    require_integration()
    
    try:
        from src.FishBroWFS_V2.gui.nicegui.api import JobSubmitRequest
        from pathlib import Path

        # 建立一個範例請求
        req = JobSubmitRequest(
            outputs_root=Path("outputs"),
            dataset_id="test_dataset",
            symbols=["ES"],
            timeframe_min=5,
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
            season="2026Q1",
        )

        # 檢查屬性
        assert req.dataset_id == "test_dataset"
        assert req.symbols == ["ES"]
        assert req.timeframe_min == 5
        assert req.strategy_name == "test_strategy"
        assert req.train_years == 3
        assert req.test_unit == "quarter"
        assert req.season == "2026Q1"

    except Exception as e:
        pytest.fail(f"JobSubmitRequest 結構測試失敗: {e}")


def test_api_health():
    """測試 API 健康狀態"""
    # 需要 dashboard
    require_dashboard_health()
    
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
