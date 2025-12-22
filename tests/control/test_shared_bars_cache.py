
"""
Shared Bars Cache 測試

確保：
1. FULL build 產出完整 bars cache
2. INCREMENTAL append-only 與 FULL 結果一致
3. Safe point 跨 bar
4. Breaks 行為 deterministic
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
import numpy as np
import pandas as pd

from FishBroWFS_V2.control.shared_build import (
    BuildMode,
    IncrementalBuildRejected,
    build_shared,
)
from FishBroWFS_V2.control.bars_store import (
    normalized_bars_path,
    resampled_bars_path,
    load_npz,
)
from FishBroWFS_V2.control.bars_manifest import load_bars_manifest
from FishBroWFS_V2.data.raw_ingest import RawIngestResult, IngestPolicy
from FishBroWFS_V2.core.resampler import (
    SessionSpecTaipei,
    compute_safe_recompute_start,
)


def _create_mock_raw_ingest_result(
    txt_path: Path,
    bars: list[tuple[datetime, float, float, float, float, float]],
) -> RawIngestResult:
    """建立模擬的 RawIngestResult 用於測試"""
    # 建立 DataFrame
    rows = []
    for ts, o, h, l, c, v in bars:
        rows.append({
            "ts_str": ts.strftime("%Y/%m/%d %H:%M:%S"),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })
    
    df = pd.DataFrame(rows)
    
    return RawIngestResult(
        df=df,
        source_path=str(txt_path),
        rows=len(df),
        policy=IngestPolicy(),
    )


def _create_synthetic_minute_bars(
    start_date: datetime,
    num_days: int,
    bars_per_day: int = 390,  # 6.5 小時 * 60 分鐘
) -> list[tuple[datetime, float, float, float, float, float]]:
    """建立合成分鐘 bars"""
    bars = []
    current = start_date
    
    for day in range(num_days):
        day_start = current.replace(hour=9, minute=30, second=0) + timedelta(days=day)
        
        for i in range(bars_per_day):
            bar_time = day_start + timedelta(minutes=i)
            # 簡單的價格模式
            base_price = 100.0 + day * 0.1
            o = base_price + i * 0.01
            h = o + 0.05
            l = o - 0.03
            c = o + 0.02
            v = 1000.0 + i * 10
            
            bars.append((bar_time, o, h, l, c, v))
    
    return bars


def test_full_build_produces_bars_cache(tmp_path):
    """測試 FULL build 產出完整 bars cache"""
    # 建立測試 TXT 檔案（模擬）
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    # 建立合成資料（2 天）
    start_date = datetime(2023, 1, 1, 9, 30, 0)
    bars = _create_synthetic_minute_bars(start_date, num_days=2, bars_per_day=10)
    
    mock_result = _create_mock_raw_ingest_result(txt_file, bars)
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        # 執行 FULL 模式，啟用 bars cache
        report = build_shared(
            season="2026Q1",
            dataset_id="TEST.DATASET",
            txt_path=txt_file,
            outputs_root=tmp_path,
            mode="FULL",
            save_fingerprint=False,
            build_bars=True,
            tfs=[15, 30],  # 只測試兩個 timeframe 以加快速度
        )
    
    assert report["success"] == True
    assert report["mode"] == "FULL"
    assert report["build_bars"] == True
    
    # 檢查檔案是否存在
    norm_path = normalized_bars_path(tmp_path, "2026Q1", "TEST.DATASET")
    assert norm_path.exists()
    
    for tf in [15, 30]:
        resampled_path = resampled_bars_path(tmp_path, "2026Q1", "TEST.DATASET", tf)
        assert resampled_path.exists()
    
    # 檢查 bars manifest 存在
    bars_manifest_path = tmp_path / "shared" / "2026Q1" / "TEST.DATASET" / "bars" / "bars_manifest.json"
    assert bars_manifest_path.exists()
    
    # 載入並驗證 bars manifest
    bars_manifest = load_bars_manifest(bars_manifest_path)
    assert bars_manifest["season"] == "2026Q1"
    assert bars_manifest["dataset_id"] == "TEST.DATASET"
    assert bars_manifest["mode"] == "FULL"
    assert "manifest_sha256" in bars_manifest
    assert "files" in bars_manifest
    
    # 檢查 normalized bars 的結構
    norm_data = load_npz(norm_path)
    required_keys = {"ts", "open", "high", "low", "close", "volume"}
    assert required_keys.issubset(norm_data.keys())
    
    # 檢查時間戳記是遞增的
    ts = norm_data["ts"]
    assert len(ts) > 0
    assert np.all(np.diff(ts.astype("int64")) > 0)
    
    # 檢查 resampled bars
    for tf in [15, 30]:
        resampled_data = load_npz(
            resampled_bars_path(tmp_path, "2026Q1", "TEST.DATASET", tf)
        )
        assert required_keys.issubset(resampled_data.keys())
        assert len(resampled_data["ts"]) > 0


def test_incremental_append_only_consistent_with_full(tmp_path):
    """
    測試 INCREMENTAL append-only 與 FULL 結果一致
    
    用合成資料：
    base: 2020-01-01..2020-01-10 的 minute bars
    append: 2020-01-11..2020-01-12
    
    做兩條路徑：
    1. FULL（用 base+append 一次做）
    2. INCREMENTAL（先 base FULL，再 append INCREMENTAL）
    
    要求：產出的 resampled_*.npz 完全一致（arrays 必須逐元素一致）
    """
    # 建立 base 資料（10 天）
    base_start = datetime(2020, 1, 1, 9, 30, 0)
    base_bars = _create_synthetic_minute_bars(base_start, num_days=10, bars_per_day=5)
    
    # 建立 append 資料（2 天）
    append_start = datetime(2020, 1, 11, 9, 30, 0)
    append_bars = _create_synthetic_minute_bars(append_start, num_days=2, bars_per_day=5)
    
    # 建立兩個 TXT 檔案
    base_txt = tmp_path / "base.txt"
    base_txt.write_text("base")
    
    append_txt = tmp_path / "append.txt"
    append_txt.write_text("append")
    
    # 模擬 ingest_raw_txt 回傳不同的結果
    base_result = _create_mock_raw_ingest_result(base_txt, base_bars)
    append_result = _create_mock_raw_ingest_result(append_txt, append_bars)
    
    # 合併的結果（用於 FULL 模式）
    combined_bars = base_bars + append_bars
    combined_result = _create_mock_raw_ingest_result(base_txt, combined_bars)
    
    # 路徑 1: FULL（一次處理所有資料）
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = combined_result
        
        full_report = build_shared(
            season="2026Q1",
            dataset_id="TEST.DATASET",
            txt_path=base_txt,  # 路徑不重要，資料是模擬的
            outputs_root=tmp_path / "full",
            mode="FULL",
            save_fingerprint=False,
            build_bars=True,
            tfs=[15, 30],
        )
    
    # 路徑 2: INCREMENTAL（先 base，再 append）
    # 第一步：建立 base
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = base_result
        
        base_report = build_shared(
            season="2026Q1",
            dataset_id="TEST.DATASET",
            txt_path=base_txt,
            outputs_root=tmp_path / "incremental",
            mode="FULL",
            save_fingerprint=False,
            build_bars=True,
            tfs=[15, 30],
        )
    
    # 第二步：append（INCREMENTAL 模式）
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = append_result
        
        # 模擬 compare_fingerprint_indices 回傳 append_only=True
        from FishBroWFS_V2.core.fingerprint import compare_fingerprint_indices
        
        def mock_compare(old_index, new_index):
            return {
                "old_range_start": "2020-01-01",
                "old_range_end": "2020-01-10",
                "new_range_start": "2020-01-01",
                "new_range_end": "2020-01-12",
                "append_only": True,
                "append_range": ("2020-01-11", "2020-01-12"),
                "earliest_changed_day": None,
                "no_change": False,
                "is_new": False,
            }
        
        with patch("FishBroWFS_V2.control.shared_build.compare_fingerprint_indices", mock_compare):
            incremental_report = build_shared(
                season="2026Q1",
                dataset_id="TEST.DATASET",
                txt_path=append_txt,
                outputs_root=tmp_path / "incremental",
                mode="INCREMENTAL",
                save_fingerprint=False,
                build_bars=True,
                tfs=[15, 30],
            )
    
    # 比較結果
    for tf in [15, 30]:
        full_path = resampled_bars_path(
            tmp_path / "full", "2026Q1", "TEST.DATASET", tf
        )
        incremental_path = resampled_bars_path(
            tmp_path / "incremental", "2026Q1", "TEST.DATASET", tf
        )
        
        assert full_path.exists()
        assert incremental_path.exists()
        
        full_data = load_npz(full_path)
        incremental_data = load_npz(incremental_path)
        
        # 檢查 arrays 長度相同
        assert len(full_data["ts"]) == len(incremental_data["ts"])
        
        # 檢查時間戳記相同（允許微小浮點誤差）
        np.testing.assert_array_almost_equal(
            full_data["ts"].astype("int64"),
            incremental_data["ts"].astype("int64"),
            decimal=5,
        )
        
        # 檢查價格相同
        for key in ["open", "high", "low", "close"]:
            np.testing.assert_array_almost_equal(
                full_data[key],
                incremental_data[key],
                decimal=10,
            )
        
        # 檢查成交量相同
        np.testing.assert_array_almost_equal(
            full_data["volume"].astype("int64"),
            incremental_data["volume"].astype("int64"),
            decimal=5,
        )


def test_safe_point_cross_bar():
    """測試 Safe point 跨 bar（Red Team 案例）"""
    # 建立 session spec: open=08:45, close=17:00（非隔夜）
    session = SessionSpecTaipei(
        open_hhmm="08:45",
        close_hhmm="17:00",
        breaks=[],
        tz="Asia/Taipei",
    )
    
    # 測試案例：tf=240, append_start=10:00
    # session_start 應該是當天的 08:45
    append_start = datetime(2023, 1, 1, 10, 0, 0)
    tf = 240  # 4 小時
    
    safe_start = compute_safe_recompute_start(append_start, tf, session)
    
    # 預期 safe_start 應該是 08:45（該 bar 起點）
    expected = datetime(2023, 1, 1, 8, 45, 0)
    assert safe_start == expected
    
    # 驗證 safe_start 不晚於 append_start
    assert safe_start <= append_start
    
    # 驗證 safe_start 是 session_start + N*tf
    session_start = datetime(2023, 1, 1, 8, 45, 0)
    delta = safe_start - session_start
    delta_minutes = int(delta.total_seconds() // 60)
    assert delta_minutes % tf == 0


def test_breaks_behavior_deterministic(tmp_path):
    """測試 Breaks 行為 deterministic"""
    # 建立有 breaks 的 session spec
    session = SessionSpecTaipei(
        open_hhmm="09:00",
        close_hhmm="15:00",
        breaks=[("12:00", "13:00")],  # 中午休市 1 小時
        tz="Asia/Taipei",
    )
    
    # 建立測試資料，包含 break 時段的 bars
    bars = [
        (datetime(2023, 1, 1, 11, 30, 0), 100.0, 101.0, 99.5, 100.5, 1000.0),  # break 前
        (datetime(2023, 1, 1, 12, 30, 0), 100.5, 101.5, 100.0, 101.0, 800.0),  # break 中（應該被忽略）
        (datetime(2023, 1, 1, 13, 30, 0), 101.0, 102.0, 100.5, 101.5, 1200.0),  # break 後
    ]
    
    # 建立測試 TXT 檔案
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    mock_result = _create_mock_raw_ingest_result(txt_file, bars)
    
    # 模擬 get_session_spec_for_dataset 回傳有 breaks 的 session
    from FishBroWFS_V2.core.resampler import get_session_spec_for_dataset
    
    def mock_get_session_spec(dataset_id: str):
        return session, True
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        with patch("FishBroWFS_V2.core.resampler.get_session_spec_for_dataset", mock_get_session_spec):
            # 執行 FULL 模式
            report = build_shared(
                season="2026Q1",
                dataset_id="TEST.DATASET",
                txt_path=txt_file,
                outputs_root=tmp_path,
                mode="FULL",
                save_fingerprint=False,
                build_bars=True,
                tfs=[60],  # 1 小時 timeframe
            )
    
    assert report["success"] == True
    
    # 載入 resampled bars
    resampled_path = resampled_bars_path(tmp_path, "2026Q1", "TEST.DATASET", 60)
    assert resampled_path.exists()
    
    resampled_data = load_npz(resampled_path)
    
    # 檢查 break 時段的 bar 是否被正確處理
    # 由於我們只有 3 筆分鐘資料，且 break 中的 bar 應該被忽略
    # 所以 resampled 的 bar 數量應該少於 3
    # 實際行為取決於 resampler 的實作，但重點是 deterministic
    ts = resampled_data["ts"]
    
    # 確保結果是 deterministic 的：重跑一次應該得到相同結果
    # 我們可以重跑一次並比較
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        with patch("FishBroWFS_V2.core.resampler.get_session_spec_for_dataset", mock_get_session_spec):
            report2 = build_shared(
                season="2026Q1",
                dataset_id="TEST.DATASET",
                txt_path=txt_file,
                outputs_root=tmp_path / "second",
                mode="FULL",
                save_fingerprint=False,
                build_bars=True,
                tfs=[60],
            )
    
    resampled_path2 = resampled_bars_path(tmp_path / "second", "2026Q1", "TEST.DATASET", 60)
    resampled_data2 = load_npz(resampled_path2)
    
    # 檢查兩次結果相同
    np.testing.assert_array_equal(
        resampled_data["ts"].astype("int64"),
        resampled_data2["ts"].astype("int64"),
    )
    
    for key in ["open", "high", "low", "close", "volume"]:
        np.testing.assert_array_equal(
            resampled_data[key],
            resampled_data2[key],
        )


def test_no_mtime_size_usage():
    """確保沒有使用檔案 mtime/size 來判斷"""
    import os
    import FishBroWFS_V2.control.shared_build
    import FishBroWFS_V2.control.shared_manifest
    import FishBroWFS_V2.control.shared_cli
    import FishBroWFS_V2.control.bars_store
    import FishBroWFS_V2.control.bars_manifest
    import FishBroWFS_V2.core.resampler
    
    # 檢查模組中是否有 os.stat().st_mtime 或 st_size
    modules = [
        FishBroWFS_V2.control.shared_build,
        FishBroWFS_V2.control.shared_manifest,
        FishBroWFS_V2.control.shared_cli,
        FishBroWFS_V2.control.bars_store,
        FishBroWFS_V2.control.bars_manifest,
        FishBroWFS_V2.core.resampler,
    ]
    
    for module in modules:
        source = module.__file__
        if source and source.endswith(".py"):
            with open(source, "r", encoding="utf-8") as f:
                content = f.read()
                # 檢查是否有使用 mtime 或 size
                assert "st_mtime" not in content
                assert "st_size" not in content


def test_no_streamlit_imports():
    """確保沒有新增任何 streamlit import"""
    import FishBroWFS_V2.control.shared_build
    import FishBroWFS_V2.control.shared_manifest
    import FishBroWFS_V2.control.shared_cli
    import FishBroWFS_V2.control.bars_store
    import FishBroWFS_V2.control.bars_manifest
    import FishBroWFS_V2.core.resampler
    
    modules = [
        FishBroWFS_V2.control.shared_build,
        FishBroWFS_V2.control.shared_manifest,
        FishBroWFS_V2.control.shared_cli,
        FishBroWFS_V2.control.bars_store,
        FishBroWFS_V2.control.bars_manifest,
        FishBroWFS_V2.core.resampler,
    ]
    
    for module in modules:
        source = module.__file__
        if source and source.endswith(".py"):
            with open(source, "r", encoding="utf-8") as f:
                content = f.read()
                # 檢查是否有 streamlit import
                assert "import streamlit" not in content
                assert "from streamlit" not in content


