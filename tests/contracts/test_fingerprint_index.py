
"""
測試 Fingerprint Index 功能

確保：
1. 同一份資料重跑 → day_hash 完全一致（determinism）
2. 尾巴新增幾天 → append_only=true、append_range 正確
3. 中間某天改一筆 close → earliest_changed_day 正確
4. atomic write：寫到 tmp 再 replace
5. 不允許使用檔案 mtime/size 來判斷
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
import numpy as np

from contracts.fingerprint import FingerprintIndex
from core.fingerprint import (
    canonical_bar_line,
    compute_day_hash,
    build_fingerprint_index_from_bars,
    compare_fingerprint_indices,
)
from control.fingerprint_store import (
    write_fingerprint_index,
    load_fingerprint_index,
    fingerprint_index_path,
)


def test_canonical_bar_line():
    """測試標準化 bar 字串格式"""
    ts = datetime(2023, 1, 1, 9, 30, 0)
    line = canonical_bar_line(ts, 100.0, 105.0, 99.5, 102.5, 1000.0)
    
    # 檢查格式
    assert line == "2023-01-01T09:30:00|100.0000|105.0000|99.5000|102.5000|1000"
    
    # 測試 rounding
    line2 = canonical_bar_line(ts, 100.123456, 105.123456, 99.123456, 102.123456, 1000.123)
    assert line2 == "2023-01-01T09:30:00|100.1235|105.1235|99.1235|102.1235|1000"
    
    # 測試負數
    line3 = canonical_bar_line(ts, -100.0, -95.0, -105.0, -102.5, 1000.0)
    assert line3 == "2023-01-01T09:30:00|-100.0000|-95.0000|-105.0000|-102.5000|1000"


def test_compute_day_hash_deterministic():
    """測試 day hash 的 deterministic 特性"""
    lines = [
        "2023-01-01T09:30:00|100.0000|105.0000|99.5000|102.5000|1000",
        "2023-01-01T10:30:00|102.5000|103.0000|102.0000|102.8000|800",
    ]
    
    # 相同輸入應該產生相同 hash
    hash1 = compute_day_hash(lines)
    hash2 = compute_day_hash(lines)
    assert hash1 == hash2
    
    # 順序不同應該產生相同 hash（因為會排序）
    lines_reversed = list(reversed(lines))
    hash3 = compute_day_hash(lines_reversed)
    assert hash3 == hash1
    
    # 不同內容應該產生不同 hash
    lines_modified = lines.copy()
    lines_modified[0] = "2023-01-01T09:30:00|100.0000|105.0000|99.5000|102.5000|1001"
    hash4 = compute_day_hash(lines_modified)
    assert hash4 != hash1


def test_fingerprint_index_creation():
    """測試 FingerprintIndex 建立與驗證"""
    day_hashes = {
        "2023-01-01": "a" * 64,
        "2023-01-02": "b" * 64,
    }
    
    index = FingerprintIndex.create(
        dataset_id="TEST.DATASET",
        range_start="2023-01-01",
        range_end="2023-01-02",
        day_hashes=day_hashes,
        build_notes="test",
    )
    
    assert index.dataset_id == "TEST.DATASET"
    assert index.range_start == "2023-01-01"
    assert index.range_end == "2023-01-02"
    assert index.day_hashes == day_hashes
    assert index.build_notes == "test"
    assert len(index.index_sha256) == 64  # SHA256 hex 長度
    
    # 驗證 index_sha256 是正確計算的
    # 嘗試修改一個欄位應該導致驗證失敗
    with pytest.raises(ValueError, match="index_sha256 驗證失敗"):
        FingerprintIndex(
            dataset_id="TEST.DATASET",
            range_start="2023-01-01",
            range_end="2023-01-02",
            day_hashes=day_hashes,
            build_notes="test",
            index_sha256="wrong_hash" * 4,  # 錯誤的 hash
        )


def test_fingerprint_index_validation():
    """測試 FingerprintIndex 驗證"""
    # 無效的日期格式
    with pytest.raises(ValueError, match="無效的日期格式"):
        FingerprintIndex.create(
            dataset_id="TEST",
            range_start="2023-01-01",
            range_end="2023-01-02",
            day_hashes={"2023/01/01": "a" * 64},  # 錯誤格式
        )
    
    # 日期不在範圍內 - 錯誤訊息可能為「不在範圍」或「無效的日期格式」
    with pytest.raises(ValueError) as exc_info:
        FingerprintIndex.create(
            dataset_id="TEST",
            range_start="2023-01-01",
            range_end="2023-01-02",
            day_hashes={"2023-01-03": "a" * 64},  # 超出範圍
        )
    error_msg = str(exc_info.value)
    # 檢查錯誤訊息是否包含「不在範圍」或「無效的日期格式」
    assert "不在範圍" in error_msg or "無效的日期格式" in error_msg
    
    # 無效的 hash 長度
    with pytest.raises(ValueError, match="長度必須為 64"):
        FingerprintIndex.create(
            dataset_id="TEST",
            range_start="2023-01-01",
            range_end="2023-01-02",
            day_hashes={"2023-01-01": "short"},  # 太短
        )
    
    # 無效的 hex
    with pytest.raises(ValueError, match="不是有效的 hex 字串"):
        FingerprintIndex.create(
            dataset_id="TEST",
            range_start="2023-01-01",
            range_end="2023-01-02",
            day_hashes={"2023-01-01": "x" * 64},  # 非 hex
        )


def test_build_fingerprint_index_from_bars():
    """測試從 bars 建立指紋索引"""
    # 建立測試 bars
    bars = [
        (datetime(2023, 1, 1, 9, 30, 0), 100.0, 105.0, 99.5, 102.5, 1000.0),
        (datetime(2023, 1, 1, 10, 30, 0), 102.5, 103.0, 102.0, 102.8, 800.0),
        (datetime(2023, 1, 2, 9, 30, 0), 102.8, 104.0, 102.5, 103.5, 1200.0),
    ]
    
    index = build_fingerprint_index_from_bars(
        dataset_id="TEST.DATASET",
        bars=bars,
        build_notes="test build",
    )
    
    assert index.dataset_id == "TEST.DATASET"
    assert index.range_start == "2023-01-01"
    assert index.range_end == "2023-01-02"
    assert len(index.day_hashes) == 2  # 兩天
    assert "2023-01-01" in index.day_hashes
    assert "2023-01-02" in index.day_hashes
    assert index.build_notes == "test build"
    
    # 驗證 deterministic：相同輸入產生相同索引
    index2 = build_fingerprint_index_from_bars(
        dataset_id="TEST.DATASET",
        bars=bars,
        build_notes="test build",
    )
    
    assert index2.index_sha256 == index.index_sha256


def test_fingerprint_index_append_only():
    """測試 append-only 檢測"""
    # 建立舊索引
    old_hashes = {
        "2023-01-01": "a" * 64,
        "2023-01-02": "b" * 64,
    }
    
    old_index = FingerprintIndex.create(
        dataset_id="TEST",
        range_start="2023-01-01",
        range_end="2023-01-02",
        day_hashes=old_hashes,
    )
    
    # 新索引：僅尾部新增
    new_hashes = {
        "2023-01-01": "a" * 64,
        "2023-01-02": "b" * 64,
        "2023-01-03": "c" * 64,
    }
    
    new_index = FingerprintIndex.create(
        dataset_id="TEST",
        range_start="2023-01-01",
        range_end="2023-01-03",
        day_hashes=new_hashes,
    )
    
    # 應該是 append-only
    assert old_index.is_append_only(new_index) == True
    assert new_index.is_append_only(old_index) == False  # 反向不是
    
    # 檢查 append_range
    append_range = old_index.get_append_range(new_index)
    assert append_range == ("2023-01-03", "2023-01-03")
    
    # 檢查 earliest_changed_day 應該為 None（因為是新增，不是變更）
    earliest = old_index.get_earliest_changed_day(new_index)
    assert earliest is None


def test_fingerprint_index_with_changes():
    """測試資料變更檢測"""
    # 建立舊索引
    old_hashes = {
        "2023-01-01": "a" * 64,
        "2023-01-02": "b" * 64,
        "2023-01-03": "c" * 64,
    }
    
    old_index = FingerprintIndex.create(
        dataset_id="TEST",
        range_start="2023-01-01",
        range_end="2023-01-03",
        day_hashes=old_hashes,
    )
    
    # 新索引：中間某天變更（使用有效的 hex 字串）
    new_hashes = {
        "2023-01-01": "a" * 64,  # 相同
        "2023-01-02": "d" * 64,  # 變更（'d' 是有效的 hex 字元）
        "2023-01-03": "c" * 64,  # 相同
    }
    
    new_index = FingerprintIndex.create(
        dataset_id="TEST",
        range_start="2023-01-01",
        range_end="2023-01-03",
        day_hashes=new_hashes,
    )
    
    # 不應該是 append-only
    assert old_index.is_append_only(new_index) == False
    
    # 檢查 earliest_changed_day
    earliest = old_index.get_earliest_changed_day(new_index)
    assert earliest == "2023-01-02"


def test_compare_fingerprint_indices():
    """測試索引比較函數"""
    # 建立兩個索引
    old_hashes = {"2023-01-01": "a" * 64, "2023-01-02": "b" * 64}
    new_hashes = {"2023-01-01": "a" * 64, "2023-01-02": "b" * 64, "2023-01-03": "c" * 64}
    
    old_index = FingerprintIndex.create(
        dataset_id="TEST",
        range_start="2023-01-01",
        range_end="2023-01-02",
        day_hashes=old_hashes,
    )
    
    new_index = FingerprintIndex.create(
        dataset_id="TEST",
        range_start="2023-01-01",
        range_end="2023-01-03",
        day_hashes=new_hashes,
    )
    
    # 比較
    diff = compare_fingerprint_indices(old_index, new_index)
    
    assert diff["old_range_start"] == "2023-01-01"
    assert diff["old_range_end"] == "2023-01-02"
    assert diff["new_range_start"] == "2023-01-01"
    assert diff["new_range_end"] == "2023-01-03"
    assert diff["append_only"] == True
    assert diff["append_range"] == ("2023-01-03", "2023-01-03")
    assert diff["earliest_changed_day"] is None
    assert diff["no_change"] == False
    assert diff["is_new"] == False
    
    # 測試無舊索引的情況
    diff_new = compare_fingerprint_indices(None, new_index)
    assert diff_new["is_new"] == True
    assert diff_new["old_range_start"] is None
    assert diff_new["old_range_end"] is None
    
    # 測試完全相同的情況
    diff_same = compare_fingerprint_indices(old_index, old_index)
    assert diff_same["no_change"] == True
    assert diff_same["append_only"] == False


def test_write_and_load_fingerprint_index(tmp_path):
    """測試寫入與載入指紋索引"""
    # 建立測試索引
    day_hashes = {
        "2023-01-01": "a" * 64,
        "2023-01-02": "b" * 64,
    }
    
    index = FingerprintIndex.create(
        dataset_id="TEST.DATASET",
        range_start="2023-01-01",
        range_end="2023-01-02",
        day_hashes=day_hashes,
        build_notes="test",
    )
    
    # 寫入檔案
    test_file = tmp_path / "test_index.json"
    write_fingerprint_index(index, test_file)
    
    # 檢查檔案存在
    assert test_file.exists()
    
    # 檢查暫存檔案已清理
    temp_file = tmp_path / "test_index.json.tmp"
    assert not temp_file.exists()
    
    # 載入檔案
    loaded = load_fingerprint_index(test_file)
    
    # 驗證載入的索引與原始相同
    assert loaded.dataset_id == index.dataset_id
    assert loaded.range_start == index.range_start
    assert loaded.range_end == index.range_end
    assert loaded.day_hashes == index.day_hashes
    assert loaded.build_notes == index.build_notes
    assert loaded.index_sha256 == index.index_sha256
    
    # 驗證 JSON 是 canonical 格式（排序的鍵）
    content = test_file.read_text()
    data = json.loads(content)
    # 檢查鍵的順序（應該排序）
    keys = list(data.keys())
    assert keys == sorted(keys)


def test_atomic_write_failure(tmp_path):
    """測試 atomic write 失敗時的清理"""
    # 建立測試索引
    day_hashes = {"2023-01-01": "a" * 64}
    index = FingerprintIndex.create(
        dataset_id="TEST",
        range_start="2023-01-01",
        range_end="2023-01-01",
        day_hashes=day_hashes,
    )
    
    test_file = tmp_path / "test_index.json"
    
    # 模擬寫入失敗
    with patch("pathlib.Path.write_text") as mock_write:
        mock_write.side_effect = IOError("模拟写入失败")
        
        with pytest.raises(IOError, match="寫入指紋索引失敗"):
            write_fingerprint_index(index, test_file)
    
    # 檢查檔案不存在（已清理）
    assert not test_file.exists()
    
    # 檢查暫存檔案不存在
    temp_file = tmp_path / "test_index.json.tmp"
    assert not temp_file.exists()


def test_fingerprint_index_path():
    """測試指紋索引路徑生成"""
    path = fingerprint_index_path(
        season="2026Q1",
        dataset_id="CME.MNQ.60m.2020-2024",
        outputs_root=Path("/tmp/outputs"),
    )
    
    expected = Path("/tmp/outputs/fingerprints/2026Q1/CME.MNQ.60m.2020-2024/fingerprint_index.json")
    assert path == expected


def test_no_mtime_size_usage():
    """確保沒有使用檔案 mtime/size 來判斷"""
    import os
    import contracts.fingerprint
    import core.fingerprint
    import control.fingerprint_store
    import control.fingerprint_cli
    
    # 檢查模組中是否有 os.stat().st_mtime 或 st_size
    modules = [
        contracts.fingerprint,
        core.fingerprint,
        control.fingerprint_store,
        control.fingerprint_cli,
    ]
    
    for module in modules:
        source = module.__file__
        if source and source.endswith(".py"):
            with open(source, "r", encoding="utf-8") as f:
                content = f.read()
                # 檢查是否有使用 mtime 或 size
                assert "st_mtime" not in content
                assert "st_size" not in content


