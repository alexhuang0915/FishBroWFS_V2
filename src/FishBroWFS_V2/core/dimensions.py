
# src/FishBroWFS_V2/core/dimensions.py
"""
穩定的維度查詢介面

提供 get_dimension_for_dataset() 函數，用於查詢商品的維度定義（交易時段、交易所等）。
此模組使用 lazy loading 避免 import-time IO，並提供 deterministic 結果。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from FishBroWFS_V2.contracts.dimensions import InstrumentDimension
from FishBroWFS_V2.contracts.dimensions_loader import load_dimension_registry


@lru_cache(maxsize=1)
def _get_cached_registry():
    """
    快取註冊表，避免重複讀取檔案
    
    使用 lru_cache(maxsize=1) 確保：
    1. 第一次呼叫時讀取檔案
    2. 後續呼叫重用快取
    3. 避免 import-time IO
    """
    return load_dimension_registry()


def get_dimension_for_dataset(
    dataset_id: str, 
    *, 
    symbol: str | None = None
) -> InstrumentDimension | None:
    """
    查詢資料集的維度定義
    
    Args:
        dataset_id: 資料集 ID，例如 "CME.MNQ.60m.2020-2024"
        symbol: 可選的商品符號，例如 "CME.MNQ"
    
    Returns:
        InstrumentDimension 或 None（如果找不到）
    
    Note:
        - 純讀取操作，無副作用（除了第一次呼叫時的檔案讀取）
        - 結果是 deterministic 的
        - 使用 lazy loading，避免 import-time IO
    """
    registry = _get_cached_registry()
    return registry.get(dataset_id, symbol)


def clear_dimension_cache() -> None:
    """
    清除維度快取
    
    主要用於測試，或需要強制重新讀取註冊表的情況
    """
    _get_cached_registry.cache_clear()


