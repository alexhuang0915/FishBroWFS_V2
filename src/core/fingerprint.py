
"""
Fingerprint 計算核心

提供 canonical bytes 規則與指紋計算函數，確保 deterministic 結果。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from contracts.fingerprint import FingerprintIndex
from contracts.dimensions import canonical_json
from core.data.raw_ingest import RawIngestResult


def canonical_bar_line(
    ts: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> str:
    """Build a deterministic bar line for hashing."""
    return (
        f"{ts.isoformat()}|{open_:.4f}|{high:.4f}|{low:.4f}|{close:.4f}|{int(volume)}"
    )


def compute_day_hash(lines: Iterable[str]) -> str:
    """Compute a stable day hash from canonicalized bar lines."""
    sorted_lines = sorted(lines)
    payload = "\n".join(sorted_lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_fingerprint_index_from_raw_ingest(
    dataset_id: str,
    raw_ingest_result: RawIngestResult,
    dataset_timezone: str = "Asia/Taipei",
    build_notes: str = ""
) -> FingerprintIndex:
    """
    從 RawIngestResult 建立指紋索引（便利函數）
    """
    df = raw_ingest_result.get_df()
    
    # 準備 bars 迭代器
    bars = []
    # Ensure TS is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df["ts"] = pd.to_datetime(df["ts"])

    for _, row in df.iterrows():
        try:
            ts = row["ts"].to_pydatetime()
            bars.append((
                ts,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"])
            ))
        except Exception as e:
            raise ValueError(f"解析 bar 資料失敗: {e}") from e
    
    return build_fingerprint_index_from_bars(
        dataset_id=dataset_id,
        bars=bars,
        dataset_timezone=dataset_timezone,
        build_notes=build_notes
    )


def compare_fingerprint_indices(
    old_index: FingerprintIndex | None,
    new_index: FingerprintIndex
) -> Dict[str, Any]:
    """
    比較兩個指紋索引，產生 diff 報告
    
    Args:
        old_index: 舊索引（可為 None）
        new_index: 新索引
    
    Returns:
        diff 報告字典
    """
    if old_index is None:
        return {
            "old_range_start": None,
            "old_range_end": None,
            "new_range_start": new_index.range_start,
            "new_range_end": new_index.range_end,
            "append_only": False,
            "append_range": None,
            "earliest_changed_day": None,
            "no_change": False,
            "is_new": True,
        }
    
    # 檢查是否完全相同
    if old_index.index_sha256 == new_index.index_sha256:
        return {
            "old_range_start": old_index.range_start,
            "old_range_end": old_index.range_end,
            "new_range_start": new_index.range_start,
            "new_range_end": new_index.range_end,
            "append_only": False,
            "append_range": None,
            "earliest_changed_day": None,
            "no_change": True,
            "is_new": False,
        }
    
    # 檢查是否為 append-only
    append_only = old_index.is_append_only(new_index)
    append_range = old_index.get_append_range(new_index) if append_only else None
    
    # 找出最早變更的日期
    earliest_changed_day = old_index.get_earliest_changed_day(new_index)
    
    return {
        "old_range_start": old_index.range_start,
        "old_range_end": old_index.range_end,
        "new_range_start": new_index.range_start,
        "new_range_end": new_index.range_end,
        "append_only": append_only,
        "append_range": append_range,
        "earliest_changed_day": earliest_changed_day,
        "no_change": False,
        "is_new": False,
    }


def build_fingerprint_index_from_bars(
    dataset_id: str,
    bars: List[Tuple[datetime, float, float, float, float, float]],
    dataset_timezone: str = "Asia/Taipei",
    build_notes: str = ""
) -> FingerprintIndex:
    """
    從 bars 列表建立指紋索引
    
    Args:
        dataset_id: 資料集 ID
        bars: bars 列表，每項為 (ts, o, h, l, c, v) tuple
        dataset_timezone: 時區
        build_notes: 建置備註
    
    Returns:
        FingerprintIndex 實例
    """
    if not bars:
        return FingerprintIndex.create(
            dataset_id=dataset_id,
            range_start="1970-01-01",
            range_end="1970-01-01",
            day_hashes={},
            dataset_timezone=dataset_timezone,
            build_notes=build_notes
        )
    
    # Sort bars by timestamp
    bars.sort(key=lambda x: x[0])
    
    # Group by day
    # Assuming bars are in local time or consistent time
    # Here we simply use the date part of the timestamp
    daily_bars = {}
    for bar in bars:
        ts = bar[0]
        day_str = ts.strftime("%Y-%m-%d")
        if day_str not in daily_bars:
            daily_bars[day_str] = []
        
        # Convert bar to dict for canonicalization
        daily_bars[day_str].append({
            "ts": ts.isoformat(),
            "o": bar[1],
            "h": bar[2],
            "l": bar[3],
            "c": bar[4],
            "v": bar[5]
        })
    
    # Compute daily hashes
    day_hashes = {}
    sorted_days = sorted(daily_bars.keys())
    
    for day_str in sorted_days:
        day_data = daily_bars[day_str]
        # Canonicalize
        json_str = canonical_json(day_data)
        # Compute SHA256
        day_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        day_hashes[day_str] = day_hash
    
    return FingerprintIndex.create(
        dataset_id=dataset_id,
        range_start=sorted_days[0],
        range_end=sorted_days[-1],
        day_hashes=day_hashes,
        dataset_timezone=dataset_timezone,
        build_notes=build_notes
    )
