
"""
Shared Manifest 寫入工具

提供 atomic write 與 self-hash 計算，確保 deterministic JSON 輸出。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from contracts.dimensions import canonical_json


def write_shared_manifest(payload: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """
    Writes shared_manifest.json atomically with manifest_sha256 (self hash).
    
    兩階段寫入流程：
    1. 建立不包含 manifest_sha256 的字典
    2. 計算 SHA256 hash（使用 canonical_json 確保 deterministic）
    3. 加入 manifest_sha256 欄位
    4. 原子寫入（tmp + replace）
    
    Args:
        payload: manifest 資料字典（不含 manifest_sha256）
        path: 目標檔案路徑
    
    Returns:
        最終 manifest 字典（包含 manifest_sha256）
    
    Raises:
        IOError: 寫入失敗
    """
    # 1. 確保父目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 2. 計算 manifest_sha256（使用 canonical_json 確保 deterministic）
    json_str = canonical_json(payload)
    manifest_sha256 = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    # 3. 建立最終字典（包含 manifest_sha256）
    final_payload = payload.copy()
    final_payload["manifest_sha256"] = manifest_sha256
    
    # 4. 使用 canonical_json 序列化最終字典
    final_json_str = canonical_json(final_payload)
    
    # 5. 原子寫入：先寫到暫存檔案，再移動
    temp_path = path.with_suffix(".json.tmp")
    
    try:
        # 寫入暫存檔案
        temp_path.write_text(final_json_str, encoding="utf-8")
        
        # 移動到目標位置（原子操作）
        temp_path.replace(path)
        
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        
        raise IOError(f"寫入 shared manifest 失敗 {path}: {e}")
    
    # 6. 驗證寫入的檔案可以正確讀回
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded_content = f.read()
        
        # 簡單驗證 JSON 格式
        loaded_data = json.loads(loaded_content)
        
        # 驗證 manifest_sha256 是否正確
        if loaded_data.get("manifest_sha256") != manifest_sha256:
            raise IOError(f"寫入後驗證失敗: manifest_sha256 不匹配")
        
    except Exception as e:
        # 如果驗證失敗，刪除檔案
        if path.exists():
            try:
                path.unlink()
            except:
                pass
        raise IOError(f"shared manifest 驗證失敗 {path}: {e}")
    
    return final_payload


def read_shared_manifest(path: Path) -> Dict[str, Any]:
    """
    讀取 shared manifest 並驗證 manifest_sha256
    
    Args:
        path: 檔案路徑
    
    Returns:
        manifest 字典
    
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或 hash 驗證失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"shared manifest 檔案不存在: {path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取 shared manifest 檔案 {path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"shared manifest JSON 解析失敗 {path}: {e}")
    
    # 驗證 manifest_sha256（如果存在）
    if "manifest_sha256" in data:
        # 計算實際 hash（排除 manifest_sha256 欄位）
        data_without_hash = {k: v for k, v in data.items() if k != "manifest_sha256"}
        json_str = canonical_json(data_without_hash)
        expected_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        
        if data["manifest_sha256"] != expected_hash:
            raise ValueError(f"shared manifest hash 驗證失敗: 預期 {expected_hash}，實際 {data['manifest_sha256']}")
    
    return data


def load_shared_manifest_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    """
    載入 shared manifest（如果存在）
    
    Args:
        path: 檔案路徑
    
    Returns:
        manifest 字典或 None（如果檔案不存在）
    
    Raises:
        ValueError: JSON 解析失敗或 hash 驗證失敗
    """
    if not path.exists():
        return None
    
    return read_shared_manifest(path)


