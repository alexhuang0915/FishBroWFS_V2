
# src/FishBroWFS_V2/core/slippage_policy.py
"""
SlippagePolicy：滑價成本模型定義

定義 per fill/per side 的滑價等級，並提供價格調整函數。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Dict, Optional
import math


@dataclass(frozen=True)
class SlippagePolicy:
    """
    滑價政策定義

    Attributes:
        definition: 滑價定義，固定為 "per_fill_per_side"
        levels: 滑價等級對應的 tick 數，預設為 S0=0, S1=1, S2=2, S3=3
        selection_level: 策略選擇使用的滑價等級（預設 S2）
        stress_level: 壓力測試使用的滑價等級（預設 S3）
        mc_execution_level: MultiCharts 執行時使用的滑價等級（預設 S1）
    """
    definition: str = "per_fill_per_side"
    levels: Dict[str, int] = field(default_factory=lambda: {"S0": 0, "S1": 1, "S2": 2, "S3": 3})
    selection_level: str = "S2"
    stress_level: str = "S3"
    mc_execution_level: str = "S1"

    def __post_init__(self):
        """驗證欄位"""
        if self.definition != "per_fill_per_side":
            raise ValueError(f"definition 必須為 'per_fill_per_side'，收到: {self.definition}")
        
        required_levels = {"S0", "S1", "S2", "S3"}
        if not required_levels.issubset(self.levels.keys()):
            missing = required_levels - set(self.levels.keys())
            raise ValueError(f"levels 缺少必要等級: {missing}")
        
        for level in (self.selection_level, self.stress_level, self.mc_execution_level):
            if level not in self.levels:
                raise ValueError(f"等級 {level} 不存在於 levels 中")
        
        # 確保 tick 數為非負整數
        for level, ticks in self.levels.items():
            if not isinstance(ticks, int) or ticks < 0:
                raise ValueError(f"等級 {level} 的 ticks 必須為非負整數，收到: {ticks}")

    def get_ticks(self, level: str) -> int:
        """
        取得指定等級的滑價 tick 數

        Args:
            level: 等級名稱，例如 "S2"

        Returns:
            滑價 tick 數

        Raises:
            KeyError: 等級不存在
        """
        return self.levels[level]

    def get_selection_ticks(self) -> int:
        """取得 selection_level 對應的 tick 數"""
        return self.get_ticks(self.selection_level)

    def get_stress_ticks(self) -> int:
        """取得 stress_level 對應的 tick 數"""
        return self.get_ticks(self.stress_level)

    def get_mc_execution_ticks(self) -> int:
        """取得 mc_execution_level 對應的 tick 數"""
        return self.get_ticks(self.mc_execution_level)


def apply_slippage_to_price(
    price: float,
    side: Literal["buy", "sell", "sellshort", "buytocover"],
    slip_ticks: int,
    tick_size: float,
) -> float:
    """
    根據滑價 tick 數調整價格

    規則：
    - 買入（buy, buytocover）：價格增加 slip_ticks * tick_size
    - 賣出（sell, sellshort）：價格減少 slip_ticks * tick_size

    Args:
        price: 原始價格
        side: 交易方向
        slip_ticks: 滑價 tick 數（非負整數）
        tick_size: 每 tick 價格變動量（必須 > 0）

    Returns:
        調整後的價格

    Raises:
        ValueError: 參數無效
    """
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    if slip_ticks < 0:
        raise ValueError(f"slip_ticks 必須 >= 0，收到: {slip_ticks}")
    
    # 計算滑價金額
    slippage_amount = slip_ticks * tick_size
    
    # 根據方向調整
    if side in ("buy", "buytocover"):
        # 買入：支付更高價格
        adjusted = price + slippage_amount
    elif side in ("sell", "sellshort"):
        # 賣出：收到更低價格
        adjusted = price - slippage_amount
    else:
        raise ValueError(f"無效的 side: {side}，必須為 buy/sell/sellshort/buytocover")
    
    # 確保價格非負（雖然理論上可能為負，但實務上不應發生）
    if adjusted < 0:
        adjusted = 0.0
    
    return adjusted


def round_to_tick(price: float, tick_size: float) -> float:
    """
    將價格四捨五入至最近的 tick 邊界

    Args:
        price: 原始價格
        tick_size: tick 大小

    Returns:
        四捨五入後的價格
    """
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    
    # 計算 tick 數
    ticks = round(price / tick_size)
    return ticks * tick_size


def compute_slippage_cost_per_side(
    slip_ticks: int,
    tick_size: float,
    quantity: float = 1.0,
) -> float:
    """
    計算單邊滑價成本（每單位）

    Args:
        slip_ticks: 滑價 tick 數
        tick_size: tick 大小
        quantity: 數量（預設 1.0）

    Returns:
        滑價成本（正數）
    """
    if slip_ticks < 0:
        raise ValueError(f"slip_ticks 必須 >= 0，收到: {slip_ticks}")
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    
    return slip_ticks * tick_size * quantity


def compute_round_trip_slippage_cost(
    slip_ticks: int,
    tick_size: float,
    quantity: float = 1.0,
) -> float:
    """
    計算來回交易（entry + exit）的總滑價成本

    由於每邊都會產生滑價，總成本為 2 * slip_ticks * tick_size * quantity

    Args:
        slip_ticks: 每邊滑價 tick 數
        tick_size: tick 大小
        quantity: 數量

    Returns:
        總滑價成本
    """
    per_side = compute_slippage_cost_per_side(slip_ticks, tick_size, quantity)
    return 2.0 * per_side


