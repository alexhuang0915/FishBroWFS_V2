
# src/FishBroWFS_V2/control/bars_manifest.py
"""
Bars Manifest 寫入工具

提供 deterministic JSON + self-hash manifest_sha256 + atomic write。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.contracts.dimensions import canonical_json


def write_bars_manifest(payload: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """
    Deterministic JSON + self-hash manifest_sha256 + atomic write.
    
    行為規格：
    1. 建立暫存檔案（.json.tmp）
    2. 計算 payload 的 SHA256 hash（排除 manifest_sha256 欄位）
    3. 將 hash 加入 payload 作為 manifest_sha256 欄位
    4. 使用 canonical_json 寫入暫存檔案（確保排序一致）
    5. atomic replace 到目標路徑
    6. 如果寫入失敗，清理暫存檔案
    
    Args:
        payload: manifest 資料字典（不含 manifest_sha256）
        path: 目標檔案路徑
        
    Returns:
        最終的 manifest 字典（包含 manifest_sha256 欄位）
        
    Raises:
        IOError: 寫入失敗
    """
    # 確保目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 建立暫存檔案路徑
    temp_path = path.with_suffix(path.suffix + ".tmp")
    
    try:
        # 計算 payload 的 SHA256 hash（排除可能的 manifest_sha256 欄位）
        payload_without_hash = {k: v for k, v in payload.items() if k != "manifest_sha256"}
        json_str = canonical_json(payload_without_hash)
        manifest_sha256 = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        
        # 建立最終 payload（包含 hash）
        final_payload = {**payload_without_hash, "manifest_sha256": manifest_sha256}
        
        # 使用 canonical_json 寫入暫存檔案
        final_json = canonical_json(final_payload)
        temp_path.write_text(final_json, encoding="utf-8")
        
        # atomic replace
        temp_path.replace(path)
        
        return final_payload
        
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise IOError(f"寫入 bars manifest 失敗 {path}: {e}")
    
    finally:
        # 確保暫存檔案被清理（如果 replace 成功，temp_path 已不存在）
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def load_bars_manifest(path: Path) -> Dict[str, Any]:
    """
    載入 bars manifest 並驗證 hash
    
    Args:
        path: manifest 檔案路徑
        
    Returns:
        manifest 字典
        
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或 hash 驗證失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"bars manifest 檔案不存在: {path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取 bars manifest 檔案 {path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"bars manifest JSON 解析失敗 {path}: {e}")
    
    # 驗證 manifest_sha256
    if "manifest_sha256" not in data:
        raise ValueError(f"bars manifest 缺少 manifest_sha256 欄位: {path}")
    
    # 計算實際 hash（排除 manifest_sha256 欄位）
    data_without_hash = {k: v for k, v in data.items() if k != "manifest_sha256"}
    json_str = canonical_json(data_without_hash)
    expected_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    if data["manifest_sha256"] != expected_hash:
        raise ValueError(f"bars manifest hash 驗證失敗: 預期 {expected_hash}，實際 {data['manifest_sha256']}")
    
    return data


def bars_manifest_path(outputs_root: Path, season: str, dataset_id: str) -> Path:
    """
    取得 bars manifest 檔案路徑
    
    建議位置：outputs/shared/{season}/{dataset_id}/bars/bars_manifest.json
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        
    Returns:
        檔案路徑
    """
    # 建立路徑
    path = outputs_root / "shared" / season / dataset_id / "bars" / "bars_manifest.json"
    return path


