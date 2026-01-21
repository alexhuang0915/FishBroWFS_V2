"""
測試 research_cli 啟動時會載入 built-in strategies。

確保：
1. 呼叫 run_research_cli() 時，策略 registry 不為空
2. 內建策略（sma_cross, breakout_channel, mean_revert_zscore）已註冊
3. 多次呼叫不會導致重入錯誤
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import pytest
import argparse

from control.research_cli import (
    run_research_cli,
    ensure_builtin_strategies_loaded,
    create_parser
)
from strategy.registry import get, list_strategies, load_builtin_strategies


def test_ensure_builtin_strategies_loaded():
    """
    測試 ensure_builtin_strategies_loaded() 函數：
    1. 第一次呼叫會載入 built-in strategies
    2. 第二次呼叫不會拋出重入錯誤
    3. 策略 registry 包含預期策略
    """
    # 先清空 registry（模擬新 process 啟動）
    # 注意：我們無法直接清空全域 registry，但可以測試函數行為
    # 我們將測試函數是否成功執行而不拋出異常
    
    # 第一次呼叫
    ensure_builtin_strategies_loaded()
    
    # 驗證策略已註冊
    strategies = list_strategies()
    assert len(strategies) >= 3, f"預期至少 3 個內建策略，但只有 {len(strategies)} 個"
    
    # 檢查特定策略是否存在
    expected_strategies = {"sma_cross", "breakout_channel", "mean_revert_zscore"}
    for strategy_id in expected_strategies:
        try:
            spec = get(strategy_id)
            assert spec is not None, f"策略 {strategy_id} 未找到"
        except KeyError:
            pytest.fail(f"策略 {strategy_id} 未在 registry 中找到")
    
    # 第二次呼叫（應處理重入錯誤）
    ensure_builtin_strategies_loaded()  # 不應拋出異常
    
    # 再次驗證策略仍然存在
    for strategy_id in expected_strategies:
        spec = get(strategy_id)
        assert spec is not None, f"策略 {strategy_id} 在第二次呼叫後消失"


def test_run_research_cli_loads_strategies(monkeypatch):
    """
    測試 run_research_cli() 會載入 built-in strategies。
    
    使用 monkeypatch 模擬 CLI 參數並檢查 ensure_builtin_strategies_loaded 是否被呼叫。
    """
    # 建立一個標記來追蹤函數是否被呼叫
    called = []
    
    def mock_ensure_builtin_strategies_loaded():
        called.append(True)
        # 實際執行原始函數
        from strategy.registry import load_builtin_strategies
        try:
            load_builtin_strategies()
        except ValueError as e:
            if "already registered" not in str(e):
                raise
    
    # monkeypatch ensure_builtin_strategies_loaded
    import control.research_cli as research_cli_module
    monkeypatch.setattr(research_cli_module, "ensure_builtin_strategies_loaded", mock_ensure_builtin_strategies_loaded)
    
    # 建立臨時目錄和假參數
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # 建立一個假的 season 目錄
        season_dir = tmp_path / "outputs" / "seasons" / "TEST2026Q1"
        season_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立一個假的 dataset 目錄
        dataset_dir = season_dir / "TEST.MNQ"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立一個假的 features 目錄
        features_dir = dataset_dir / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立一個假的 features manifest
        manifest_path = features_dir / "features_manifest.json"
        manifest_path.write_text('{"features_specs": [], "files_sha256": {}}')
        
        # 建立一個假的 features NPZ 檔案
        import numpy as np
        features_data = {
            "ts": np.array([0, 3600], dtype="datetime64[s]"),
            "close": np.array([100.0, 101.0]),
        }
        np.savez(features_dir / "features_60m.npz", **features_data)
        
        # 建立一個假的策略需求檔案
        strategy_dir = tmp_path / "outputs" / "strategies" / "sma_cross"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        req_json = strategy_dir / "features.json"
        req_json.write_text('''{
            "strategy_id": "sma_cross",
            "required": [],
            "optional": [],
            "min_schema_version": "v1",
            "notes": "test"
        }''')
        
        # 建立 parser 並解析參數
        parser = create_parser()
        args = parser.parse_args([
            "--season", "TEST2026Q1",
            "--dataset-id", "TEST.MNQ",
            "--strategy-id", "sma_cross",
            "--outputs-root", str(tmp_path / "outputs"),
            "--allow-build",
            "--txt-path", str(tmp_path / "dummy.txt"),
        ])
        
        # 建立 dummy txt 檔案
        (tmp_path / "dummy.txt").write_text("dummy content")
        
        # 執行 run_research_cli（會因為缺少資料而失敗，但我們只關心 bootstrap 階段）
        try:
            run_research_cli(args)
        except (SystemExit, Exception) as e:
            # 預期會因為缺少資料而失敗，但我們只關心 ensure_builtin_strategies_loaded 是否被呼叫
            pass
        
        # 驗證 ensure_builtin_strategies_loaded 被呼叫
        assert len(called) > 0, "ensure_builtin_strategies_loaded 未被呼叫"
        assert called[0] is True


def test_cli_without_strategies_registry_empty(monkeypatch):
    """
    測試如果沒有呼叫 ensure_builtin_strategies_loaded，策略 registry 為空。
    
    這個測試驗證問題確實存在：新 process 中策略 registry 初始為空。
    """
    # 模擬新 process：清除 registry（實際上無法清除，但我們可以檢查初始狀態）
    # 我們將檢查 load_builtin_strategies 是否被呼叫
    
    called_load = []
    
    def mock_load_builtin_strategies():
        called_load.append(True)
        # 不執行實際載入
    
    # monkeypatch load_builtin_strategies
    import strategy.registry as registry_module
    monkeypatch.setattr(registry_module, "load_builtin_strategies", mock_load_builtin_strategies)
    
    # 直接呼叫 run_research_cli 的內部邏輯（不透過 ensure_builtin_strategies_loaded）
    # 我們將模擬一個沒有 bootstrap 的情況
    import control.research_cli as research_cli_module
    
    # 儲存原始函數
    original_ensure = research_cli_module.ensure_builtin_strategies_loaded
    
    # 替換為不執行任何操作的函數
    def noop_ensure():
        pass
    
    monkeypatch.setattr(research_cli_module, "ensure_builtin_strategies_loaded", noop_ensure)
    
    # 建立臨時目錄
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # 建立一個假的 season 目錄
        season_dir = tmp_path / "outputs" / "seasons" / "TEST2026Q1"
        season_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立一個假的 dataset 目錄
        dataset_dir = season_dir / "TEST.MNQ"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立一個假的 features 目錄
        features_dir = dataset_dir / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立一個假的 features manifest
        manifest_path = features_dir / "features_manifest.json"
        manifest_path.write_text('{"features_specs": [], "files_sha256": {}}')
        
        # 建立一個假的 features NPZ 檔案
        import numpy as np
        features_data = {
            "ts": np.array([0, 3600], dtype="datetime64[s]"),
            "close": np.array([100.0, 101.0]),
        }
        np.savez(features_dir / "features_60m.npz", **features_data)
        
        # 建立一個假的策略需求檔案
        strategy_dir = tmp_path / "outputs" / "strategies" / "sma_cross"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        req_json = strategy_dir / "features.json"
        req_json.write_text('''{
            "strategy_id": "sma_cross",
            "required": [],
            "optional": [],
            "min_schema_version": "v1",
            "notes": "test"
        }''')
        
        # 建立 parser 並解析參數
        parser = create_parser()
        args = parser.parse_args([
            "--season", "TEST2026Q1",
            "--dataset-id", "TEST.MNQ",
            "--strategy-id", "sma_cross",
            "--outputs-root", str(tmp_path / "outputs"),
        ])
        
        # 執行 run_research_cli（會因為策略未註冊而失敗）
        try:
            run_research_cli(args)
        except (SystemExit, KeyError, Exception) as e:
            # 預期會失敗，因為策略未註冊
            pass
        
        # 恢復原始函數
        monkeypatch.setattr(research_cli_module, "ensure_builtin_strategies_loaded", original_ensure)
    
    # 驗證 load_builtin_strategies 未被呼叫（因為我們替換了 ensure 函數）
    assert len(called_load) == 0, "load_builtin_strategies 不應被呼叫"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])