
#!/usr/bin/env python3
"""
FishBro WFS - Direct Engine Benchmark
用途: 繞過所有 Harness/Subprocess 複雜度，直接 import engine 測速
"""
import sys
import time
import gc
import numpy as np
from pathlib import Path

# 1. 強制設定路徑 (指向 src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

print(f"python_path: {sys.path[0]}")

try:
    # Correct src-based package name in this repo:
    # src/FishBroWFS_V2/pipeline/runner_grid.py
    from FishBroWFS_V2.pipeline.runner_grid import run_grid  # type: ignore
    print("✅ Engine imported successfully (FishBroWFS_V2.pipeline.runner_grid).")
except ImportError as e:
    print(f"❌ FATAL: Cannot import engine: {e}")
    sys.exit(1)

# 2. 設定規模 (小規模 Smoke Test)
BARS = 20_000
PARAMS = 5_000
HOT_RUNS = 5

def generate_data(n_bars, n_params):
    print(f"generating data: {n_bars} bars, {n_params} params...")
    rng = np.random.default_rng(42)
    
    close = 10000 + np.cumsum(rng.standard_normal(n_bars)) * 10
    # 使用 np.abs 避免 AttributeError
    high = close + np.abs(rng.standard_normal(n_bars)) * 5
    low = close - np.abs(rng.standard_normal(n_bars)) * 5
    open_ = (high + low) / 2 + rng.standard_normal(n_bars)
    
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    
    # Generate Params (runner_grid contract: params_matrix must be (n, >=3))
    w1 = rng.integers(10, 100, size=n_params)
    w2 = rng.integers(5, 50, size=n_params)
    w3 = rng.integers(2, 30, size=n_params)
    params = np.column_stack((w1, w2, w3))
    
    # Layout check
    data_arrays = [open_, high, low, close, params]
    final_arrays = []
    for arr in data_arrays:
        arr = arr.astype(np.float64)
        if not arr.flags['C_CONTIGUOUS']:
            arr = np.ascontiguousarray(arr)
        final_arrays.append(arr)
        
    return final_arrays[0], final_arrays[1], final_arrays[2], final_arrays[3], final_arrays[4]

def main():
    opens, highs, lows, closes, params = generate_data(BARS, PARAMS)
    
    print("-" * 40)
    print(f"Start Benchmark: {BARS} bars x {PARAMS} params")
    print("-" * 40)

    # COLD RUN
    print("🥶 Cold run (compiling)...", end="", flush=True)
    t0 = time.perf_counter()
    _ = run_grid(
        open_=opens,
        high=highs,
        low=lows,
        close=closes,
        params_matrix=params,
        commission=0.0,
        slip=0.0,
        sort_params=False,
    )
    print(f" Done in {time.perf_counter() - t0:.4f}s")

    # HOT RUNS
    times = []
    print(f"🔥 Hot runs ({HOT_RUNS} times, GC off)...")
    gc.disable()
    for i in range(HOT_RUNS):
        t_start = time.perf_counter()
        _ = run_grid(
            open_=opens,
            high=highs,
            low=lows,
            close=closes,
            params_matrix=params,
            commission=0.0,
            slip=0.0,
            sort_params=False,
        )
        dt = time.perf_counter() - t_start
        times.append(dt)
        print(f"   Run {i+1}: {dt:.4f}s")
    gc.enable()
    
    min_time = min(times)
    total_ops = BARS * PARAMS
    tput = total_ops / min_time
    
    print("-" * 40)
    print(f"MIN TIME:   {min_time:.4f}s")
    print(f"THROUGHPUT: {int(tput):,} pair-bars/sec")
    print("-" * 40)

if __name__ == "__main__":
    main()


