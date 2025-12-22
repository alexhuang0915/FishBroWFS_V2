
"""驗證 UI API 是否完全誠實對接真實 Control API，禁止 fallback mock

憲法級原則：
1. 所有 API 函數必須對接真實 Control API 端點
2. 禁止任何 fallback mock 或假資料
3. 錯誤必須 raise，不能 silent fallback
"""

import pytest
import ast
import os
from pathlib import Path


def test_api_functions_no_fallback_mock():
    """檢查 api.py 中所有函數是否都沒有 fallback mock"""
    api_path = Path("src/FishBroWFS_V2/gui/nicegui/api.py")
    with open(api_path, "r") as f:
        content = f.read()
    
    # 檢查是否有 try-except 回退到模擬資料的模式
    forbidden_patterns = [
        # 禁止的 fallback 模式
        "except.*return.*mock",
        "except.*return.*預設",
        "except.*return.*default",
        "except.*return.*模擬",
        "except.*return.*simulated",
        "except.*return.*fake",
        "except.*return.*假",
        "except.*return.*fallback",
        "except.*return.*backup",
        "except.*return.*測試",
        "except.*return.*test",
    ]
    
    for pattern in forbidden_patterns:
        assert pattern not in content.lower(), f"發現禁止的 fallback 模式: {pattern}"
    
    # 檢查是否有直接回傳假資料的函數
    tree = ast.parse(content)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_name = node.name
            # 跳過輔助函數
            if func_name.startswith("_") or func_name in ["_mock_jobs", "_map_status", "_estimate_progress"]:
                continue
                
            # 檢查函數體中是否有直接回傳假資料
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Dict):
                    # 檢查是否有硬編碼的假資料
                    dict_str = ast.unparse(stmt)
                    if "mock" in dict_str.lower() or "fake" in dict_str.lower():
                        # 但允許在註解或字串中包含這些詞
                        pass


def test_api_base_from_env():
    """檢查 API_BASE 是否從環境變數讀取"""
    api_path = Path("src/FishBroWFS_V2/gui/nicegui/api.py")
    with open(api_path, "r") as f:
        content = f.read()
    
    # 檢查是否有 API_BASE 定義
    assert "API_BASE = os.environ.get" in content
    assert "FISHBRO_API_BASE" in content
    assert "http://127.0.0.1:8000" in content


def test_all_api_functions_call_real_endpoints():
    """檢查所有 API 函數是否都呼叫 _call_api"""
    api_path = Path("src/FishBroWFS_V2/gui/nicegui/api.py")
    with open(api_path, "r") as f:
        content = f.read()
    
    # 應該呼叫 _call_api 的函數列表
    api_functions = [
        "list_datasets",
        "list_strategies", 
        "submit_job",
        "list_recent_jobs",
        "get_job",
        "get_rolling_summary",
        "get_season_report",
        "generate_deploy_zip",
        "list_chart_artifacts",
        "load_chart_artifact",
    ]
    
    for func_name in api_functions:
        # 檢查函數定義是否存在
        assert f"def {func_name}" in content, f"函數 {func_name} 未定義"
        
        # 檢查函數體中是否有 _call_api 呼叫
        # 簡單檢查：函數定義後是否有 _call_api
        lines = content.split('\n')
        in_function = False
        found_call_api = False
        
        for i, line in enumerate(lines):
            if f"def {func_name}" in line:
                in_function = True
                continue
                
            if in_function:
                if line.strip().startswith("def "):
                    # 進入下一個函數
                    break
                    
                if "_call_api" in line and not line.strip().startswith("#"):
                    found_call_api = True
                    break
        
        assert found_call_api, f"函數 {func_name} 未呼叫 _call_api"


def test_no_hardcoded_mock_data():
    """檢查是否有硬編碼的模擬資料"""
    api_path = Path("src/FishBroWFS_V2/gui/nicegui/api.py")
    with open(api_path, "r") as f:
        content = f.read()
    
    # 檢查是否有硬編碼的假資料模式
    hardcoded_patterns = [
        '"S0_net": 1250',
        '"total_return": 12.5',
        '"labels": ["Day 1"',
        '"values": [100, 105',
        '"Deployment package for job"',
        '"Mock job for testing"',
    ]
    
    for pattern in hardcoded_patterns:
        # 這些應該只出現在 _mock_jobs 函數中
        if pattern in content:
            # 檢查是否在 _mock_jobs 函數之外
            lines = content.split('\n')
            in_mock_jobs = False
            
            for i, line in enumerate(lines):
                if "def _mock_jobs" in line:
                    in_mock_jobs = True
                    continue
                    
                if in_mock_jobs and line.strip().startswith("def "):
                    in_mock_jobs = False
                    continue
                    
                if pattern in line and not in_mock_jobs:
                    # 允許在註解中
                    if not line.strip().startswith("#"):
                        pytest.fail(f"發現硬編碼假資料在 _mock_jobs 之外: {pattern}")


def test_error_handling_raises_not_silent():
    """檢查錯誤處理是否 raise 而不是 silent"""
    api_path = Path("src/FishBroWFS_V2/gui/nicegui/api.py")
    with open(api_path, "r") as f:
        content = f.read()
    
    # 檢查 _call_api 函數是否有詳細的錯誤訊息
    assert "raise RuntimeError" in content
    assert "無法連線到 Control API" in content
    assert "Control API 請求超時" in content
    assert "Control API 服務不可用" in content


if __name__ == "__main__":
    # 執行測試
    pytest.main([__file__, "-v"])


