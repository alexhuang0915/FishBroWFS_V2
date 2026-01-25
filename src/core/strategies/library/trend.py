"""
Standard Strategies Library.
"""

import pandas as pd
import numpy as np

class SmaCross:
    """
    Simple Moving Average Crossover Strategy.
    """
    
    def __init__(self, params: dict):
        # Accept both legacy and config-style param names.
        # This keeps TUI/handler wiring simple when params come from YAML like `fast_period`.
        self.fast = params.get("fast", params.get("fast_period", 10))
        self.slow = params.get("slow", params.get("slow_period", 20))
        
    def compute_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Returns:
            Series of 1 (Long), -1 (Short), 0 (Neutral).
        """
        # Close is required
        if "close" not in df.columns:
            raise ValueError("Input data missing 'close' column")
            
        close = df["close"]
        
        # Compute Indicators
        sma_fast = close.rolling(window=self.fast).mean()
        sma_slow = close.rolling(window=self.slow).mean()
        
        # Generate Signals
        # 1 when Fast > Slow, -1 when Fast < Slow
        signals = pd.Series(0, index=df.index)
        signals[sma_fast > sma_slow] = 1
        signals[sma_fast < sma_slow] = -1
        
        return signals

    def compute_signals_ctx(self, ctx, df: pd.DataFrame) -> pd.Series:
        """
        FeatureContext-aware entrypoint (V1).
        For now, reuse the same logic on data1 close.
        """
        return self.compute_signals(df)
