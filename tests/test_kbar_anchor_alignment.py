"""Test K-bar aggregation: anchor alignment to Session.start."""

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


def test_anchor_to_session_start_60m(mnq_profile: Path) -> None:
    """Test 60-minute bars are anchored to session start (08:45:00)."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars starting from session start
    df = pd.DataFrame({
        "ts_str": [
            "2013/1/1 08:45:00",  # Session start
            "2013/1/1 08:50:00",
            "2013/1/1 09:00:00",
            "2013/1/1 09:30:00",
            "2013/1/1 09:45:00",  # Should be start of next 60m bucket
            "2013/1/1 10:00:00",
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5, 104.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5],
        "volume": [1000, 1100, 1200, 1300, 1400, 1500],
    })
    
    result = aggregate_kbar(df, 60, profile)
    
    # Verify first bar is anchored to session start
    first_bar_time = result["ts_str"].iloc[0].split(" ")[1]
    assert first_bar_time == "08:45:00", f"First bar should be anchored to 08:45:00, got {first_bar_time}"
    
    # Verify subsequent bars are at 60-minute intervals from start
    if len(result) > 1:
        second_bar_time = result["ts_str"].iloc[1].split(" ")[1]
        assert second_bar_time == "09:45:00", f"Second bar should be at 09:45:00, got {second_bar_time}"


def test_anchor_to_session_start_30m(mnq_profile: Path) -> None:
    """Test 30-minute bars are anchored to session start (08:45:00)."""
    profile = load_session_profile(mnq_profile)
    
    # Create bars starting from session start
    df = pd.DataFrame({
        "ts_str": [
            "2013/1/1 08:45:00",  # Session start
            "2013/1/1 08:50:00",
            "2013/1/1 09:00:00",
            "2013/1/1 09:15:00",  # Should be start of next 30m bucket
            "2013/1/1 09:30:00",
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })
    
    result = aggregate_kbar(df, 30, profile)
    
    # Verify first bar is anchored to session start
    first_bar_time = result["ts_str"].iloc[0].split(" ")[1]
    assert first_bar_time == "08:45:00", f"First bar should be anchored to 08:45:00, got {first_bar_time}"
    
    # Verify subsequent bars are at 30-minute intervals from start
    if len(result) > 1:
        second_bar_time = result["ts_str"].iloc[1].split(" ")[1]
        assert second_bar_time == "09:15:00", f"Second bar should be at 09:15:00, got {second_bar_time}"
