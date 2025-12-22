
# src/FishBroWFS_V2/control/bars_store.py
"""
Bars I/O 工具

提供 deterministic NPZ 檔案讀寫，支援 atomic write（tmp + replace）與 SHA256 計算。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Dict, Literal, Optional, Union
import numpy as np

Timeframe = Literal[15, 30, 60, 120, 240]


def bars_dir(outputs_root: Path, season: str, dataset_id: str) -> Path:
    """
    取得 bars 目錄路徑

    建議位置：outputs/shared/{season}/{dataset_id}/bars/

    Args:
        outputs_root: 輸出根目錄
        season: 季節標記，例如 "2026Q1"
        dataset_id: 資料集 ID

    Returns:
        目錄路徑
    """
    # 建立路徑
    path = outputs_root / "shared" / season / dataset_id / "bars"
    return path


def normalized_bars_path(outputs_root: Path, season: str, dataset_id: str) -> Path:
    """
    取得 normalized bars 檔案路徑

    建議位置：outputs/shared/{season}/{dataset_id}/bars/normalized_bars.npz

    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID

    Returns:
        檔案路徑
    """
    dir_path = bars_dir(outputs_root, season, dataset_id)
    return dir_path / "normalized_bars.npz"


def resampled_bars_path(
    outputs_root: Path, 
    season: str, 
    dataset_id: str, 
    tf_min: Timeframe
) -> Path:
    """
    取得 resampled bars 檔案路徑

    建議位置：outputs/shared/{season}/{dataset_id}/bars/resampled_{tf_min}m.npz

    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        tf_min: timeframe 分鐘數（15, 30, 60, 120, 240）

    Returns:
        檔案路徑
    """
    dir_path = bars_dir(outputs_root, season, dataset_id)
    return dir_path / f"resampled_{tf_min}m.npz"


def write_npz_atomic(path: Path, arrays: Dict[str, np.ndarray]) -> None:
    """
    Write npz via tmp + replace. Deterministic keys order.

    行為規格：
    1. 建立暫存檔案（.npz.tmp）
    2. 將 arrays 的 keys 排序以確保 deterministic
    3. 使用 np.savez_compressed 寫入暫存檔案
    4. 將暫存檔案 atomic replace 到目標路徑
    5. 如果寫入失敗，清理暫存檔案

    Args:
        path: 目標檔案路徑
        arrays: 字典，key 為字串，value 為 numpy array

    Raises:
        IOError: 寫入失敗
    """
    # 確保目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 建立暫存檔案路徑（np.savez 會自動添加 .npz 副檔名）
    # 所以我們需要建立沒有 .npz 的暫存檔案名，例如 normalized_bars.npz.tmp -> normalized_bars.tmp
    # 然後 np.savez 會建立 normalized_bars.tmp.npz，我們再重命名為 normalized_bars.npz
    temp_base = path.with_suffix("")  # 移除 .npz
    temp_path = temp_base.with_suffix(temp_base.suffix + ".tmp.npz")
    
    try:
        # 排序 keys 以確保 deterministic
        sorted_keys = sorted(arrays.keys())
        sorted_arrays = {k: arrays[k] for k in sorted_keys}
        
        # 寫入暫存檔案（使用 savez，避免壓縮可能導致的問題）
        np.savez(temp_path, **sorted_arrays)
        
        # atomic replace
        temp_path.replace(path)
        
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise IOError(f"寫入 NPZ 檔案失敗 {path}: {e}")
    
    finally:
        # 確保暫存檔案被清理（如果 replace 成功，temp_path 已不存在）
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def load_npz(path: Path) -> Dict[str, np.ndarray]:
    """
    載入 NPZ 檔案

    Args:
        path: NPZ 檔案路徑

    Returns:
        字典，key 為字串，value 為 numpy array

    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: 檔案格式錯誤
    """
    if not path.exists():
        raise FileNotFoundError(f"NPZ 檔案不存在: {path}")
    
    try:
        with np.load(path, allow_pickle=False) as data:
            # 轉換為字典（保持原始順序，但我們不依賴順序）
            arrays = {key: data[key] for key in data.files}
            return arrays
    except Exception as e:
        raise ValueError(f"載入 NPZ 檔案失敗 {path}: {e}")


def sha256_file(path: Path) -> str:
    """
    計算檔案的 SHA256 hash

    Args:
        path: 檔案路徑

    Returns:
        SHA256 hex digest（小寫）

    Raises:
        FileNotFoundError: 檔案不存在
        IOError: 讀取失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"檔案不存在: {path}")
    
    sha256 = hashlib.sha256()
    
    try:
        with open(path, "rb") as f:
            # 分塊讀取以避免記憶體問題
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
    except Exception as e:
        raise IOError(f"讀取檔案失敗 {path}: {e}")
    
    return sha256.hexdigest()


def canonical_json(obj: dict) -> str:
    """
    產生標準化 JSON 字串，確保序列化一致性

    使用與 contracts/dimensions.py 相同的實作

    Args:
        obj: 要序列化的字典

    Returns:
        標準化 JSON 字串
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


