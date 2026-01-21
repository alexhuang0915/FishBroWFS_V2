
"""Test K-bar aggregation: no cross-session aggregation."""

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


def test_no_cross_session_60m(mnq_profile: Path) -> None:
    """Test 60-minute bars do not cross session boundaries."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars that span DAY session end and NIGHT session start
    df = pd.DataFrame({
        "ts_str": [
            "2013/1/1 13:30:00",  # First TRADING window
            "2013/1/1 13:40:00",  # First TRADING window
            "2013/1/1 13:44:00",  # First TRADING window (last bar before end)
            "2013/1/1 21:00:00",  # Second TRADING window start
            "2013/1/1 21:10:00",  # Second TRADING window
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })
    
    result = aggregate_kbar(df, 60, profile)
    
    # Verify no bar contains both TRADING windows
    assert "session" in result.columns, "Result must include session column"
    
    # Must have both windows (both labeled TRADING)
    assert set(result["session"].dropna()) == {"TRADING"}, (
        f"Should have TRADING sessions, got {set(result['session'].dropna())}"
    )
    
    # Should have two bars (one per window)
    assert len(result) == 2, f"Should have 2 bars (one per TRADING window), got {len(result)}"
    
    # Verify no bar mixes windows (each row has exactly one session)
    assert result["session"].notna().all(), "All bars must have a session label"
    assert len(result[result["session"].isna()]) == 0, "No bar should have session=None"


def test_no_cross_session_30m(mnq_profile: Path) -> None:
    """Test 30-minute bars do not cross session boundaries."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars at DAY session end (now TRADING window)
    df = pd.DataFrame({
        "ts_str": [
            "2013/1/1 13:30:00",
            "2013/1/1 13:40:00",
            "2013/1/1 13:44:00",  # Last bar in first TRADING window
        ],
        "open": [100.0, 101.0, 102.0],
        "high": [100.5, 101.5, 102.5],
        "low": [99.5, 100.5, 101.5],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000, 1100, 1200],
    })
    
    result = aggregate_kbar(df, 30, profile)
    
    # All bars should be in TRADING session
    assert "session" in result.columns, "Result must include session column"
    assert all(result["session"] == "TRADING"), f"All bars should be TRADING session, got {result['session'].unique()}"


