
"""
Feature Registry 合約

定義特徵規格與註冊表，支援 deterministic 查詢與 lookback 計算。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
# from config.registry.timeframes import load_timeframes # REMOVED (Legacy)
from contracts.timeframes_registry import load_timeframes


class FeatureSpec(BaseModel):
    """
    單一特徵規格
    
    Attributes:
        name: 特徵名稱（例如 "atr_14"）
        timeframe_min: 適用的 timeframe 分鐘數（必須來自 timeframe registry）
        lookback_bars: 計算所需的最大 lookback bar 數（例如 ATR(14) 需要 14）
        params: 參數字典（例如 {"window": 14, "method": "log"}）
        window: 滾動視窗大小（window=1 表示非視窗特徵）
        min_warmup_bars: 暖機所需的最小 bar 數（暖機期間輸出 NaN）
        dtype: 輸出資料型別（目前僅支援 float64）
        div0_policy: 除零處理策略（目前僅支援 DIV0_RET_NAN）
        family: 特徵家族（可選，例如 "ma", "volatility", "momentum"）
    """
    name: str
    timeframe_min: int
    lookback_bars: int = Field(default=0, ge=0)
    params: Dict[str, str | int | float] = Field(default_factory=dict)
    window: int = Field(default=1, ge=1)
    min_warmup_bars: int = Field(default=0, ge=0)
    dtype: Literal["float64"] = Field(default="float64")
    div0_policy: Literal["DIV0_RET_NAN"] = Field(default="DIV0_RET_NAN")
    family: Optional[str] = Field(default=None)


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
            tf_min: timeframe 分鐘數（必須來自 timeframe registry）
            
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
    
    每個特徵都適用於所有 timeframe（來自 timeframe registry）
    """
    # Use timeframe registry for deterministic timeframes
    timeframes = load_timeframes().allowed_timeframes
    
    specs = []
    
    for tf in timeframes:
        # atr_14
        specs.append(FeatureSpec(
            name="atr_14",
            timeframe_min=tf,
            lookback_bars=14,
            params={"window": 14},
            window=14,
            min_warmup_bars=14,
            dtype="float64",
            div0_policy="DIV0_RET_NAN",
            family="volatility"
        ))
        
        # ret_z_200
        specs.append(FeatureSpec(
            name="ret_z_200",
            timeframe_min=tf,
            lookback_bars=200,
            params={"window": 200, "method": "log"},
            window=200,
            min_warmup_bars=200,
            dtype="float64",
            div0_policy="DIV0_RET_NAN",
            family="return"
        ))
        
        # session_vwap
        specs.append(FeatureSpec(
            name="session_vwap",
            timeframe_min=tf,
            lookback_bars=0,
            params={},
            window=1,
            min_warmup_bars=0,
            dtype="float64",
            div0_policy="DIV0_RET_NAN",
            family="session"
        ))
    
    return FeatureRegistry(specs=specs)

