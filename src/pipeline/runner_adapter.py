
"""Runner adapter for funnel pipeline.

Provides unified interface to existing runners without exposing engine details.
Adapter returns data only (no file I/O) - all file writing is done by artifacts system.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from pipeline.runner_grid import run_grid
from pipeline.stage0_runner import run_stage0
from pipeline.stage2_runner import run_stage2
from pipeline.topk import select_topk


def _coerce_1d_float64(x):
    if isinstance(x, np.ndarray):
        return x.astype(np.float64, copy=False)
    return np.asarray(x, dtype=np.float64)


def _coerce_2d_float64(x):
    if isinstance(x, np.ndarray):
        return x.astype(np.float64, copy=False)
    return np.asarray(x, dtype=np.float64)


def _coerce_arrays(cfg: dict) -> dict:
    # in-place is ok (stage_cfg is per-stage copy anyway)
    if "open_" in cfg:
        cfg["open_"] = _coerce_1d_float64(cfg["open_"])
    if "high" in cfg:
        cfg["high"] = _coerce_1d_float64(cfg["high"])
    if "low" in cfg:
        cfg["low"] = _coerce_1d_float64(cfg["low"])
    if "close" in cfg:
        cfg["close"] = _coerce_1d_float64(cfg["close"])
    if "params_matrix" in cfg:
        cfg["params_matrix"] = _coerce_2d_float64(cfg["params_matrix"])
    return cfg


def run_stage_job(stage_cfg: dict) -> dict:
    """
    Run a stage job and return metrics and winners.
    
    This adapter wraps existing runners (run_grid, run_stage0, run_stage2)
    to provide a unified interface. It does NOT write any files - all file
    writing must be done by the artifacts system.
    
    Args:
        stage_cfg: Stage configuration dictionary containing:
            - stage_name: Stage identifier ("stage0_coarse", "stage1_topk", "stage2_confirm")
            - param_subsample_rate: Subsample rate for this stage
            - topk: Optional top-K count (for Stage0/1)
            - open_, high, low, close: OHLC arrays
            - params_matrix: Parameter matrix
            - commission: Commission per trade (REQUIRED, no default)
            - slip: Slippage per trade (REQUIRED, no default)
            - order_qty: Order quantity (default: 1)
            - Other stage-specific parameters
    
    Returns:
        Dictionary with:
        - metrics: dict containing performance metrics
        - winners: dict with schema {"topk": [...], "notes": {"schema": "v1", ...}}
    
    Note:
        - This function does NOT write any files
        - All file writing must be done by core/artifacts.py
        - Returns data only for artifact system to consume
    """
    stage_cfg = _coerce_arrays(stage_cfg)
    
    stage_name = stage_cfg.get("stage_name", "")
    
    if stage_name == "stage0_coarse":
        return _run_stage0_job(stage_cfg)
    elif stage_name == "stage1_topk":
        return _run_stage1_job(stage_cfg)
    elif stage_name == "stage2_confirm":
        return _run_stage2_job(stage_cfg)
    else:
        raise ValueError(f"Unknown stage_name: {stage_name}")


def _run_stage0_job(cfg: dict) -> dict:
    """Run Stage0 coarse exploration job."""
    close = cfg["close"]
    params_matrix = cfg["params_matrix"]
    proxy_name = cfg.get("proxy_name", "ma_proxy_v0")
    
    # Apply subsample if needed
    param_subsample_rate = cfg.get("param_subsample_rate", 1.0)
    seed = cfg.get("subsample_seed", 42)
    if param_subsample_rate < 1.0:
        n_total = params_matrix.shape[0]
        n_effective = int(n_total * param_subsample_rate)
        # Deterministic selection (use seed from config if available)
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n_total)
        selected_indices = np.sort(perm[:n_effective])
        params_matrix = params_matrix[selected_indices]
    
    # Run Stage0
    stage0_results = run_stage0(close, params_matrix, proxy_name=proxy_name)
    
    # Extract metrics
    metrics = {
        "params_total": cfg.get("params_total", params_matrix.shape[0]),
        "params_effective": len(stage0_results),
        "bars": len(close),
        "stage_name": "stage0_coarse",
    }
    
    # Convert to winners format
    topk = cfg.get("topk", 50)
    topk_param_ids = select_topk(stage0_results, k=topk)
    
    winners = {
        "topk": [
            {
                "param_id": int(r.param_id),
                "proxy_value": float(r.proxy_value),
            }
            for r in stage0_results
            if r.param_id in topk_param_ids
        ],
        "notes": {
            "schema": "v1",
            "stage": "stage0_coarse",
            "topk_count": len(topk_param_ids),
        },
    }
    
    return {"metrics": metrics, "winners": winners}


def _run_stage1_job(cfg: dict) -> dict:
    """Run Stage1 Top-K refinement job."""
    # Stage1 uses grid runner with increased subsample
    open_ = cfg["open_"]
    high = cfg["high"]
    low = cfg["low"]
    close = cfg["close"]
    params_matrix = cfg["params_matrix"]
    
    # Commission and slippage must be provided by caller (no defaults)
    # According to Config Constitution v1, cost models are mandatory in profiles
    commission = cfg.get("commission")
    slip = cfg.get("slip")
    
    if commission is None:
        raise ValueError("commission must be provided in stage configuration")
    if slip is None:
        raise ValueError("slip must be provided in stage configuration")
    
    order_qty = cfg.get("order_qty", 1)
    
    param_subsample_rate = cfg.get("param_subsample_rate", 1.0)
    seed = cfg.get("subsample_seed", 42)
    
    # Apply subsample
    if param_subsample_rate < 1.0:
        n_total = params_matrix.shape[0]
        n_effective = int(n_total * param_subsample_rate)
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n_total)
        selected_indices = np.sort(perm[:n_effective])
        params_matrix = params_matrix[selected_indices]
    
    # Run grid
    result = run_grid(
        open_,
        high,
        low,
        close,
        params_matrix,
        commission=commission,
        slip=slip,
        order_qty=order_qty,
        sort_params=True,
        param_subsample_seed=seed,
    )
    
    metrics_array = result.get("metrics", np.array([]))
    perf = result.get("perf", {})
    
    # Extract metrics
    metrics = {
        "params_total": cfg.get("params_total", params_matrix.shape[0]),
        "params_effective": metrics_array.shape[0] if metrics_array.size > 0 else 0,
        "bars": len(close),
        "stage_name": "stage1_topk",
    }
    
    if isinstance(perf, dict):
        runtime_s = perf.get("t_total_s", 0.0)
        if runtime_s:
            metrics["runtime_s"] = float(runtime_s)
    
    # Select top-K
    topk = cfg.get("topk", 20)
    if metrics_array.size > 0:
        # Sort by net_profit (column 0)
        net_profits = metrics_array[:, 0]
        top_indices = np.argsort(net_profits)[::-1][:topk]
        
        winners_list = []
        for idx in top_indices:
            winners_list.append({
                "param_id": int(idx),
                "net_profit": float(metrics_array[idx, 0]),
                "trades": int(metrics_array[idx, 1]),
                "max_dd": float(metrics_array[idx, 2]),
            })
    else:
        winners_list = []
    
    winners = {
        "topk": winners_list,
        "notes": {
            "schema": "v1",
            "stage": "stage1_topk",
            "topk_count": len(winners_list),
        },
    }
    
    return {"metrics": metrics, "winners": winners}


def _run_stage2_job(cfg: dict) -> dict:
    """Run Stage2 full confirmation job."""
    open_ = cfg["open_"]
    high = cfg["high"]
    low = cfg["low"]
    close = cfg["close"]
    params_matrix = cfg["params_matrix"]
    
    # Commission and slippage must be provided by caller (no defaults)
    # According to Config Constitution v1, cost models are mandatory in profiles
    commission = cfg.get("commission")
    slip = cfg.get("slip")
    
    if commission is None:
        raise ValueError("commission must be provided in stage configuration")
    if slip is None:
        raise ValueError("slip must be provided in stage configuration")
    
    order_qty = cfg.get("order_qty", 1)
    
    # Stage2 must use all params (subsample_rate = 1.0)
    # Get top-K from previous stage if available
    prev_winners = cfg.get("prev_stage_winners", [])
    if prev_winners:
        param_ids = [w.get("param_id") for w in prev_winners if "param_id" in w]
    else:
        # Fallback: use all params
        param_ids = list(range(params_matrix.shape[0]))
    
    # Run Stage2
    stage2_results = run_stage2(
        open_,
        high,
        low,
        close,
        params_matrix,
        param_ids,
        commission=commission,
        slip=slip,
        order_qty=order_qty,
    )
    
    # Extract metrics
    metrics = {
        "params_total": cfg.get("params_total", params_matrix.shape[0]),
        "params_effective": len(stage2_results),
        "bars": len(close),
        "stage_name": "stage2_confirm",
    }
    
    # Convert to winners format
    winners_list = []
    for r in stage2_results:
        winners_list.append({
            "param_id": int(r.param_id),
            "net_profit": float(r.net_profit),
            "trades": int(r.trades),
            "max_dd": float(r.max_dd),
        })
    
    winners = {
        "topk": winners_list,
        "notes": {
            "schema": "v1",
            "stage": "stage2_confirm",
            "full_confirm": True,
        },
    }
    
    return {"metrics": metrics, "winners": winners}


