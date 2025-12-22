
"""
Shared Build Gate 測試

確保：
1. FULL 模式永遠允許
2. INCREMENTAL 模式：append-only 允許
3. INCREMENTAL 模式：歷史改動拒絕
4. manifest deterministic 與 atomic write
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
import numpy as np

from FishBroWFS_V2.contracts.fingerprint import FingerprintIndex
from FishBroWFS_V2.control.shared_build import (
    BuildMode,
    IncrementalBuildRejected,
    build_shared,
    load_shared_manifest,
)
from FishBroWFS_V2.control.shared_manifest import write_shared_manifest
from FishBroWFS_V2.core.fingerprint import (
    canonical_bar_line,
    compute_day_hash,
    build_fingerprint_index_from_bars,
)
from FishBroWFS_V2.data.raw_ingest import RawIngestResult, IngestPolicy
import pandas as pd


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


def test_full_mode_always_allowed(tmp_path):
    """測試 FULL 模式永遠允許"""
    # 建立測試 TXT 檔案（模擬）
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    # 模擬 ingest_raw_txt 回傳一個 RawIngestResult
    bars = [
        (datetime(2023, 1, 1, 9, 30, 0), 100.0, 105.0, 99.5, 102.5, 1000.0),
        (datetime(2023, 1, 2, 9, 30, 0), 102.5, 103.0, 102.0, 102.8, 800.0),
    ]
    
    mock_result = _create_mock_raw_ingest_result(txt_file, bars)
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        # 執行 FULL 模式
        report = build_shared(
            season="2026Q1",
            dataset_id="TEST.DATASET",
            txt_path=txt_file,
            outputs_root=tmp_path,
            mode="FULL",
            save_fingerprint=False,
        )
    
    assert report["success"] == True
    assert report["mode"] == "FULL"
    assert report["season"] == "2026Q1"
    assert report["dataset_id"] == "TEST.DATASET"


def test_incremental_append_only_allowed(tmp_path):
    """測試 INCREMENTAL 模式：append-only 允許"""
    # 建立測試 TXT 檔案（模擬）
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    # 模擬 compare_fingerprint_indices 回傳 append_only=True
    from FishBroWFS_V2.core.fingerprint import compare_fingerprint_indices
    
    def mock_compare(old_index, new_index):
        return {
            "old_range_start": "2023-01-01",
            "old_range_end": "2023-01-02",
            "new_range_start": "2023-01-01",
            "new_range_end": "2023-01-03",
            "append_only": True,
            "append_range": ("2023-01-03", "2023-01-03"),
            "earliest_changed_day": None,
            "no_change": False,
            "is_new": False,
        }
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        # 模擬 ingest_raw_txt 回傳一個 RawIngestResult
        bars = [
            (datetime(2023, 1, 1, 9, 30, 0), 100.0, 105.0, 99.5, 102.5, 1000.0),
        ]
        mock_result = _create_mock_raw_ingest_result(txt_file, bars)
        mock_ingest.return_value = mock_result
        
        with patch("FishBroWFS_V2.control.shared_build.compare_fingerprint_indices", mock_compare):
            # 執行 INCREMENTAL 模式
            report = build_shared(
                season="2026Q1",
                dataset_id="TEST.DATASET",
                txt_path=txt_file,
                outputs_root=tmp_path,
                mode="INCREMENTAL",
                save_fingerprint=False,
            )
    
    assert report["success"] == True
    assert report["mode"] == "INCREMENTAL"
    assert report["diff"]["append_only"] == True
    assert report.get("incremental_accepted") == True


def test_incremental_historical_changes_rejected(tmp_path):
    """測試 INCREMENTAL 模式：歷史改動拒絕"""
    # 先建立舊指紋索引
    old_hashes = {
        "2023-01-01": "a" * 64,
        "2023-01-02": "b" * 64,
    }
    
    old_index = FingerprintIndex.create(
        dataset_id="TEST.DATASET",
        range_start="2023-01-01",
        range_end="2023-01-02",
        day_hashes=old_hashes,
    )
    
    # 寫入指紋索引
    from FishBroWFS_V2.control.fingerprint_store import write_fingerprint_index
    index_path = tmp_path / "fingerprints" / "2026Q1" / "TEST.DATASET" / "fingerprint_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    write_fingerprint_index(old_index, index_path)
    
    # 建立測試 TXT 檔案（模擬）
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    # 模擬 ingest_raw_txt 回傳一個 RawIngestResult（包含變更的資料）
    # 注意：hash 會不同，因為資料不同
    bars = [
        (datetime(2023, 1, 1, 9, 30, 0), 100.0, 105.0, 99.5, 102.5, 1000.0),
        (datetime(2023, 1, 2, 9, 30, 0), 102.5, 103.0, 102.0, 102.8, 800.0),
        # 故意修改第二天的資料，使其 hash 不同
    ]
    
    mock_result = _create_mock_raw_ingest_result(txt_file, bars)
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        # 執行 INCREMENTAL 模式，應該被拒絕
        with pytest.raises(IncrementalBuildRejected) as exc_info:
            build_shared(
                season="2026Q1",
                dataset_id="TEST.DATASET",
                txt_path=txt_file,
                outputs_root=tmp_path,
                mode="INCREMENTAL",
                save_fingerprint=False,
            )
        
        assert "INCREMENTAL 模式被拒絕" in str(exc_info.value)
        assert "earliest_changed_day" in str(exc_info.value)


def test_incremental_new_dataset_allowed(tmp_path):
    """測試 INCREMENTAL 模式：全新資料集允許（因為 is_new）"""
    # 不建立舊指紋索引
    
    # 建立測試 TXT 檔案（模擬）
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    bars = [
        (datetime(2023, 1, 1, 9, 30, 0), 100.0, 105.0, 99.5, 102.5, 1000.0),
    ]
    
    mock_result = _create_mock_raw_ingest_result(txt_file, bars)
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        # 執行 INCREMENTAL 模式
        report = build_shared(
            season="2026Q1",
            dataset_id="TEST.DATASET",
            txt_path=txt_file,
            outputs_root=tmp_path,
            mode="INCREMENTAL",
            save_fingerprint=False,
        )
    
    assert report["success"] == True
    assert report["diff"]["is_new"] == True
    assert report.get("incremental_accepted") is not None


def test_manifest_deterministic(tmp_path):
    """測試 manifest deterministic：同輸入重跑 manifest_sha256 一樣"""
    # 建立測試 TXT 檔案（模擬）
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    bars = [
        (datetime(2023, 1, 1, 9, 30, 0), 100.0, 105.0, 99.5, 102.5, 1000.0),
    ]
    
    mock_result = _create_mock_raw_ingest_result(txt_file, bars)
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        # 第一次執行
        report1 = build_shared(
            season="2026Q1",
            dataset_id="TEST.DATASET",
            txt_path=txt_file,
            outputs_root=tmp_path,
            mode="FULL",
            save_fingerprint=False,
            generated_at_utc="2023-01-01T00:00:00Z",  # 固定時間戳記
        )
        
        # 第二次執行（相同輸入）
        report2 = build_shared(
            season="2026Q1",
            dataset_id="TEST.DATASET",
            txt_path=txt_file,
            outputs_root=tmp_path,
            mode="FULL",
            save_fingerprint=False,
            generated_at_utc="2023-01-01T00:00:00Z",  # 相同固定時間戳記
        )
    
    # 檢查 manifest_sha256 相同
    assert report1["manifest_sha256"] == report2["manifest_sha256"]
    
    # 載入 manifest 驗證 hash
    manifest_path = Path(report1["manifest_path"])
    assert manifest_path.exists()
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    assert manifest_data["manifest_sha256"] == report1["manifest_sha256"]


def test_manifest_atomic_write(tmp_path):
    """測試 manifest atomic write：使用 .tmp + replace"""
    # 建立測試 payload
    payload = {
        "build_mode": "FULL",
        "season": "2026Q1",
        "dataset_id": "TEST.DATASET",
        "input_txt_path": "test.txt",
    }
    
    manifest_path = tmp_path / "shared_manifest.json"
    
    # 模擬寫入失敗，檢查暫存檔案被清理
    with patch("pathlib.Path.write_text") as mock_write:
        mock_write.side_effect = IOError("模拟写入失败")
        
        with pytest.raises(IOError, match="寫入 shared manifest 失敗"):
            write_shared_manifest(payload, manifest_path)
    
    # 檢查暫存檔案不存在
    temp_path = manifest_path.with_suffix(".json.tmp")
    assert not temp_path.exists()
    assert not manifest_path.exists()
    
    # 正常寫入
    final_payload = write_shared_manifest(payload, manifest_path)
    
    # 檢查檔案存在
    assert manifest_path.exists()
    assert "manifest_sha256" in final_payload
    
    # 檢查暫存檔案已清理
    assert not temp_path.exists()


def test_load_shared_manifest(tmp_path):
    """測試載入 shared manifest"""
    # 建立測試 manifest
    payload = {
        "build_mode": "FULL",
        "season": "2026Q1",
        "dataset_id": "TEST.DATASET",
        "input_txt_path": "test.txt",
    }
    
    # 使用正確的路徑結構：outputs_root/shared/season/dataset_id/shared_manifest.json
    from FishBroWFS_V2.control.shared_build import _shared_manifest_path
    manifest_path = _shared_manifest_path(
        season="2026Q1",
        dataset_id="TEST.DATASET",
        outputs_root=tmp_path,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    final_payload = write_shared_manifest(payload, manifest_path)
    
    # 使用 load_shared_manifest 載入
    loaded = load_shared_manifest(
        season="2026Q1",
        dataset_id="TEST.DATASET",
        outputs_root=tmp_path,
    )
    
    assert loaded is not None
    assert loaded["build_mode"] == "FULL"
    assert loaded["manifest_sha256"] == final_payload["manifest_sha256"]
    
    # 測試不存在的 manifest
    nonexistent = load_shared_manifest(
        season="2026Q1",
        dataset_id="NONEXISTENT",
        outputs_root=tmp_path,
    )
    
    assert nonexistent is None


def test_no_mtime_size_usage():
    """確保沒有使用檔案 mtime/size 來判斷"""
    import os
    import FishBroWFS_V2.control.shared_build
    import FishBroWFS_V2.control.shared_manifest
    import FishBroWFS_V2.control.shared_cli
    
    # 檢查模組中是否有 os.stat().st_mtime 或 st_size
    modules = [
        FishBroWFS_V2.control.shared_build,
        FishBroWFS_V2.control.shared_manifest,
        FishBroWFS_V2.control.shared_cli,
    ]
    
    for module in modules:
        source = module.__file__
        if source and source.endswith(".py"):
            with open(source, "r", encoding="utf-8") as f:
                content = f.read()
                # 檢查是否有使用 mtime 或 size
                assert "st_mtime" not in content
                assert "st_size" not in content


def test_exit_code_simulation(tmp_path):
    """測試 CLI exit code 模擬（透過 IncrementalBuildRejected）"""
    from FishBroWFS_V2.control.shared_build import IncrementalBuildRejected
    
    # 建立測試 TXT 檔案（模擬）
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("dummy")
    
    # 模擬 ingest_raw_txt 回傳一個 RawIngestResult
    bars = [
        (datetime(2023, 1, 1, 9, 30, 0), 100.0, 105.0, 99.5, 102.5, 1000.0),
    ]
    
    mock_result = _create_mock_raw_ingest_result(txt_file, bars)
    
    with patch("FishBroWFS_V2.control.shared_build.ingest_raw_txt") as mock_ingest:
        mock_ingest.return_value = mock_result
        
        # 模擬歷史變更（透過 monkey patch compare_fingerprint_indices）
        from FishBroWFS_V2.core.fingerprint import compare_fingerprint_indices
        
        def mock_compare(old_index, new_index):
            return {
                "old_range_start": "2023-01-01",
                "old_range_end": "2023-01-01",
                "new_range_start": "2023-01-01",
                "new_range_end": "2023-01-01",
                "append_only": False,
                "append_range": None,
                "earliest_changed_day": "2023-01-01",
                "no_change": False,
                "is_new": False,
            }
        
        with patch("FishBroWFS_V2.control.shared_build.compare_fingerprint_indices", mock_compare):
            with pytest.raises(IncrementalBuildRejected) as exc_info:
                build_shared(
                    season="2026Q1",
                    dataset_id="TEST.DATASET",
                    txt_path=txt_file,
                    outputs_root=tmp_path,
                    mode="INCREMENTAL",
                    save_fingerprint=False,
                )
            
            assert "INCREMENTAL 模式被拒絕" in str(exc_info.value)


