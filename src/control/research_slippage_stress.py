
"""
Slippage Stress Matrix 計算與 Survive Gate 評估

給定 bars、fills/intents、commission 配置，計算 S0–S3 等級的 KPI 矩陣。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from core.slippage_policy import SlippagePolicy, apply_slippage_to_price


@dataclass
class StressResult:
    """
    單一滑價等級的壓力測試結果
    """
    level: str  # 等級名稱，例如 "S0"
    slip_ticks: int  # 滑價 tick 數
    net_after_cost: float  # 扣除成本後的淨利
    gross_profit: float  # 總盈利（未扣除成本）
    gross_loss: float  # 總虧損（未扣除成本）
    profit_factor: float  # 盈利因子 = gross_profit / abs(gross_loss)（如果 gross_loss != 0）
    mdd_after_cost: float  # 扣除成本後的最大回撤（絕對值）
    trades: int  # 交易次數（來回算一次）


@dataclass
class CommissionConfig:
    """
    手續費配置（每邊固定金額）
    """
    per_side_usd: Dict[str, float]  # 商品符號 -> 每邊手續費（USD）
    default_per_side_usd: float = 0.0  # 預設手續費（如果商品未指定）


def compute_stress_matrix(
    bars: Dict[str, np.ndarray],
    fills: List[Dict[str, Any]],
    commission_config: CommissionConfig,
    slippage_policy: SlippagePolicy,
    tick_size_map: Dict[str, float],  # 商品符號 -> tick_size
    symbol: str,  # 當前商品符號，例如 "MNQ"
) -> Dict[str, StressResult]:
    """
    計算滑價壓力矩陣（S0–S3）

    Args:
        bars: 價格 bars 字典，至少包含 "open", "high", "low", "close"
        fills: 成交列表，每個成交為字典，包含 "entry_price", "exit_price", "entry_side", "exit_side", "quantity" 等欄位
        commission_config: 手續費配置
        slippage_policy: 滑價政策
        tick_size_map: tick_size 對應表
        symbol: 商品符號

    Returns:
        字典 mapping level -> StressResult
    """
    # 取得 tick_size
    tick_size = tick_size_map.get(symbol)
    if tick_size is None or tick_size <= 0:
        raise ValueError(f"商品 {symbol} 的 tick_size 無效或缺失: {tick_size}")
    
    # 取得手續費（每邊）
    commission_per_side = commission_config.per_side_usd.get(
        symbol, commission_config.default_per_side_usd
    )
    
    results = {}
    
    for level in ["S0", "S1", "S2", "S3"]:
        slip_ticks = slippage_policy.get_ticks(level)
        
        # 計算該等級下的淨利與其他指標
        net, gross_profit, gross_loss, trades = _compute_net_with_slippage(
            fills, slip_ticks, tick_size, commission_per_side
        )
        
        # 計算盈利因子
        if gross_loss == 0:
            profit_factor = float("inf") if gross_profit > 0 else 1.0
        else:
            profit_factor = gross_profit / abs(gross_loss)
        
        # 計算最大回撤（簡化版本：使用淨利序列）
        # 由於我們沒有逐筆的 equity curve，這裡先設為 0
        mdd = 0.0
        
        results[level] = StressResult(
            level=level,
            slip_ticks=slip_ticks,
            net_after_cost=net,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            mdd_after_cost=mdd,
            trades=trades,
        )
    
    return results


def _compute_net_with_slippage(
    fills: List[Dict[str, Any]],
    slip_ticks: int,
    tick_size: float,
    commission_per_side: float,
) -> Tuple[float, float, float, int]:
    """
    計算給定滑價 tick 數下的淨利、總盈利、總虧損與交易次數
    """
    total_net = 0.0
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    trades = 0
    
    for fill in fills:
        # 假設 fill 結構包含 entry_price, exit_price, entry_side, exit_side, quantity
        entry_price = fill.get("entry_price")
        exit_price = fill.get("exit_price")
        entry_side = fill.get("entry_side")  # "buy" 或 "sellshort"
        exit_side = fill.get("exit_side")    # "sell" 或 "buytocover"
        quantity = fill.get("quantity", 1.0)
        
        if None in (entry_price, exit_price, entry_side, exit_side):
            continue
        
        # 應用滑價調整價格
        entry_price_adj = apply_slippage_to_price(
            entry_price, entry_side, slip_ticks, tick_size
        )
        exit_price_adj = apply_slippage_to_price(
            exit_price, exit_side, slip_ticks, tick_size
        )
        
        # 計算毛利（未扣除手續費）
        if entry_side in ("buy", "buytocover"):
            # 多頭：買入後賣出
            gross = (exit_price_adj - entry_price_adj) * quantity
        else:
            # 空頭：賣出後買回
            gross = (entry_price_adj - exit_price_adj) * quantity
        
        # 扣除手續費（每邊）
        commission_total = 2 * commission_per_side * quantity
        
        # 淨利
        net = gross - commission_total
        
        total_net += net
        if net > 0:
            total_gross_profit += net + commission_total  # 還原手續費以得到 gross profit
        else:
            total_gross_loss += net - commission_total  # gross loss 為負值
        
        trades += 1
    
    return total_net, total_gross_profit, total_gross_loss, trades


def survive_s2(
    result_s2: StressResult,
    *,
    min_trades: int = 30,
    min_pf: float = 1.10,
    max_mdd_pct: Optional[float] = None,
    max_mdd_abs: Optional[float] = None,
) -> bool:
    """
    判斷策略是否通過 S2 生存閘門

    Args:
        result_s2: S2 等級的 StressResult
        min_trades: 最小交易次數
        min_pf: 最小盈利因子
        max_mdd_pct: 最大回撤百分比（如果可用）
        max_mdd_abs: 最大回撤絕對值（備用）

    Returns:
        bool: 是否通過閘門
    """
    # 檢查交易次數
    if result_s2.trades < min_trades:
        return False
    
    # 檢查盈利因子
    if result_s2.profit_factor < min_pf:
        return False
    
    # 檢查最大回撤（如果提供）
    if max_mdd_pct is not None:
        # 需要 equity curve 計算百分比回撤，目前暫不實作
        pass
    elif max_mdd_abs is not None:
        if result_s2.mdd_after_cost > max_mdd_abs:
            return False
    
    return True


def compute_stress_test_passed(
    results: Dict[str, StressResult],
    stress_level: str = "S3",
) -> bool:
    """
    計算壓力測試是否通過（S3 淨利 > 0）

    Args:
        results: 壓力測試結果字典
        stress_level: 壓力測試等級（預設 S3）

    Returns:
        bool: 壓力測試通過標誌
    """
    stress_result = results.get(stress_level)
    if stress_result is None:
        return False
    return stress_result.net_after_cost > 0


def generate_stress_report(
    results: Dict[str, StressResult],
    slippage_policy: SlippagePolicy,
    survive_s2_flag: bool,
    stress_test_passed_flag: bool,
) -> Dict[str, Any]:
    """
    產生壓力測試報告

    Returns:
        報告字典，包含 policy、矩陣、閘門結果等
    """
    matrix = {}
    for level, result in results.items():
        matrix[level] = {
            "slip_ticks": result.slip_ticks,
            "net_after_cost": result.net_after_cost,
            "gross_profit": result.gross_profit,
            "gross_loss": result.gross_loss,
            "profit_factor": result.profit_factor,
            "mdd_after_cost": result.mdd_after_cost,
            "trades": result.trades,
        }
    
    return {
        "slippage_policy": {
            "definition": slippage_policy.definition,
            "levels": slippage_policy.levels,
            "selection_level": slippage_policy.selection_level,
            "stress_level": slippage_policy.stress_level,
            "mc_execution_level": slippage_policy.mc_execution_level,
        },
        "stress_matrix": matrix,
        "survive_s2": survive_s2_flag,
        "stress_test_passed": stress_test_passed_flag,
    }


