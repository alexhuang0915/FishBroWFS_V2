#!/usr/bin/env python3
"""
Benchmark for resample_ohlcv performance.
Generate synthetic data of varying sizes and measure execution time.
"""
import sys
import os
# Add src to path as per project convention
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from core.resampler import resample_ohlcv, SessionSpecTaipei

def generate_synthetic_data(n_bars: int, start_dt: datetime = None):
    """Generate synthetic OHLCV data with 1-minute bars."""
    if start_dt is None:
        start_dt = datetime(2025, 1, 1, 0, 0, 0)
    
    # Generate timestamps at 1-minute intervals
    ts = np.array([start_dt + timedelta(minutes=i) for i in range(n_bars)])
    
    # Generate random OHLCV (simplified)
    np.random.seed(42)
    base_price = 100.0
    returns = np.random.randn(n_bars) * 0.01
    prices = base_price * np.exp(np.cumsum(returns))
    
    # Simulate OHLC with some spread
    open_prices = prices * (1 + np.random.randn(n_bars) * 0.001)
    high_prices = np.maximum(open_prices, prices * (1 + np.random.rand(n_bars) * 0.002))
    low_prices = np.minimum(open_prices, prices * (1 - np.random.rand(n_bars) * 0.002))
    close_prices = prices
    volumes = np.random.randint(100, 10000, size=n_bars)
    
    return ts, open_prices, high_prices, low_prices, close_prices, volumes

def benchmark():
    """Run benchmarks for different input sizes."""
    session = SessionSpecTaipei(
        open_hhmm="00:00",
        close_hhmm="24:00",
        breaks=[],
        tz="Asia/Taipei"
    )
    
    sizes = [1000, 10_000, 100_000, 500_000, 1_000_000]
    results = []
    
    for n in sizes:
        print(f"Generating {n} bars...")
        ts, o, h, l, c, v = generate_synthetic_data(n)
        
        # Warm-up (optional)
        if n == sizes[0]:
            _ = resample_ohlcv(ts[:100], o[:100], h[:100], l[:100], c[:100], v[:100], 
                               tf_min=15, session=session)
        
        # Benchmark
        start = time.perf_counter()
        result = resample_ohlcv(ts, o, h, l, c, v, tf_min=15, session=session)
        elapsed = time.perf_counter() - start
        
        output_bars = len(result['ts'])
        results.append({
            'input_bars': n,
            'output_bars': output_bars,
            'time_seconds': elapsed,
            'bars_per_second': n / elapsed if elapsed > 0 else float('inf'),
            'output_bars_per_second': output_bars / elapsed if elapsed > 0 else float('inf')
        })
        print(f"  Processed {n} -> {output_bars} bars in {elapsed:.3f}s ({n/elapsed:.0f} bars/s)")
    
    # Print summary table
    print("\n=== Benchmark Results ===")
    print(f"{'Input Bars':>12} {'Output Bars':>12} {'Time (s)':>10} {'Input Bars/s':>12} {'Output Bars/s':>12}")
    for r in results:
        print(f"{r['input_bars']:12d} {r['output_bars']:12d} {r['time_seconds']:10.3f} {r['bars_per_second']:12.0f} {r['output_bars_per_second']:12.0f}")
    
    # Save results to file
    import json
    out_path = "outputs/_dp_evidence/phase_final_audit_fix/resampler_benchmark_results.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")

if __name__ == "__main__":
    benchmark()