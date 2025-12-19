"""Session classification.

Phase 6.6: Classify timestamps into trading sessions using DST-safe timezone conversion.
Converts local time to exchange time for classification.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd
from zoneinfo import ZoneInfo

from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow


def _parse_ts_str(ts_str: str) -> datetime:
    """Parse timestamp string (handles non-zero-padded dates like "2013/1/1").
    
    Phase 6.6: Manual parsing to handle "YYYY/M/D" format without zero-padding.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        
    Returns:
        datetime (naive, no timezone attached)
    """
    date_s, time_s = ts_str.split(" ")
    y, m, d = (int(x) for x in date_s.split("/"))
    hh, mm, ss = (int(x) for x in time_s.split(":"))
    return datetime(y, m, d, hh, mm, ss)


def _parse_ts_str_tpe(ts_str: str) -> datetime:
    """Parse timestamp string and attach Asia/Taipei timezone.
    
    Phase 6.6: Only does format parsing + attach timezone, no "correction" or sort.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        
    Returns:
        datetime with Asia/Taipei timezone
    """
    dt = _parse_ts_str(ts_str)
    return dt.replace(tzinfo=ZoneInfo("Asia/Taipei"))


def _parse_ts_str_with_tz(ts_str: str, tz: str) -> datetime:
    """Parse timestamp string and attach specified timezone.
    
    Phase 6.6: Parse ts_str and attach timezone.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        tz: IANA timezone (e.g., "Asia/Taipei")
        
    Returns:
        datetime with specified timezone
    """
    dt = _parse_ts_str(ts_str)
    return dt.replace(tzinfo=ZoneInfo(tz))


def _to_exchange_hms(ts_str: str, data_tz: str, exchange_tz: str) -> str:
    """Convert timestamp string to exchange timezone and return HH:MM:SS.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" (data timezone)
        data_tz: IANA timezone of input data (e.g., "Asia/Taipei")
        exchange_tz: IANA timezone of exchange (e.g., "America/Chicago")
        
    Returns:
        Time string "HH:MM:SS" in exchange timezone
    """
    dt = _parse_ts_str(ts_str).replace(tzinfo=ZoneInfo(data_tz))
    dt_ex = dt.astimezone(ZoneInfo(exchange_tz))
    return dt_ex.strftime("%H:%M:%S")


def classify_session(
    ts_str: str,
    profile: SessionProfile,
) -> str | None:
    """Classify timestamp string into session state.
    
    Phase 6.6: Core classification logic with DST-safe timezone conversion.
    - ts_str (TPE string) → parse as data_tz → convert to exchange_tz
    - Use exchange time to compare with windows
    - BREAK 優先於 TRADING
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" (data timezone)
        profile: Session profile with data_tz, exchange_tz, and windows
        
    Returns:
        Session state: "TRADING", "BREAK", or None
    """
    # Phase 6.6: Parse ts_str as data_tz, convert to exchange_tz
    data_dt = _parse_ts_str_with_tz(ts_str, profile.data_tz)
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    exchange_dt = data_dt.astimezone(exchange_tz_info)
    
    # Extract exchange time HH:MM:SS
    exchange_time_str = exchange_dt.strftime("%H:%M:%S")
    
    # Phase 6.6: Use windows if available (preferred method)
    if profile.windows:
        # BREAK 優先於 TRADING - check BREAK windows first
        for window in profile.windows:
            if window.state == "BREAK":
                if profile._time_in_range(exchange_time_str, window.start, window.end):
                    return "BREAK"
        
        # Then check TRADING windows
        for window in profile.windows:
            if window.state == "TRADING":
                if profile._time_in_range(exchange_time_str, window.start, window.end):
                    return "TRADING"
        
        return None
    
    # Fallback to legacy modes for backward compatibility
    if profile.mode == "tz_convert":
        # tz_convert mode: Check BREAK first, then TRADING
        if profile.break_start and profile.break_end:
            if profile._time_in_range(exchange_time_str, profile.break_start, profile.break_end):
                return "BREAK"
        return "TRADING"
    
    elif profile.mode == "FIXED_TPE":
        # FIXED_TPE mode: Use sessions list
        for session in profile.sessions:
            if profile._time_in_range(exchange_time_str, session.start, session.end):
                return session.name
        return None
    
    elif profile.mode == "EXCHANGE_RULE":
        # EXCHANGE_RULE mode: Use rules
        rules = profile.rules
        if "daily_maintenance" in rules:
            maint = rules["daily_maintenance"]
            maint_start = maint.get("start", "16:00:00")
            maint_end = maint.get("end", "17:00:00")
            if profile._time_in_range(exchange_time_str, maint_start, maint_end):
                return "MAINTENANCE"
        
        if "trading_week" in rules:
            return "TRADING"
        
        # Check sessions if available
        if profile.sessions:
            for session in profile.sessions:
                if profile._time_in_range(exchange_time_str, session.start, session.end):
                    return session.name
        
        return None
    
    else:
        raise ValueError(f"Unknown profile mode: {profile.mode}")


def classify_sessions(
    ts_str_series: pd.Series,
    profile: SessionProfile,
) -> pd.Series:
    """Classify multiple timestamps into session names.
    
    Args:
        ts_str_series: Series of timestamp strings ("YYYY/M/D HH:MM:SS") in local time
        profile: Session profile
        
    Returns:
        Series of session names (or None)
    """
    return ts_str_series.apply(lambda ts: classify_session(ts, profile))
