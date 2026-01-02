"""Dashboard demo feed (deterministic). Not research/golden data."""

from __future__ import annotations

import numpy as np
from typing import Tuple


def generate_dashboard_ohlc(
    n_bars: int = 2000, seed: int = 42
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate deterministic OHLC arrays for dashboard visualization.
    
    Parameters
    ----------
    n_bars : int, default=2000
        Number of bars to generate.
    seed : int, default=42
        Random seed for reproducibility (unused in deterministic pattern).
    
    Returns
    -------
    open, high, low, close : np.ndarray
        Four float64 arrays of length n_bars.
    
    Notes
    -----
    - Enforces invariants per bar: high >= max(open, close), low <= min(open, close)
    - Includes a deterministic spike‑crash pattern that guarantees at least one completed trade
      for typical Donchian‑ATR parameters (channel_len ≤ 50).
    - Heartbeat‑friendly: ensures trades > 0 and non‑empty equity curve.
    """
    # Use a deterministic pattern inspired by Phase 8‑Gamma decreasing baseline spike.
    # This guarantees a complete trade cycle (entry + exit) for the kernel.
    baseline = 100.0
    spike_bar = n_bars // 2 if n_bars >= 200 else 100  # middle of series
    crash_bar = spike_bar + 1
    
    # Ensure indices within bounds
    if crash_bar >= n_bars:
        crash_bar = n_bars - 1
        spike_bar = crash_bar - 1
    
    # High decreasing by 0.001 each bar to prevent early entry
    high = baseline - np.arange(n_bars) * 0.001
    # Open slightly below high
    open_ = high - 0.001
    # Close slightly above high (but still decreasing)
    close = high + 0.5
    # Low below high
    low = high - 1.0
    
    # Spike bar: extreme high and low to guarantee entry stop crossing
    high[spike_bar] = 1_000_000_000.0
    low[spike_bar] = 0.001
    open_[spike_bar] = high[spike_bar] - 0.001  # still huge
    close[spike_bar] = 1_000_000.0  # as before
    
    # Crash bar: extreme low to trigger exit stop
    high[crash_bar] = 0.01 + 1.0
    low[crash_bar] = 0.0001
    open_[crash_bar] = 0.01
    close[crash_bar:] = 0.01
    
    # Ensure low > 0 (strictly positive)
    low = np.maximum(low, 0.00001)
    
    # Enforce invariants (already satisfied by construction, but safe)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    
    # Convert to float64 contiguous arrays
    open_ = np.ascontiguousarray(open_, dtype=np.float64)
    high = np.ascontiguousarray(high, dtype=np.float64)
    low = np.ascontiguousarray(low, dtype=np.float64)
    close = np.ascontiguousarray(close, dtype=np.float64)
    
    return open_, high, low, close


if __name__ == "__main__":
    # Quick smoke test
    o, h, l, c = generate_dashboard_ohlc(n_bars=100)
    print(f"Generated {len(o)} bars")
    print(f"Open shape: {o.shape}, dtype: {o.dtype}")
    print(f"High >= max(Open, Close) check: {(h >= np.maximum(o, c)).all()}")
    print(f"Low <= min(Open, Close) check: {(l <= np.minimum(o, c)).all()}")
    print(f"First 5 closes: {c[:5]}")
    print(f"Last 5 closes: {c[-5:]}")
