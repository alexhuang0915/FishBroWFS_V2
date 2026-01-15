
"""Test DST boundary handling for CME.MNQ.

Tests that session classification remains correct across DST transitions.
Uses programmatic timezone conversion to avoid manual TPE time errors.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

# Skip if required profile is missing (deleted per spec)
profile_path = Path("configs/profiles/CME_MNQ_v2.yaml")
if not profile_path.exists():
    pytest.skip("CME_MNQ_v2.yaml deleted per spec", allow_module_level=True)

from data.session.classify import classify_session
from data.session.loader import load_session_profile


@pytest.fixture
def mnq_v2_profile(profiles_root: Path) -> Path:
    """Load CME.MNQ v2 session profile with windows format."""
    profile_path = profiles_root / "CME_MNQ_v2.yaml"
    return profile_path


def _chicago_to_tpe_ts_str(chicago_time_str: str, date_str: str) -> str:
    """Convert Chicago time to Taiwan time ts_str for a given date.
    
    Args:
        chicago_time_str: Time string "HH:MM:SS" in Chicago timezone
        date_str: Date string "YYYY/M/D" or "YYYY/MM/DD"
        
    Returns:
        Full ts_str "YYYY/M/D HH:MM:SS" in Taiwan timezone
    """
    # Parse date (handles non-zero-padded)
    date_parts = date_str.split("/")
    y, m, d = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
    
    # Parse Chicago time
    time_parts = chicago_time_str.split(":")
    hh, mm, ss = int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
    
    # Create datetime in Chicago timezone
    chicago_tz = ZoneInfo("America/Chicago")
    dt_chicago = datetime(y, m, d, hh, mm, ss, tzinfo=chicago_tz)
    
    # Convert to Taiwan time
    tpe_tz = ZoneInfo("Asia/Taipei")
    dt_tpe = dt_chicago.astimezone(tpe_tz)
    
    # Return as "YYYY/M/D HH:MM:SS" string (matching input format)
    return f"{dt_tpe.year}/{dt_tpe.month}/{dt_tpe.day} {dt_tpe.hour:02d}:{dt_tpe.minute:02d}:{dt_tpe.second:02d}"


def test_dst_spring_forward_break(mnq_v2_profile: Path) -> None:
    """Test BREAK session classification during DST spring forward (March).
    
    CME break: 16:00-17:00 CT (Chicago time)
    During DST transition, this break period maps to different Taiwan times.
    But classification should still correctly identify BREAK session.
    """
    profile = load_session_profile(mnq_v2_profile)
    
    # DST spring forward: Second Sunday in March (2024-03-10)
    # Before DST (Standard Time, UTC-6): 16:00 CT maps to different TPE time
    # After DST (Daylight Time, UTC-5): 16:00 CT maps to different TPE time
    
    # Calculate TPE ts_str for Chicago 16:00:00 on specific dates
    # Before DST (March 9, 2024 - Saturday)
    tpe_before = _chicago_to_tpe_ts_str("16:00:00", "2024/3/9")
    tpe_before_end = _chicago_to_tpe_ts_str("16:59:59", "2024/3/9")
    
    # After DST (March 11, 2024 - Monday)
    tpe_after = _chicago_to_tpe_ts_str("16:00:00", "2024/3/11")
    tpe_after_end = _chicago_to_tpe_ts_str("16:59:59", "2024/3/11")
    
    # Test break period before DST
    assert classify_session(tpe_before, profile) == "BREAK"
    assert classify_session(tpe_before_end, profile) == "BREAK"
    
    # Test break period after DST
    assert classify_session(tpe_after, profile) == "BREAK"
    assert classify_session(tpe_after_end, profile) == "BREAK"
    
    # Verify: Same exchange time (16:00 CT) maps to different Taiwan times,
    # but classification is consistent (both are BREAK)


def test_dst_fall_back_break(mnq_v2_profile: Path) -> None:
    """Test BREAK session classification during DST fall back (November).
    
    CME break: 16:00-17:00 CT (Chicago time)
    During DST fall back, this break period maps to different Taiwan times.
    But classification should still correctly identify BREAK session.
    """
    profile = load_session_profile(mnq_v2_profile)
    
    # DST fall back: First Sunday in November (2024-11-03)
    # Before DST (Daylight Time, UTC-5): 16:00 CT maps to different TPE time
    # After DST (Standard Time, UTC-6): 16:00 CT maps to different TPE time
    
    # Calculate TPE ts_str for Chicago 16:00:00 on specific dates
    # Before DST (November 2, 2024 - Saturday)
    tpe_before = _chicago_to_tpe_ts_str("16:00:00", "2024/11/2")
    tpe_before_end = _chicago_to_tpe_ts_str("16:59:59", "2024/11/2")
    
    # After DST (November 4, 2024 - Monday)
    tpe_after = _chicago_to_tpe_ts_str("16:00:00", "2024/11/4")
    tpe_after_end = _chicago_to_tpe_ts_str("16:59:59", "2024/11/4")
    
    # Test break period before DST
    assert classify_session(tpe_before, profile) == "BREAK"
    assert classify_session(tpe_before_end, profile) == "BREAK"
    
    # Test break period after DST
    assert classify_session(tpe_after, profile) == "BREAK"
    assert classify_session(tpe_after_end, profile) == "BREAK"
    
    # Verify: Same exchange time (16:00 CT) maps to different Taiwan times,
    # but classification is consistent (both are BREAK)


def test_dst_trading_session_consistency(mnq_v2_profile: Path) -> None:
    """Test TRADING session classification remains consistent across DST.
    
    CME trading: 17:00 CT - 16:00 CT (next day)
    This should be correctly identified regardless of DST transitions.
    """
    profile = load_session_profile(mnq_v2_profile)
    
    # Calculate TPE ts_str for Chicago 17:00:00 on specific dates
    # March (before DST, Standard Time)
    tpe_mar_before = _chicago_to_tpe_ts_str("17:00:00", "2024/3/9")
    assert classify_session(tpe_mar_before, profile) == "TRADING"
    
    # March (after DST, Daylight Time)
    tpe_mar_after = _chicago_to_tpe_ts_str("17:00:00", "2024/3/11")
    assert classify_session(tpe_mar_after, profile) == "TRADING"
    
    # November (before DST, Daylight Time)
    tpe_nov_before = _chicago_to_tpe_ts_str("17:00:00", "2024/11/2")
    assert classify_session(tpe_nov_before, profile) == "TRADING"
    
    # November (after DST, Standard Time)
    tpe_nov_after = _chicago_to_tpe_ts_str("17:00:00", "2024/11/4")
    assert classify_session(tpe_nov_after, profile) == "TRADING"
    
    # Verify: Exchange time 17:00 CT is consistently classified as TRADING,
    # regardless of how it maps to Taiwan time due to DST


