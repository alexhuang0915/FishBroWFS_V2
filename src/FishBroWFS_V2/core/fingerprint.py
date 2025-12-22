
# src/FishBroWFS_V2/core/fingerprint.py
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

from FishBroWFS_V2.contracts.fingerprint import FingerprintIndex
from FishBroWFS_V2.data.raw_ingest import RawIngestResult


def canonical_bar_line(
    ts: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float
) -> str:
    """
    將單一 bar 轉換為標準化字串
    
    格式固定：YYYY-MM-DDTHH:MM:SS|{o:.4f}|{h:.4f}|{l:.4f}|{c:.4f}|{v:.0f}
    
    Args:
        ts: 時間戳記
        o: 開盤價
        h: 最高價
        l: 最低價
        c: 收盤價
        v: 成交量
    
    Returns:
        標準化字串
    """
    # 格式化時間戳記
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S")
    
    # 格式化價格（固定小數位數）
    # 使用 round 確保 deterministic，避免浮點數表示差異
    o_fmt = f"{o:.4f}"
    h_fmt = f"{h:.4f}"
    l_fmt = f"{l:.4f}"
    c_fmt = f"{c:.4f}"
    
    # 格式化成交量（整數）
    v_fmt = f"{v:.0f}"
    
    return f"{ts_str}|{o_fmt}|{h_fmt}|{l_fmt}|{c_fmt}|{v_fmt}"


def compute_day_hash(lines: List[str]) -> str:
    """
    計算一日的 hash
    
    將該日所有 bar 的標準化字串排序後連接，計算 SHA256。
    
    Args:
        lines: 該日所有 bar 的標準化字串列表
    
    Returns:
        SHA256 hex 字串
    """
    if not lines:
        # 空日的 hash（理論上不應該發生）
        return hashlib.sha256(b"").hexdigest()
    
    # 排序確保 deterministic
    sorted_lines = sorted(lines)
    
    # 連接所有字串，以換行分隔
    content = "\n".join(sorted_lines)
    
    # 計算 SHA256
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse_ts_str(ts_str: str) -> datetime:
    """
    解析時間戳記字串
    
    支援多種格式：
    - "YYYY-MM-DD HH:MM:SS"
    - "YYYY/MM/DD HH:MM:SS"
    - "YYYY-MM-DDTHH:MM:SS"
    """
    # 嘗試常見格式
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%dT%H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    
    # 如果都不匹配，嘗試使用 pandas 解析
    try:
        return pd.to_datetime(ts_str).to_pydatetime()
    except Exception as e:
        raise ValueError(f"無法解析時間戳記: {ts_str}") from e


def _group_bars_by_day(
    bars: Iterable[Tuple[datetime, float, float, float, float, float]]
) -> Dict[str, List[str]]:
    """
    將 bars 按日期分組
    
    Args:
        bars: (ts, o, h, l, c, v) 的迭代器
    
    Returns:
        字典：日期字串 (YYYY-MM-DD) -> 該日所有 bar 的標準化字串列表
    """
    day_groups: Dict[str, List[str]] = {}
    
    for ts, o, h, l, c, v in bars:
        # 取得日期字串
        day_str = ts.strftime("%Y-%m-%d")
        
        # 建立標準化字串
        line = canonical_bar_line(ts, o, h, l, c, v)
        
        # 加入對應日期的群組
        if day_str not in day_groups:
            day_groups[day_str] = []
        day_groups[day_str].append(line)
    
    return day_groups


def build_fingerprint_index_from_bars(
    dataset_id: str,
    bars: Iterable[Tuple[datetime, float, float, float, float, float]],
    dataset_timezone: str = "Asia/Taipei",
    build_notes: str = ""
) -> FingerprintIndex:
    """
    從 bars 建立指紋索引
    
    Args:
        dataset_id: 資料集 ID
        bars: (ts, o, h, l, c, v) 的迭代器
        dataset_timezone: 時區
        build_notes: 建置備註
    
    Returns:
        FingerprintIndex
    """
    # 按日期分組
    day_groups = _group_bars_by_day(bars)
    
    if not day_groups:
        raise ValueError("沒有 bars 資料")
    
    # 計算每日 hash
    day_hashes: Dict[str, str] = {}
    for day_str, lines in day_groups.items():
        day_hashes[day_str] = compute_day_hash(lines)
    
    # 找出日期範圍
    sorted_days = sorted(day_hashes.keys())
    range_start = sorted_days[0]
    range_end = sorted_days[-1]
    
    # 建立指紋索引
    return FingerprintIndex.create(
        dataset_id=dataset_id,
        range_start=range_start,
        range_end=range_end,
        day_hashes=day_hashes,
        dataset_timezone=dataset_timezone,
        build_notes=build_notes
    )


def build_fingerprint_index_from_raw_ingest(
    dataset_id: str,
    raw_ingest_result: RawIngestResult,
    dataset_timezone: str = "Asia/Taipei",
    build_notes: str = ""
) -> FingerprintIndex:
    """
    從 RawIngestResult 建立指紋索引（便利函數）
    
    Args:
        dataset_id: 資料集 ID
        raw_ingest_result: RawIngestResult
        dataset_timezone: 時區
        build_notes: 建置備註
    
    Returns:
        FingerprintIndex
    """
    df = raw_ingest_result.df
    
    # 準備 bars 迭代器
    bars = []
    for _, row in df.iterrows():
        try:
            ts = _parse_ts_str(row["ts_str"])
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


