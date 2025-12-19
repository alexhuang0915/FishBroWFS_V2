"""K-Bar Aggregation.

Phase 6.6: Aggregate bars into K-bars (30/60/120/240/DAY minutes).
Must anchor to Session.start (exchange timezone), no cross-session aggregation.
DST-safe: Uses exchange clock for bucket calculation.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from FishBroWFS_V2.data.session.classify import _parse_ts_str_tpe
from FishBroWFS_V2.data.session.schema import SessionProfile


# Allowed K-bar intervals (minutes)
ALLOWED_INTERVALS = {30, 60, 120, 240, "DAY"}


def _is_trading_session(sess: str | None) -> bool:
    """Check if a session is aggregatable (trading session).
    
    Phase 6.6: Unified rule for determining aggregatable sessions.
    
    Rules:
    - BREAK: Not aggregatable (absolute boundary)
    - None: Not aggregatable (outside any session)
    - MAINTENANCE: Not aggregatable
    - All others (TRADING, DAY, NIGHT, etc.): Aggregatable
    
    This supports both:
    - Phase 6.6: TRADING/BREAK semantics
    - Legacy: DAY/NIGHT semantics
    
    Args:
        sess: Session name or None
        
    Returns:
        True if session is aggregatable, False otherwise
    """
    if sess is None:
        return False
    # Phase 6.6: BREAK is absolute boundary
    if sess == "BREAK":
        return False
    # Legacy: MAINTENANCE is not aggregatable
    if sess == "MAINTENANCE":
        return False
    # All other sessions (TRADING, DAY, NIGHT, etc.) are aggregatable
    return True


def aggregate_kbar(
    df: pd.DataFrame,
    interval: int | str,
    profile: SessionProfile,
) -> pd.DataFrame:
    """Aggregate bars into K-bars.
    
    Rules:
    - Only allowed intervals: 30, 60, 120, 240, DAY
    - Must anchor to Session.start
    - No cross-session aggregation
    - DAY bar = one complete session
    
    Args:
        df: DataFrame with columns: ts_str, open, high, low, close, volume
        interval: K-bar interval in minutes (30/60/120/240) or "DAY"
        profile: Session profile
        
    Returns:
        Aggregated DataFrame with same columns
        
    Raises:
        ValueError: If interval is not allowed
    """
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(
            f"Invalid interval: {interval}. Allowed: {ALLOWED_INTERVALS}"
        )
    
    if interval == "DAY":
        return _aggregate_day_bar(df, profile)
    
    # For minute intervals, aggregate within sessions
    return _aggregate_minute_bar(df, int(interval), profile)


def _aggregate_day_bar(df: pd.DataFrame, profile: SessionProfile) -> pd.DataFrame:
    """Aggregate into DAY bars (one complete session per bar).
    
    Phase 6.6: BREAK is absolute boundary - only aggregate trading sessions.
    DST-safe: Uses exchange clock for session grouping.
    DAY bar = one complete trading session.
    Each trading session produces one DAY bar, regardless of calendar date.
    """
    from FishBroWFS_V2.data.session.classify import classify_sessions
    
    # Classify each bar into session
    df = df.copy()
    df["_session"] = classify_sessions(df["ts_str"], profile)
    
    # Phase 6.6: Filter out non-aggregatable sessions (BREAK, None, MAINTENANCE)
    df = df[df["_session"].apply(_is_trading_session)]
    
    if len(df) == 0:
        return pd.DataFrame(columns=["ts_str", "open", "high", "low", "close", "volume", "session"])
    
    # Convert to exchange timezone for grouping (DST-safe)
    # Phase 6.6: Add derived columns (not violating raw layer)
    if not profile.exchange_tz:
        raise ValueError("Profile must have exchange_tz for DAY bar aggregation")
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    df["_local_dt"] = df["ts_str"].apply(_parse_ts_str_tpe)
    df["_ex_dt"] = df["_local_dt"].apply(lambda dt: dt.astimezone(exchange_tz_info))
    
    # Group by session - each group = one complete session
    # For overnight sessions, all bars of the same session are grouped together
    groups = df.groupby("_session", dropna=False)
    
    result_rows = []
    for session, group in groups:
        # For EXCHANGE_RULE mode, session may not be in profile.sessions
        # Still produce DAY bar if session was classified
        # (session_obj is only needed for anchor time, which DAY bar doesn't use)
        
        # Determine session start date in exchange timezone
        # Sort group by exchange datetime to find first bar chronologically
        group_sorted = group.sort_values("_ex_dt")
        first_bar_ex_dt = group_sorted["_ex_dt"].iloc[0]
        
        # Get original local ts_str for output (keep TPE time)
        # Use first bar's ts_str as anchor - it represents session start in local time
        first_bar_ts_str = group_sorted["ts_str"].iloc[0]
        
        # For DAY bar, use first bar's ts_str directly
        # This ensures output matches the actual first bar time in local timezone
        ts_str = first_bar_ts_str
        
        # Aggregate OHLCV
        open_val = group["open"].iloc[0]
        high_val = group["high"].max()
        low_val = group["low"].min()
        close_val = group["close"].iloc[-1]
        volume_val = group["volume"].sum()
        
        result_rows.append({
            "ts_str": ts_str,
            "open": open_val,
            "high": high_val,
            "low": low_val,
            "close": close_val,
            "volume": int(volume_val),
            "session": session,  # Phase 6.6: Add session label (derived data, not violating Raw)
        })
    
    result_df = pd.DataFrame(result_rows)
    
    # Remove helper columns if they exist
    for col in ["_session", "_local_dt", "_ex_dt"]:
        if col in result_df.columns:
            result_df = result_df.drop(columns=[col])
    
    # Sort by ts_str to maintain chronological order
    if len(result_df) > 0:
        result_df = result_df.sort_values("ts_str").reset_index(drop=True)
    
    return result_df


def _aggregate_minute_bar(
    df: pd.DataFrame,
    interval_minutes: int,
    profile: SessionProfile,
) -> pd.DataFrame:
    """Aggregate into minute bars (30/60/120/240).
    
    Phase 6.6: BREAK is absolute boundary - only aggregate trading sessions.
    DST-safe: Uses exchange clock for bucket calculation.
    Must anchor to Session.start (exchange timezone), no cross-session aggregation.
    Bucket doesn't need to be full - any data produces a bar.
    """
    from FishBroWFS_V2.data.session.classify import classify_sessions
    
    # Classify each bar into session
    df = df.copy()
    df["_session"] = classify_sessions(df["ts_str"], profile)
    
    # Phase 6.6: Filter out non-aggregatable sessions (BREAK, None, MAINTENANCE)
    df = df[df["_session"].apply(_is_trading_session)]
    
    if len(df) == 0:
        return pd.DataFrame(columns=["ts_str", "open", "high", "low", "close", "volume", "session"])
    
    # Convert to exchange timezone for bucket calculation
    # Phase 6.6: Add derived columns (not violating raw layer)
    if not profile.exchange_tz:
        raise ValueError("Profile must have exchange_tz for minute bar aggregation")
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    
    df["_local_dt"] = df["ts_str"].apply(_parse_ts_str_tpe)
    df["_ex_dt"] = df["_local_dt"].apply(lambda dt: dt.astimezone(exchange_tz_info))
    
    # Extract exchange date and time for grouping
    df["_ex_date"] = df["_ex_dt"].apply(lambda dt: dt.date().isoformat().replace("-", "/"))
    df["_ex_time"] = df["_ex_dt"].apply(lambda dt: dt.strftime("%H:%M:%S"))
    
    result_rows = []
    
    # Process each (exchange_date, session) group separately
    groups = df.groupby(["_ex_date", "_session"], dropna=False)
    
    for (ex_date, session), group in groups:
        if not _is_trading_session(session):
            continue  # Skip non-aggregatable sessions (BREAK, None, MAINTENANCE)
        
        # Find session start time from profile (in exchange timezone)
        # Phase 6.6: If windows exist, use first TRADING window.start
        # Legacy: Use current session name to find matching session.start
        session_start = None
        
        if profile.windows:
            # Phase 6.6: Use first TRADING window.start
            for window in profile.windows:
                if window.state == "TRADING":
                    session_start = window.start
                    break
        else:
            # Legacy: Find session.start by matching session name
            for sess in profile.sessions:
                if sess.name == session:
                    session_start = sess.start
                    break
        
        # If still not found, use first bar's exchange time as anchor
        if session_start is None:
            first_bar_ex_time = group["_ex_time"].iloc[0]
            session_start = first_bar_ex_time
        
        # Calculate bucket start times anchored to session.start (exchange timezone)
        buckets = _calculate_buckets(session_start, interval_minutes)
        
        # Assign each bar to a bucket using exchange time
        group = group.copy()
        group["_bucket"] = group["_ex_time"].apply(
            lambda t: _find_bucket(t, buckets)
        )
        
        # Aggregate per bucket
        bucket_groups = group.groupby("_bucket", dropna=False)
        
        for bucket_start, bucket_group in bucket_groups:
            if pd.isna(bucket_start):
                continue
            
            # Phase 6.6: Bucket doesn't need to be full - any data produces a bar
            # BREAK is absolute boundary (already filtered out above)
            if bucket_group.empty:
                continue
            
            # ts_str output: Use original local ts_str (TPE), not exchange time
            # But bucket grouping was done in exchange time
            first_bar_ts_str = bucket_group["ts_str"].iloc[0]  # Original TPE ts_str
            
            # Aggregate OHLCV
            open_val = bucket_group["open"].iloc[0]
            high_val = bucket_group["high"].max()
            low_val = bucket_group["low"].min()
            close_val = bucket_group["close"].iloc[-1]
            volume_val = bucket_group["volume"].sum()
            
            result_rows.append({
                "ts_str": first_bar_ts_str,  # Keep original TPE ts_str
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": int(volume_val),
                "session": session,  # Phase 6.6: Add session label (derived data, not violating Raw)
            })
    
    result_df = pd.DataFrame(result_rows)
    
    # Remove helper columns
    for col in ["_session", "_ex_date", "_ex_time", "_bucket", "_local_dt", "_ex_dt"]:
        if col in result_df.columns:
            result_df = result_df.drop(columns=[col])
    
    # Sort by ts_str to maintain chronological order
    if len(result_df) > 0:
        result_df = result_df.sort_values("ts_str").reset_index(drop=True)
    
    return result_df


def _calculate_buckets(session_start: str, interval_minutes: int) -> List[str]:
    """Calculate bucket start times anchored to session_start.
    
    Args:
        session_start: Session start time "HH:MM:SS"
        interval_minutes: Interval in minutes
        
    Returns:
        List of bucket start times ["HH:MM:SS", ...]
    """
    # Parse session_start
    parts = session_start.split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    
    # Convert to total minutes
    start_minutes = h * 60 + m
    
    buckets = []
    current_minutes = start_minutes
    
    # Generate buckets until end of day (24:00:00 = 1440 minutes)
    while current_minutes < 1440:
        h_bucket = current_minutes // 60
        m_bucket = current_minutes % 60
        bucket_str = f"{h_bucket:02d}:{m_bucket:02d}:00"
        buckets.append(bucket_str)
        current_minutes += interval_minutes
    
    return buckets


def _find_bucket(time_str: str, buckets: List[str]) -> str | None:
    """Find which bucket a time belongs to.
    
    Phase 6.6: Anchor-based bucket assignment.
    Bucket = floor((time - anchor) / interval)
    
    Args:
        time_str: Time string "HH:MM:SS"
        buckets: List of bucket start times (sorted ascending)
        
    Returns:
        Bucket start time if found, None otherwise
    """
    # Find the largest bucket <= time_str
    # Buckets are sorted ascending, so iterate backwards
    for i in range(len(buckets) - 1, -1, -1):
        if buckets[i] <= time_str:
            # Check if next bucket would exceed time_str
            if i + 1 < len(buckets):
                next_bucket = buckets[i + 1]
                if time_str < next_bucket:
                    return buckets[i]
            else:
                # Last bucket - time_str falls in this bucket
                return buckets[i]
    
    return None
