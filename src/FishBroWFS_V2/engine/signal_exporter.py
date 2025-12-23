"""Signal series exporter for bar-based position, margin, and notional in base currency."""

import pandas as pd
import numpy as np
from typing import Optional

REQUIRED_COLUMNS = [
    "ts",
    "instrument",
    "close",
    "position_contracts",
    "currency",
    "fx_to_base",
    "close_base",
    "multiplier",
    "initial_margin_per_contract",
    "maintenance_margin_per_contract",
    "notional_base",
    "margin_initial_base",
    "margin_maintenance_base",
]


def build_signal_series_v1(
    *,
    instrument: str,
    bars_df: pd.DataFrame,   # cols: ts, close (ts sorted asc)
    fills_df: pd.DataFrame,  # cols: ts, qty (contracts signed)
    timeframe: str,
    tz: str,
    base_currency: str,
    instrument_currency: str,
    fx_to_base: float,
    multiplier: float,
    initial_margin_per_contract: float,
    maintenance_margin_per_contract: float,
) -> pd.DataFrame:
    """
    Build signal series V1 DataFrame from bars and fills.
    
    Args:
        instrument: Instrument identifier (e.g., "CME.MNQ")
        bars_df: DataFrame with columns ['ts', 'close']; must be sorted ascending by ts
        fills_df: DataFrame with columns ['ts', 'qty']; qty is signed contracts (+ for buy, - for sell)
        timeframe: Bar timeframe (e.g., "5min")
        tz: Timezone string (e.g., "UTC")
        base_currency: Base currency code (e.g., "TWD")
        instrument_currency: Instrument currency code (e.g., "USD")
        fx_to_base: FX rate from instrument currency to base currency
        multiplier: Contract multiplier
        initial_margin_per_contract: Initial margin per contract in instrument currency
        maintenance_margin_per_contract: Maintenance margin per contract in instrument currency
        
    Returns:
        DataFrame with REQUIRED_COLUMNS, one row per bar, sorted by ts.
        
    Raises:
        ValueError: If input DataFrames are empty or missing required columns
        AssertionError: If bars_df is not sorted ascending
    """
    # Validate inputs
    if bars_df.empty:
        raise ValueError("bars_df cannot be empty")
    if "ts" not in bars_df.columns or "close" not in bars_df.columns:
        raise ValueError("bars_df must have columns ['ts', 'close']")
    if "ts" not in fills_df.columns or "qty" not in fills_df.columns:
        raise ValueError("fills_df must have columns ['ts', 'qty']")
    
    # Ensure bars are sorted ascending
    if not bars_df["ts"].is_monotonic_increasing:
        bars_df = bars_df.sort_values("ts").reset_index(drop=True)
    
    # Prepare bars DataFrame as base
    result = bars_df[["ts", "close"]].copy()
    result["instrument"] = instrument
    
    # If no fills, position is zero for all bars
    if fills_df.empty:
        result["position_contracts"] = 0.0
    else:
        # Ensure fills are sorted by ts
        fills_sorted = fills_df.sort_values("ts").reset_index(drop=True)
        
        # Merge fills to bars using merge_asof to align fill ts to bar ts
        # direction='backward' assigns fill to the nearest bar with ts <= fill_ts
        # We need to merge on ts, but we want to get the bar ts for each fill
        merged = pd.merge_asof(
            fills_sorted,
            result[["ts"]].rename(columns={"ts": "bar_ts"}),
            left_on="ts",
            right_on="bar_ts",
            direction="backward"
        )
        
        # Group by bar_ts and sum qty
        fills_per_bar = merged.groupby("bar_ts")["qty"].sum().reset_index()
        fills_per_bar = fills_per_bar.rename(columns={"bar_ts": "ts", "qty": "fill_qty"})
        
        # Merge fills back to bars
        result = pd.merge(result, fills_per_bar, on="ts", how="left")
        result["fill_qty"] = result["fill_qty"].fillna(0.0)
        
        # Cumulative sum of fills to get position
        result["position_contracts"] = result["fill_qty"].cumsum()
    
    # Add currency and FX columns
    result["currency"] = instrument_currency
    result["fx_to_base"] = fx_to_base
    
    # Calculate close in base currency
    result["close_base"] = result["close"] * fx_to_base
    
    # Add contract specs
    result["multiplier"] = multiplier
    result["initial_margin_per_contract"] = initial_margin_per_contract
    result["maintenance_margin_per_contract"] = maintenance_margin_per_contract
    
    # Calculate notional and margins in base currency
    # notional_base = position_contracts * close_base * multiplier
    result["notional_base"] = result["position_contracts"] * result["close_base"] * multiplier
    
    # margin_initial_base = abs(position_contracts) * initial_margin_per_contract * fx_to_base
    result["margin_initial_base"] = (
        abs(result["position_contracts"]) * initial_margin_per_contract * fx_to_base
    )
    
    # margin_maintenance_base = abs(position_contracts) * maintenance_margin_per_contract * fx_to_base
    result["margin_maintenance_base"] = (
        abs(result["position_contracts"]) * maintenance_margin_per_contract * fx_to_base
    )
    
    # Ensure all required columns are present and in correct order
    for col in REQUIRED_COLUMNS:
        if col not in result.columns:
            raise RuntimeError(f"Missing column {col} in result")
    
    # Reorder columns
    result = result[REQUIRED_COLUMNS]
    
    # Ensure no NaN values (except maybe where close is NaN, but that shouldn't happen)
    if result.isna().any().any():
        # Fill numeric NaNs with 0 where appropriate
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        result[numeric_cols] = result[numeric_cols].fillna(0.0)
    
    return result