
#!/usr/bin/env python3
"""測試 NiceGUI new_job 頁面提交功能"""

import sys
from pathlib import Path

# 添加 src 到路徑
sys.path.insert(0, str(Path(__file__).parent / "src"))

from FishBroWFS_V2.gui.nicegui.api import (
    JobSubmitRequest,
    list_datasets,
    list_strategies,
    submit_job
)

def test_submit_job():
    """測試任務提交功能"""
    print("=== 測試 NiceGUI new_job 頁面提交功能 ===")
    
    # 1. 檢查 datasets
    print("\n1. 檢查 datasets...")
    try:
        datasets = list_datasets(Path("outputs"))
        print(f"  找到 {len(datasets)} 個 datasets: {datasets}")
    except Exception as e:
        print(f"  錯誤: {e}")
        return False
    
    # 2. 檢查 strategies
    print("\n2. 檢查 strategies...")
    try:
        strategies = list_strategies()
        print(f"  找到 {len(strategies)} 個 strategies: {strategies}")
    except Exception as e:
        print(f"  錯誤: {e}")
        return False
    
    if not datasets or not strategies:
        print("  缺少 datasets 或 strategies，跳過提交測試")
        return True
    
    # 3. 測試提交任務
    print("\n3. 測試提交任務...")
    try:
        req = JobSubmitRequest(
            outputs_root=Path("outputs"),
            dataset_id=datasets[0],
            symbols=["MNQ", "MES", "MXF"],
            timeframe_min=60,
            strategy_name=strategies[0],
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
        
        print(f"  提交請求: dataset={req.dataset_id}, strategy={req.strategy_name}")
        job_record = submit_job(req)
        
        print(f"  成功! job_id: {job_record.job_id}")
        print(f"  狀態: {job_record.status}")
        print(f"  訊息: {job_record.message}")
        
        return True
        
    except Exception as e:
        print(f"  提交失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_health():
    """測試 API 健康狀態"""
    print("\n=== 測試 API 健康狀態 ===")
    
    # 測試 Control API
    import requests
    try:
        resp = requests.get("http://127.0.0.1:8000/health", timeout=5)
        print(f"Control API: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"Control API 錯誤: {e}")
        return False
    
    # 測試 NiceGUI
    try:
        resp = requests.get("http://localhost:8080/health", timeout=5)
        print(f"NiceGUI: {resp.status_code} - 可訪問")
    except Exception as e:
        print(f"NiceGUI 錯誤: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("開始測試 NiceGUI new_job 頁面提交功能...")
    
    # 測試 API 健康狀態
    if not test_api_health():
        print("\n⚠️  API 健康狀態測試失敗，但繼續測試提交功能...")
    
    # 測試提交功能
    success = test_submit_job()
    
    if success:
        print("\n✅ 測試成功！NiceGUI new_job 頁面提交功能正常")
        sys.exit(0)
    else:
        print("\n❌ 測試失敗！需要檢查問題")
        sys.exit(1)


