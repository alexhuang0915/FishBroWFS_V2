"""Raw data ingestion - Raw means RAW.

Phase 6.5 Data Ingest v1: Immutable, extremely stupid raw data ingestion.
No sort, no dedup, no dropna (unless recorded in ingest_policy).

Binding: One line = one row, preserve TXT row order exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class IngestPolicy:
    """Ingest policy - only records format normalization decisions, not data cleaning.
    
    Attributes:
        normalized_24h: Whether 24:00:00 times were normalized to next day 00:00:00
        column_map: Column name mapping from source to standard names
    """
    normalized_24h: bool = False
    column_map: dict[str, str] | None = None


@dataclass(frozen=True)
class RawIngestResult:
    """Raw ingest result - immutable contract.
    
    Attributes:
        df: DataFrame with exactly columns: ts_str, open, high, low, close, volume
        source_path: Path to source TXT file
        rows: Number of rows ingested
        policy: Ingest policy applied
    """
    df: pd.DataFrame  # columns exactly: ts_str, open, high, low, close, volume
    source_path: str
    rows: int
    policy: IngestPolicy


def _normalize_24h(date_s: str, time_s: str) -> tuple[str, bool]:
    """Normalize 24:xx:xx time to next day 00:00:00.
    
    Only allows 24:00:00 (exact). Raises ValueError for other 24:xx:xx times.
    
    Args:
        date_s: Date string (e.g., "2013/1/1")
        time_s: Time string (e.g., "24:00:00" or "09:30:00")
        
    Returns:
        Tuple of (normalized ts_str, normalized_flag)
        - If 24:00:00: returns next day 00:00:00 and True
        - Otherwise: returns original "date_s time_s" and False
        
    Raises:
        ValueError: If time_s starts with "24:" but is not exactly "24:00:00"
    """
    t = time_s.strip()
    if t.startswith("24:"):
        if t != "24:00:00":
            raise ValueError(f"Invalid 24h time: {time_s} (only 24:00:00 is allowed)")
        # Parse date only (no timezone)
        d = pd.to_datetime(date_s.strip(), format="%Y/%m/%d", errors="raise")
        d2 = (d + pd.Timedelta(days=1)).to_pydatetime().date()
        return f"{d2.year}/{d2.month}/{d2.day} 00:00:00", True
    return f"{date_s.strip()} {t}", False


def ingest_raw_txt(
    txt_path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> RawIngestResult:
    """Ingest raw TXT file - Raw means RAW.
    
    Core rules (Binding):
    - One line = one row, preserve TXT row order exactly
    - No sort_values()
    - No drop_duplicates()
    - No dropna() (unless recorded in ingest_policy)
    
    Format normalization (allowed):
    - 24:00:00 → next day 00:00:00 (recorded in policy.normalized_24h)
    - Column mapping (recorded in policy.column_map)
    
    Args:
        txt_path: Path to raw TXT file
        column_map: Optional column name mapping (e.g., {"Date": "Date", "Time": "Time", ...})
        
    Returns:
        RawIngestResult with df containing columns: ts_str, open, high, low, close, volume
        
    Raises:
        FileNotFoundError: If txt_path does not exist
        ValueError: If parsing fails or invalid 24h time format
    """
    if not txt_path.exists():
        raise FileNotFoundError(f"TXT file not found: {txt_path}")
    
    # Read TXT file (preserve order)
    # Assume CSV-like format with header
    df_raw = pd.read_csv(txt_path, encoding="utf-8")
    
    # Apply column mapping if provided
    if column_map:
        df_raw = df_raw.rename(columns=column_map)
    
    # Expected columns after mapping: Date, Time, Open, High, Low, Close, TotalVolume (or Volume)
    required_cols = ["Date", "Time", "Open", "High", "Low", "Close"]
    volume_cols = ["TotalVolume", "Volume"]
    
    # Check required columns
    missing_cols = [col for col in required_cols if col not in df_raw.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}. Found: {list(df_raw.columns)}")
    
    # Find volume column
    volume_col = None
    for vcol in volume_cols:
        if vcol in df_raw.columns:
            volume_col = vcol
            break
    
    if volume_col is None:
        raise ValueError(f"Missing volume column. Expected one of: {volume_cols}. Found: {list(df_raw.columns)}")
    
    # Build ts_str column (preserve row order)
    normalized_24h = False
    ts_str_list = []
    
    for idx, row in df_raw.iterrows():
        date_s = str(row["Date"])
        time_s = str(row["Time"])
        
        try:
            ts_str, was_normalized = _normalize_24h(date_s, time_s)
            if was_normalized:
                normalized_24h = True
            ts_str_list.append(ts_str)
        except Exception as e:
            raise ValueError(f"Failed to normalize timestamp at row {idx}: {e}") from e
    
    # Build result DataFrame (preserve order, no sort/dedup/dropna)
    result_df = pd.DataFrame({
        "ts_str": ts_str_list,
        "open": pd.to_numeric(df_raw["Open"], errors="raise").astype("float64"),
        "high": pd.to_numeric(df_raw["High"], errors="raise").astype("float64"),
        "low": pd.to_numeric(df_raw["Low"], errors="raise").astype("float64"),
        "close": pd.to_numeric(df_raw["Close"], errors="raise").astype("float64"),
        "volume": pd.to_numeric(df_raw[volume_col], errors="coerce").fillna(0).astype("int64"),
    })
    
    # Record policy
    policy = IngestPolicy(
        normalized_24h=normalized_24h,
        column_map=column_map,
    )
    
    return RawIngestResult(
        df=result_df,
        source_path=str(txt_path),
        rows=len(result_df),
        policy=policy,
    )
