
"""Test DAY bar definition: one complete session per bar."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data.session.kbar import aggregate_kbar
from data.session.loader import load_session_profile


@pytest.fixture
def mnq_profile(profiles_root: Path) -> Path:
    """Load CME.MNQ session profile."""
    profile_path = profiles_root / "CME_MNQ_TPE_v1.yaml"
    return profile_path


def test_day_bar_one_session(mnq_profile: Path) -> None:
    """Test DAY bar = one complete DAY session."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars for one complete DAY session
    df = pd.DataFrame({
        "ts_str": [
            "2013/1/1 08:45:00",  # DAY session start
            "2013/1/1 09:00:00",
            "2013/1/1 10:00:00",
            "2013/1/1 11:00:00",
            "2013/1/1 12:00:00",
            "2013/1/1 13:00:00",
            "2013/1/1 13:44:00",  # Last bar before session end
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
        "volume": [1000, 1100, 1200, 1300, 1400, 1500, 1600],
    })
    
    result = aggregate_kbar(df, "DAY", profile)
    
    # Should have exactly one DAY bar
    assert len(result) == 1, f"Should have 1 DAY bar, got {len(result)}"
    
    # Verify the bar contains all DAY session bars
    day_bar = result.iloc[0]
    assert day_bar["open"] == 100.0, "Open should be first bar's open"
    assert day_bar["high"] == 106.5, "High should be max of all bars"
    assert day_bar["low"] == 99.5, "Low should be min of all bars"
    assert day_bar["close"] == 106.5, "Close should be last bar's close"
    assert day_bar["volume"] == sum([1000, 1100, 1200, 1300, 1400, 1500, 1600]), "Volume should be sum"
    
    # Verify ts_str is anchored to session start
    ts_str = day_bar["ts_str"]
    time_part = ts_str.split(" ")[1]
    assert time_part == "08:45:00", f"DAY bar should be anchored to session start, got {time_part}"


def test_day_bar_multiple_sessions(mnq_profile: Path) -> None:
    """Test DAY bars for multiple sessions."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars for DAY and NIGHT sessions on same day
    df = pd.DataFrame({
        "ts_str": [
            # DAY session
            "2013/1/1 08:45:00",
            "2013/1/1 10:00:00",
            "2013/1/1 13:00:00",
            # NIGHT session
            "2013/1/1 21:00:00",
            "2013/1/1 23:00:00",
            "2013/1/2 02:00:00",
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5, 104.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5],
        "volume": [1000, 1100, 1200, 1300, 1400, 1500],
    })
    
    result = aggregate_kbar(df, "DAY", profile)
    
    # With TRADING/BREAK profile, both windows are TRADING, aggregated into one bar
    assert len(result) == 1, f"Should have 1 DAY bar (both TRADING windows merged), got {len(result)}"
    
    # Verify aggregated bar
    day_bar = result.iloc[0]
    assert day_bar["volume"] == 1000 + 1100 + 1200 + 1300 + 1400 + 1500, "DAY bar volume should sum all bars"


