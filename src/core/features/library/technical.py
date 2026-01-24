"""
Standard Technical Indicators.

Pure functions: DataFrame -> DataFrame.
"""

import pandas as pd

def simple_moving_average(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Calculate Simple Moving Average.
    
    Params:
        period (int): Window size.
        input_col (str): Column to average (default: close).
    """
    period = params.get("period", 14)
    input_col = params.get("input_col", "close")
    
    if input_col not in df.columns:
        raise ValueError(f"Input column {input_col} not found in data")
        
    series = df[input_col].rolling(window=period).mean()
    
    # Return as DataFrame with clear name
    return pd.DataFrame({f"sma_{period}": series}, index=df.index)
