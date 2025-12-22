
"""
Stage P2-1.8: Contract Tests for Granular Breakdown and Extended Observability

Tests that verify:
- Granular timing keys exist and are non-negative floats
- Extended observability keys exist (entry/exit intents/fills totals)
- Accounting consistency (intents_total == entry + exit, fills_total == entry + exit)
- run_grid output contains timing keys in perf dict
"""
from __future__ import annotations

import os
import numpy as np

from FishBroWFS_V2.strategy.kernel import run_kernel_arrays, DonchianAtrParams
from FishBroWFS_V2.engine.types import BarArrays
from FishBroWFS_V2.pipeline.runner_grid import run_grid


def test_perf_breakdown_keys_existence() -> None:
    """
    D1: Contract test - Verify granular timing keys exist in _obs and are floats >= 0.0
    Also verify that t_total_kernel_s >= max(stage_times) for sanity check.
    
    Contract: keys always exist, values always float >= 0.0.
    (When perf harness runs with profiling enabled, these will naturally become >0 real data.)
    """
    import os
    # Ensure clean environment for test
    old_trigger_rate = os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    # Task 2: Kernel profiling is optional - keys will always exist (may be 0.0 if not profiled)
    # We can optionally enable profiling to get real timing data, but it's not required for contract
    old_profile_kernel = os.environ.get("FISHBRO_PROFILE_KERNEL")
    # Optionally enable profiling to get real timing values (not required - keys exist regardless)
    # Uncomment the line below if you want to test with profiling enabled:
    # os.environ["FISHBRO_PROFILE_KERNEL"] = "1"
    
    try:
        n_bars = 200
        warmup = 20
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        bars = BarArrays(
            open=open_.astype(np.float64),
            high=high.astype(np.float64),
            low=low.astype(np.float64),
            close=close.astype(np.float64),
        )
        
        params = DonchianAtrParams(channel_len=warmup, atr_len=10, stop_mult=1.0)
        
        result = run_kernel_arrays(
            bars=bars,
            params=params,
            commission=0.0,
            slip=0.0,
            order_qty=1,
        )
        
        # Verify _obs exists and contains timing keys
        assert "_obs" in result, "_obs must exist in kernel result"
        obs = result["_obs"]
        assert isinstance(obs, dict), "_obs must be a dict"
        
        # Required timing keys (now in _obs, not _perf)
        # Task 2: Contract - keys always exist, values always float >= 0.0
        timing_keys = [
            "t_calc_indicators_s",
            "t_build_entry_intents_s",
            "t_simulate_entry_s",
            "t_calc_exits_s",
            "t_simulate_exit_s",
            "t_total_kernel_s",
        ]
        
        stage_times = []
        for key in timing_keys:
            assert key in obs, f"{key} must exist in _obs (keys always exist, even if 0.0)"
            value = obs[key]
            assert isinstance(value, float), f"{key} must be float, got {type(value)}"
            assert value >= 0.0, f"{key} must be >= 0.0, got {value}"
            if key != "t_total_kernel_s":
                stage_times.append(value)
        
        # Sanity check: total time should be >= max of individual stage times
        # (allowing some overhead for timer calls and other operations)
        # Note: This check only makes sense if profiling was enabled (values > 0)
        t_total = obs["t_total_kernel_s"]
        if stage_times and t_total > 0.0:
            max_stage = max(stage_times)
            # Allow equality or small overhead
            assert t_total >= max_stage, (
                f"t_total_kernel_s ({t_total}) should be >= max(stage_times) ({max_stage})"
            )
    finally:
        # Restore environment
        # restore trigger rate
        if old_trigger_rate is None:
            os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
        else:
            os.environ["FISHBRO_PERF_TRIGGER_RATE"] = old_trigger_rate
        
        # restore kernel profiling flag
        if old_profile_kernel is None:
            os.environ.pop("FISHBRO_PROFILE_KERNEL", None)
        else:
            os.environ["FISHBRO_PROFILE_KERNEL"] = old_profile_kernel


def test_extended_observability_keys_existence() -> None:
    """
    D1: Contract test - Verify extended observability keys exist in _obs
    """
    import os
    # Ensure clean environment for test
    old_trigger_rate = os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    
    try:
        n_bars = 200
        warmup = 20
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        bars = BarArrays(
            open=open_.astype(np.float64),
            high=high.astype(np.float64),
            low=low.astype(np.float64),
            close=close.astype(np.float64),
        )
        
        params = DonchianAtrParams(channel_len=warmup, atr_len=10, stop_mult=1.0)
        
        result = run_kernel_arrays(
            bars=bars,
            params=params,
            commission=0.0,
            slip=0.0,
            order_qty=1,
        )
        
        # Verify _obs exists and contains extended keys
        assert "_obs" in result, "_obs must exist in kernel result"
        obs = result["_obs"]
        assert isinstance(obs, dict), "_obs must be a dict"
        
        # Required observability keys
        obs_keys = [
            "entry_intents_total",
            "entry_fills_total",
            "exit_intents_total",
            "exit_fills_total",
        ]
        
        for key in obs_keys:
            assert key in obs, f"{key} must exist in _obs"
            value = obs[key]
            assert isinstance(value, int), f"{key} must be int, got {type(value)}"
            assert value >= 0, f"{key} must be >= 0, got {value}"
    finally:
        # Restore environment
        if old_trigger_rate is not None:
            os.environ["FISHBRO_PERF_TRIGGER_RATE"] = old_trigger_rate


def test_accounting_consistency() -> None:
    """
    D2: Contract test - Verify accounting consistency
    intents_total == entry_intents_total + exit_intents_total
    fills_total == entry_fills_total + exit_fills_total
    Also verify entry_intents_total == valid_mask_sum in arrays mode
    """
    import os
    # Ensure clean environment for test
    old_trigger_rate = os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    
    try:
        n_bars = 200
        warmup = 20
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        bars = BarArrays(
            open=open_.astype(np.float64),
            high=high.astype(np.float64),
            low=low.astype(np.float64),
            close=close.astype(np.float64),
        )
        
        params = DonchianAtrParams(channel_len=warmup, atr_len=10, stop_mult=1.0)
        
        result = run_kernel_arrays(
            bars=bars,
            params=params,
            commission=0.0,
            slip=0.0,
            order_qty=1,
        )
        
        obs = result["_obs"]
        
        # Verify intents_total consistency
        intents_total = obs.get("intents_total", 0)
        entry_intents_total = obs.get("entry_intents_total", 0)
        exit_intents_total = obs.get("exit_intents_total", 0)
        
        assert intents_total == entry_intents_total + exit_intents_total, (
            f"intents_total ({intents_total}) must equal "
            f"entry_intents_total ({entry_intents_total}) + exit_intents_total ({exit_intents_total})"
        )
        
        # Verify fills_total consistency
        fills_total = obs.get("fills_total", 0)
        entry_fills_total = obs.get("entry_fills_total", 0)
        exit_fills_total = obs.get("exit_fills_total", 0)
        
        assert fills_total == entry_fills_total + exit_fills_total, (
            f"fills_total ({fills_total}) must equal "
            f"entry_fills_total ({entry_fills_total}) + exit_fills_total ({exit_fills_total})"
        )
        
        # Verify entry_intents_total == valid_mask_sum (arrays mode contract)
        if "valid_mask_sum" in obs and "entry_intents_total" in obs:
            valid_mask_sum = obs.get("valid_mask_sum", 0)
            entry_intents = obs.get("entry_intents_total", 0)
            assert entry_intents == valid_mask_sum, (
                f"entry_intents_total ({entry_intents}) must equal valid_mask_sum ({valid_mask_sum})"
            )
    finally:
        # Restore environment
        if old_trigger_rate is not None:
            os.environ["FISHBRO_PERF_TRIGGER_RATE"] = old_trigger_rate


def test_run_grid_perf_contains_timing_keys(monkeypatch) -> None:
    """
    Contract test - Verify run_grid output contains timing keys in perf dict.
    This ensures timing aggregation works correctly at grid level.
    """
    # Task 1: Explicitly enable kernel profiling (required for timing collection)
    old_profile_kernel = os.environ.get("FISHBRO_PROFILE_KERNEL")
    os.environ["FISHBRO_PROFILE_KERNEL"] = "1"
    
    # Enable profile mode to ensure timing collection
    monkeypatch.setenv("FISHBRO_PROFILE_GRID", "1")
    
    try:
        n_bars = 200
        n_params = 5
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        # Generate minimal params
        params = np.array([
            [20, 10, 1.0],
            [25, 12, 1.5],
            [30, 15, 2.0],
            [35, 18, 1.0],
            [40, 20, 1.5],
        ], dtype=np.float64)
        
        result = run_grid(
            open_=open_,
            high=high,
            low=low,
            close=close,
            params_matrix=params,
            commission=0.0,
            slip=0.0,
            order_qty=1,
            sort_params=False,
        )
        
        # Verify perf dict exists
        assert "perf" in result, "perf must exist in run_grid result"
        perf = result["perf"]
        assert isinstance(perf, dict), "perf must be a dict"
        
        # Stage P2-2 Step A: Required micro-profiling timing keys (aggregated across params)
        # Task 2: Since profile is enabled, timing keys must exist
        timing_keys = [
            "t_ind_donchian_s",
            "t_ind_atr_s",
            "t_build_entry_intents_s",
            "t_simulate_entry_s",
            "t_calc_exits_s",
            "t_simulate_exit_s",
            "t_total_kernel_s",
        ]
        
        for key in timing_keys:
            assert key in perf, f"{key} must exist in perf dict when profile is enabled"
            value = perf[key]
            assert isinstance(value, float), f"{key} must be float, got {type(value)}"
            assert value >= 0.0, f"{key} must be >= 0.0, got {value}"
        
        # Stage P2-2 Step A: Memoization potential assessment keys
        unique_keys = [
            "unique_channel_len_count",
            "unique_atr_len_count",
            "unique_ch_atr_pair_count",
        ]
        
        for key in unique_keys:
            assert key in perf, f"{key} must exist in perf dict"
            value = perf[key]
            assert isinstance(value, int), f"{key} must be int, got {type(value)}"
            assert value >= 1, f"{key} must be >= 1, got {value}"
    finally:
        # Task 1: Restore FISHBRO_PROFILE_KERNEL environment variable
        if old_profile_kernel is None:
            os.environ.pop("FISHBRO_PROFILE_KERNEL", None)
        else:
            os.environ["FISHBRO_PROFILE_KERNEL"] = old_profile_kernel


