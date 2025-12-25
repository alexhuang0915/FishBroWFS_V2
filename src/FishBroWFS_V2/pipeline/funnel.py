
"""Funnel orchestrator - Stage0 → Top-K → Stage2 pipeline.

This is the main entry point for the Phase 4 Funnel pipeline.
It orchestrates the complete flow: proxy ranking → selection → full backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from FishBroWFS_V2.config.constants import TOPK_K
from FishBroWFS_V2.pipeline.stage0_runner import Stage0Result, run_stage0
from FishBroWFS_V2.pipeline.stage2_runner import Stage2Result, run_stage2
from FishBroWFS_V2.pipeline.topk import select_topk


@dataclass(frozen=True)
class FunnelResult:
    """
    Complete funnel pipeline result.
    
    Contains:
    - stage0_results: all Stage0 proxy ranking results
    - topk_param_ids: selected Top-K parameter indices
    - stage2_results: full backtest results for Top-K parameters
    - meta: optional metadata
    """
    stage0_results: List[Stage0Result]
    topk_param_ids: List[int]
    stage2_results: List[Stage2Result]
    meta: Optional[dict] = None


import warnings


def run_funnel(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
    *,
    k: int = TOPK_K,
    commission: float = 0.0,
    slip: float = 0.0,
    order_qty: int = 1,
    proxy_name: str = "ma_proxy_v0",
) -> FunnelResult:
    """
    [DEPRECATED] Run complete Funnel pipeline: Stage0 → Top-K → Stage2.
    
    This function is deprecated in favor of `FishBroWFS_V2.pipeline.funnel_runner.run_funnel`.
    The new implementation provides better audit logging, artifact writing, and OOM gating.
    
    Pipeline flow (fixed):
    1. Stage0: proxy ranking on all parameters
    2. Top-K: select top K parameters based on proxy_value
    3. Stage2: full backtest on Top-K subset
    
    Args:
        open_, high, low, close: OHLC arrays (float64, 1D, same length)
        params_matrix: float64 2D array (n_params, >=3)
            - For Stage0: uses col0 (fast_len), col1 (slow_len) for MA proxy
            - For Stage2: uses col0 (channel_len), col1 (atr_len), col2 (stop_mult) for kernel
        k: number of top parameters to select (default: TOPK_K)
        commission: commission per trade (absolute)
        slip: slippage per trade (absolute)
        order_qty: order quantity (default: 1)
        proxy_name: name of proxy to use for Stage0 (default: ma_proxy_v0)
        
    Returns:
        FunnelResult containing:
        - stage0_results: all proxy ranking results
        - topk_param_ids: selected Top-K parameter indices
        - stage2_results: full backtest results for Top-K only
        
    Note:
        - Pipeline is deterministic: same input produces same output
        - Stage0 does NOT compute PnL metrics (only proxy_value)
        - Top-K selection is based solely on proxy_value
        - Stage2 runs full backtest only on Top-K subset
        - DEPRECATED: Use `FishBroWFS_V2.pipeline.funnel_runner.run_funnel` instead
    """
    warnings.warn(
        "pipeline.funnel.run_funnel is deprecated. "
        "Use pipeline.funnel_runner.run_funnel instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # Step 1: Stage0 - proxy ranking
    stage0_results = run_stage0(
        close,
        params_matrix,
        proxy_name=proxy_name,
    )
    
    # Step 2: Top-K selection
    topk_param_ids = select_topk(stage0_results, k=k)
    
    # Step 3: Stage2 - full backtest on Top-K
    stage2_results = run_stage2(
        open_,
        high,
        low,
        close,
        params_matrix,
        topk_param_ids,
        commission=commission,
        slip=slip,
        order_qty=order_qty,
    )
    
    return FunnelResult(
        stage0_results=stage0_results,
        topk_param_ids=topk_param_ids,
        stage2_results=stage2_results,
        meta=None,
    )


