
"""Test K-bar aggregation: no cross-session aggregation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from FishBroWFS_V2.data.session.kbar import aggregate_kbar
from FishBroWFS_V2.data.session.loader import load_session_profile


@pytest.fixture
def mnq_profile() -> Path:
    """Load CME.MNQ session profile."""
    profile_path = Path(__file__).parent.parent / "src" / "FishBroWFS_V2" / "data" / "profiles" / "CME_MNQ_TPE_v1.yaml"
    return profile_path


def test_no_cross_session_60m(mnq_profile: Path) -> None:
    """Test 60-minute bars do not cross session boundaries."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars that span DAY session end and NIGHT session start
    df = pd.DataFrame({
        "ts_str": [
            "2013/1/1 13:30:00",  # DAY session
            "2013/1/1 13:40:00",  # DAY session
            "2013/1/1 13:44:00",  # DAY session (last bar before end)
            "2013/1/1 21:00:00",  # NIGHT session start
            "2013/1/1 21:10:00",  # NIGHT session
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })
    
    result = aggregate_kbar(df, 60, profile)
    
    # Verify no bar contains both DAY and NIGHT session bars
    # Use session column instead of string contains (more robust)
    assert "session" in result.columns, "Result must include session column"
    
    # Must have both DAY and NIGHT sessions
    assert set(result["session"].dropna()) == {"DAY", "NIGHT"}, (
        f"Should have both DAY and NIGHT sessions, got {set(result['session'].dropna())}"
    )
    
    day_bars = result[result["session"] == "DAY"]
    night_bars = result[result["session"] == "NIGHT"]
    
    assert len(day_bars) > 0, "Should have DAY session bars"
    assert len(night_bars) > 0, "Should have NIGHT session bars"
    
    # Verify no bar mixes sessions (each row has exactly one session)
    assert result["session"].notna().all(), "All bars must have a session label"
    assert len(result[result["session"].isna()]) == 0, "No bar should have session=None"


def test_no_cross_session_30m(mnq_profile: Path) -> None:
    """Test 30-minute bars do not cross session boundaries."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars at DAY session end
    df = pd.DataFrame({
        "ts_str": [
            "2013/1/1 13:30:00",
            "2013/1/1 13:40:00",
            "2013/1/1 13:44:00",  # Last bar in DAY session
        ],
        "open": [100.0, 101.0, 102.0],
        "high": [100.5, 101.5, 102.5],
        "low": [99.5, 100.5, 101.5],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000, 1100, 1200],
    })
    
    result = aggregate_kbar(df, 30, profile)
    
    # All bars should be in DAY session
    assert "session" in result.columns, "Result must include session column"
    assert all(result["session"] == "DAY"), f"All bars should be DAY session, got {result['session'].unique()}"


