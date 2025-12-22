
# src/FishBroWFS_V2/contracts/dimensions_loader.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.contracts.dimensions import DimensionRegistry, canonical_json


def default_registry_path() -> Path:
    """
    取得預設維度註冊表檔案路徑
    
    Returns:
        Path 物件指向 configs/dimensions_registry.json
    """
    # 從專案根目錄開始
    project_root = Path(__file__).parent.parent.parent
    return project_root / "configs" / "dimensions_registry.json"


def load_dimension_registry(path: Path | None = None) -> DimensionRegistry:
    """
    載入維度註冊表
    
    Args:
        path: 註冊表檔案路徑，若為 None 則使用預設路徑
    
    Returns:
        DimensionRegistry 物件
    
    Raises:
        ValueError: 檔案存在但 JSON 解析失敗或 schema 驗證失敗
        FileNotFoundError: 不會引發，檔案不存在時回傳空註冊表
    """
    if path is None:
        path = default_registry_path()
    
    # 檔案不存在 -> 回傳空註冊表
    if not path.exists():
        return DimensionRegistry()
    
    # 讀取檔案內容
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取維度註冊表檔案 {path}: {e}")
    
    # 解析 JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"維度註冊表 JSON 解析失敗 {path}: {e}")
    
    # 驗證並建立 DimensionRegistry
    try:
        # 確保有必要的鍵
        if not isinstance(data, dict):
            raise ValueError("根節點必須是字典")
        
        # 建立 registry，pydantic 會驗證 schema
        registry = DimensionRegistry(**data)
        return registry
    except Exception as e:
        raise ValueError(f"維度註冊表 schema 驗證失敗 {path}: {e}")


def write_dimension_registry(registry: DimensionRegistry, path: Path | None = None) -> None:
    """
    寫入維度註冊表（原子寫入）
    
    Args:
        registry: 要寫入的 DimensionRegistry
        path: 目標檔案路徑，若為 None 則使用預設路徑
    
    Note:
        使用原子寫入（tmp + replace）避免寫入過程中斷
    """
    if path is None:
        path = default_registry_path()
    
    # 確保目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 轉換為字典並標準化 JSON
    data = registry.model_dump()
    json_str = canonical_json(data)
    
    # 原子寫入：先寫到暫存檔案，再移動
    temp_path = path.with_suffix(".json.tmp")
    try:
        temp_path.write_text(json_str, encoding="utf-8")
        temp_path.replace(path)
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        raise IOError(f"寫入維度註冊表失敗 {path}: {e}")


