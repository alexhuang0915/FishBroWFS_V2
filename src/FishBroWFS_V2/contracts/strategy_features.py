
# src/FishBroWFS_V2/contracts/strategy_features.py
"""
Strategy Feature Declaration 合約

定義策略特徵需求的統一格式，讓 resolver 能夠解析與驗證。
"""

from __future__ import annotations

import json
from typing import List, Optional
from pydantic import BaseModel, Field


class FeatureRef(BaseModel):
    """
    單一特徵引用
    
    Attributes:
        name: 特徵名稱，例如 "atr_14", "ret_z_200", "session_vwap"
        timeframe_min: timeframe 分鐘數，例如 15, 30, 60, 120, 240
    """
    name: str = Field(..., description="特徵名稱")
    timeframe_min: int = Field(..., description="timeframe 分鐘數 (15, 30, 60, 120, 240)")


class StrategyFeatureRequirements(BaseModel):
    """
    策略特徵需求
    
    Attributes:
        strategy_id: 策略 ID
        required: 必需的特徵列表
        optional: 可選的特徵列表（預設為空）
        min_schema_version: 最小 schema 版本（預設 "v1"）
        notes: 備註（預設為空字串）
    """
    strategy_id: str = Field(..., description="策略 ID")
    required: List[FeatureRef] = Field(..., description="必需的特徵列表")
    optional: List[FeatureRef] = Field(default_factory=list, description="可選的特徵列表")
    min_schema_version: str = Field(default="v1", description="最小 schema 版本")
    notes: str = Field(default="", description="備註")


def canonical_json_requirements(req: StrategyFeatureRequirements) -> str:
    """
    產生 deterministic JSON 字串
    
    使用 sort_keys=True 確保字典順序穩定，separators 移除多餘空白。
    
    Args:
        req: StrategyFeatureRequirements 實例
    
    Returns:
        deterministic JSON 字串
    """
    # 轉換為字典（使用 pydantic 的 dict 方法）
    data = req.model_dump()
    
    # 使用與其他 contracts 一致的 canonical_json 格式
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def load_requirements_from_json(json_path: str) -> StrategyFeatureRequirements:
    """
    從 JSON 檔案載入策略特徵需求
    
    Args:
        json_path: JSON 檔案路徑
    
    Returns:
        StrategyFeatureRequirements 實例
    
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或驗證失敗
    """
    import json
    from pathlib import Path
    
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"需求檔案不存在: {json_path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取需求檔案 {json_path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"需求 JSON 解析失敗 {json_path}: {e}")
    
    try:
        return StrategyFeatureRequirements(**data)
    except Exception as e:
        raise ValueError(f"需求資料驗證失敗 {json_path}: {e}")


def save_requirements_to_json(
    req: StrategyFeatureRequirements,
    json_path: str,
) -> None:
    """
    將策略特徵需求儲存為 JSON 檔案
    
    Args:
        req: StrategyFeatureRequirements 實例
        json_path: JSON 檔案路徑
    
    Raises:
        ValueError: 寫入失敗
    """
    import json
    from pathlib import Path
    
    path = Path(json_path)
    
    # 建立目錄（如果不存在）
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 使用 canonical JSON 格式
    json_str = canonical_json_requirements(req)
    
    try:
        path.write_text(json_str, encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法寫入需求檔案 {json_path}: {e}")


