#!/usr/bin/env python3
"""
Profile resample_ohlcv to identify bottlenecks.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import cProfile
import pstats
import io
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from core.resampler import resample_ohlcv, SessionSpecTaipei

def generate_synthetic_data(n_bars: int):
    """Generate synthetic OHLCV data with 1-minute bars."""
    start_dt = datetime(2025, 1, 1, 0, 0, 0)
    ts = np.array([start_dt + timedelta(minutes=i) for i in range(n_bars)])
    np.random.seed(42)
    base_price = 100.0
    returns = np.random.randn(n_bars) * 0.01
    prices = base_price * np.exp(np.cumsum(returns))
    open_prices = prices * (1 + np.random.randn(n_bars) * 0.001)
    high_prices = np.maximum(open_prices, prices * (1 + np.random.rand(n_bars) * 0.002))
    low_prices = np.minimum(open_prices, prices * (1 - np.random.rand(n_bars) * 0.002))
    close_prices = prices
    volumes = np.random.randint(100, 10000, size=n_bars)
    return ts, open_prices, high_prices, low_prices, close_prices, volumes

def profile_resample(n=100000):
    ts, o, h, l, c, v = generate_synthetic_data(n)
    session = SessionSpecTaipei(
        open_hhmm="00:00",
        close_hhmm="24:00",
        breaks=[],
        tz="Asia/Taipei"
    )
    
    pr = cProfile.Profile()
    pr.enable()
    result = resample_ohlcv(ts, o, h, l, c, v, tf_min=15, session=session)
    pr.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    
    profile_output = s.getvalue()
    print(profile_output)
    
    # Save to file
    out_path = f"outputs/_dp_evidence/phase_final_audit_fix/resampler_profile_{n}.txt"
    with open(out_path, 'w') as f:
        f.write(profile_output)
    print(f"Profile saved to {out_path}")

if __name__ == "__main__":
    profile_resample(100000)