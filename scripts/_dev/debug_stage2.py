import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import numpy as np
from pipeline.stage2_runner import run_stage2

# Generate trending data
np.random.seed(42)
n_bars = 2000
trend = np.linspace(0, 1000, n_bars)
cycle = 50 * np.sin(np.linspace(0, 10 * np.pi, n_bars))
noise = np.cumsum(np.random.normal(0, 2, n_bars))
close = 1000 + trend + cycle + noise
open_ = close + np.random.normal(0, 5, n_bars)
high = np.maximum(open_, close) + np.abs(np.random.normal(0, 5, n_bars)) + 2
low = np.minimum(open_, close) - np.abs(np.random.normal(0, 5, n_bars)) - 2

# Create a single parameter set that should definitely trigger trades
# Use aggressive parameters: short channel, short ATR, small multiplier
params_matrix = np.array([
    [10, 5, 1.5],   # Very short channel
    [20, 10, 2.0],  # Medium
    [30, 15, 3.0],  # Longer
]).astype(np.float64)

param_ids = [0, 1, 2]

print("Data shape:", open_.shape)
print("Close range:", close.min(), close.max())
print("Trend magnitude:", trend[-1] - trend[0])

# Run Stage 2
results = run_stage2(
    open_, high, low, close,
    params_matrix,
    param_ids,
    commission=0.0,
    slip=0.0,
    order_qty=1
)

print("\nStage 2 Results:")
for r in results:
    print(f"  param_id={r.param_id}: net_profit={r.net_profit:.4f}, trades={r.trades}, max_dd={r.max_dd:.4f}")

# Check if any trades occurred
total_trades = sum(r.trades for r in results)
print(f"\nTotal trades across all parameters: {total_trades}")

# Check variance
profits = np.array([r.net_profit for r in results])
print(f"Net profits: {profits}")
print(f"Std of profits: {np.std(profits)}")

# Also check the kernel directly
print("\n--- Checking kernel directly ---")
from strategy.kernel import run_kernel
from engine.engine_types import BarArrays
from data.layout import normalize_bars

bars = normalize_bars(open_, high, low, close)
print(f"Bars shape: {bars.open.shape}")

# Test with the most aggressive parameter
from strategy.kernel import DonchianAtrParams
params = DonchianAtrParams(channel_len=10, atr_len=5, stop_mult=1.5)
kernel_result = run_kernel(bars, params, commission=0.0, slip=0.0, order_qty=1)
print(f"Kernel result metrics: {kernel_result['metrics']}")
print(f"Fills count: {len(kernel_result.get('fills', []))}")