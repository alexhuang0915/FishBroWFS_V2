from __future__ import annotations

import numpy as np


class BaselineV1:
    """
    Baseline V1 strategy.
    
    A deterministic strategy that is guaranteed to trade.
    Uses target_dir + stop-entry + protective stop-loss.
    """

    def __init__(self, params: dict):
        self.period = int(params.get("period", 10))
        self.stop_dist_pct = float(params.get("stop_dist_pct", 0.02))

    def compute_orders_ctx(self, ctx, df=None):
        n = len(df) if df is not None else 0
        target_dir = np.zeros(n, dtype=np.int64)
        long_stop = np.full(n, np.nan, dtype=np.float64)
        exit_long_stop = np.full(n, np.nan, dtype=np.float64)
        
        # We need close prices for stop levels
        # Assuming df has 'close'
        if df is None or "close" not in df.columns:
            return {"target_dir": target_dir}

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        pos = 0
        for i in range(n):
            # i is signal bar (T). Simulator will use this for entry at bar T+1.
            if pos == 0:
                if i % self.period == 0:
                    # Request Long
                    target_dir[i] = 1
                    # Stop entry: slightly below current close to ensure it triggers at next open
                    long_stop[i] = close[i] * 0.99
                    pos = 1
            else:
                if i % self.period == self.period // 2:
                    # Request Exit
                    target_dir[i] = 0
                    pos = 0
                else:
                    # Maintain position + protective stop
                    target_dir[i] = 1
                    exit_long_stop[i] = close[i] * (1.0 - self.stop_dist_pct)

        return {
            "target_dir": target_dir,
            "long_stop": long_stop,
            "exit_long_stop": exit_long_stop,
        }
