
"""
Feature Store（NPZ atomic + SHA256）

提供 features cache 的 I/O 工具，重用 bars_store 的 atomic write 與 SHA256 計算。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Literal, Optional
import numpy as np
from config.registry.timeframes import load_timeframes

from control.bars_store import (
    write_npz_atomic,
    load_npz,
    sha256_file,
    canonical_json,
)

# Dynamically create Timeframe literal type based on timeframe registry
_timeframe_registry = load_timeframes()
_timeframe_values = tuple(_timeframe_registry.allowed_timeframes)
Timeframe = Literal[_timeframe_values]  # type: ignore


def features_dir(outputs_root: Path, season: str, dataset_id: str) -> Path:
    """
    取得 features 目錄路徑
    
    建議位置：outputs/shared/{season}/{dataset_id}/features/
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記，例如 "2026Q1"
        dataset_id: 資料集 ID
        
    Returns:
        目錄路徑
    """
    # 建立路徑
    path = outputs_root / "shared" / season / dataset_id / "features"
    return path


def features_path(
    outputs_root: Path,
    season: str,
    dataset_id: str,
    tf_min: Timeframe,
) -> Path:
    """
    取得 features 檔案路徑
    
    建議位置：outputs/shared/{season}/{dataset_id}/features/features_{tf_min}m.npz
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        tf_min: timeframe 分鐘數（15, 30, 60, 120, 240）
        
    Returns:
        檔案路徑
    """
    dir_path = features_dir(outputs_root, season, dataset_id)
    return dir_path / f"features_{tf_min}m.npz"


def write_features_npz_atomic(
    path: Path,
    features_dict: Dict[str, np.ndarray],
) -> None:
    """
    Write features NPZ via tmp + replace. Deterministic keys order.

    重用 bars_store.write_npz_atomic 但確保 keys 順序固定：
    ts, atr_14, ret_z_200, session_vwap

    Args:
        path: 目標檔案路徑
        features_dict: 特徵字典，必須包含所有必要 keys

    Raises:
        ValueError: 缺少必要 keys
        IOError: 寫入失敗
    """
    # 驗證必要 keys
    required_keys = {"ts", "atr_14", "ret_z_200", "session_vwap"}
    missing_keys = required_keys - set(features_dict.keys())
    if missing_keys:
        raise ValueError(f"features_dict 缺少必要 keys: {missing_keys}")
    
    # 確保 ts 的 dtype 是 datetime64[s]
    ts = features_dict["ts"]
    if not np.issubdtype(ts.dtype, np.datetime64):
        raise ValueError(f"ts 的 dtype 必須是 datetime64，實際為 {ts.dtype}")
    
    # 確保所有特徵陣列都是 float64
    for key in ["atr_14", "ret_z_200", "session_vwap"]:
        arr = features_dict[key]
        if not np.issubdtype(arr.dtype, np.floating):
            raise ValueError(f"{key} 的 dtype 必須是浮點數，實際為 {arr.dtype}")
    
    # 使用 bars_store 的 write_npz_atomic
    write_npz_atomic(path, features_dict)


def load_features_npz(path: Path) -> Dict[str, np.ndarray]:
    """
    載入 features NPZ 檔案
    
    Args:
        path: NPZ 檔案路徑
        
    Returns:
        特徵字典
        
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: 檔案格式錯誤或缺少必要 keys
    """
    # 使用 bars_store 的 load_npz
    data = load_npz(path)
    
    # 驗證必要 keys
    required_keys = {"ts", "atr_14", "ret_z_200", "session_vwap"}
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        raise ValueError(f"載入的 NPZ 缺少必要 keys: {missing_keys}")
    
    return data


def sha256_features_file(
    outputs_root: Path,
    season: str,
    dataset_id: str,
    tf_min: Timeframe,
) -> str:
    """
    計算 features NPZ 檔案的 SHA256 hash
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        tf_min: timeframe 分鐘數
        
    Returns:
        SHA256 hex digest（小寫）
        
    Raises:
        FileNotFoundError: 檔案不存在
        IOError: 讀取失敗
    """
    path = features_path(outputs_root, season, dataset_id, tf_min)
    return sha256_file(path)


def compute_features_sha256_dict(
    outputs_root: Path,
    season: str,
    dataset_id: str,
    tfs: Optional[list[Timeframe]] = None,
) -> Dict[str, str]:
    """
    計算所有 timeframe 的 features NPZ 檔案 SHA256 hash
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        tfs: timeframe 列表，若為 None 則使用 timeframe registry 中的所有 timeframe
        
    Returns:
        字典：filename -> sha256
    """
    if tfs is None:
        # Use all timeframes from registry
        tfs = list(_timeframe_registry.allowed_timeframes)
    
    result = {}
    
    for tf in tfs:
        try:
            sha256 = sha256_features_file(outputs_root, season, dataset_id, tf)
            result[f"features_{tf}m.npz"] = sha256
        except FileNotFoundError:
            # 檔案不存在，跳過
            continue
    
    return result


