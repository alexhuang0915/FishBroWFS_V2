
# src/FishBroWFS_V2/contracts/features.py
"""
Feature Registry 合約

定義特徵規格與註冊表，支援 deterministic 查詢與 lookback 計算。
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class FeatureSpec(BaseModel):
    """
    單一特徵規格
    
    Attributes:
        name: 特徵名稱（例如 "atr_14"）
        timeframe_min: 適用的 timeframe 分鐘數（15, 30, 60, 120, 240）
        lookback_bars: 計算所需的最大 lookback bar 數（例如 ATR(14) 需要 14）
        params: 參數字典（例如 {"window": 14, "method": "log"}）
    """
    name: str
    timeframe_min: int
    lookback_bars: int = Field(default=0, ge=0)
    params: Dict[str, str | int | float] = Field(default_factory=dict)


class FeatureRegistry(BaseModel):
    """
    特徵註冊表
    
    管理所有特徵規格，提供按 timeframe 查詢與 lookback 計算。
    """
    specs: List[FeatureSpec] = Field(default_factory=list)
    
    def specs_for_tf(self, tf_min: int) -> List[FeatureSpec]:
        """
        取得適用於指定 timeframe 的所有特徵規格
        
        Args:
            tf_min: timeframe 分鐘數（15, 30, 60, 120, 240）
            
        Returns:
            特徵規格列表（按 name 排序以確保 deterministic）
        """
        filtered = [spec for spec in self.specs if spec.timeframe_min == tf_min]
        # 按 name 排序以確保 deterministic
        return sorted(filtered, key=lambda s: s.name)
    
    def max_lookback_for_tf(self, tf_min: int) -> int:
        """
        計算指定 timeframe 的最大 lookback bar 數
        
        Args:
            tf_min: timeframe 分鐘數
            
        Returns:
            最大 lookback bar 數（如果沒有特徵則回傳 0）
        """
        specs = self.specs_for_tf(tf_min)
        if not specs:
            return 0
        return max(spec.lookback_bars for spec in specs)


def default_feature_registry() -> FeatureRegistry:
    """
    建立預設特徵註冊表（寫死 3 個共享特徵）
    
    特徵定義：
    1. atr_14: ATR(14), lookback=14
    2. ret_z_200: returns z-score (window=200), lookback=200
    3. session_vwap: session VWAP, lookback=0
    
    每個特徵都適用於所有 timeframe（15, 30, 60, 120, 240）
    """
    # 所有支援的 timeframe
    timeframes = [15, 30, 60, 120, 240]
    
    specs = []
    
    for tf in timeframes:
        # atr_14
        specs.append(FeatureSpec(
            name="atr_14",
            timeframe_min=tf,
            lookback_bars=14,
            params={"window": 14}
        ))
        
        # ret_z_200
        specs.append(FeatureSpec(
            name="ret_z_200",
            timeframe_min=tf,
            lookback_bars=200,
            params={"window": 200, "method": "log"}
        ))
        
        # session_vwap
        specs.append(FeatureSpec(
            name="session_vwap",
            timeframe_min=tf,
            lookback_bars=0,
            params={}
        ))
    
    return FeatureRegistry(specs=specs)


