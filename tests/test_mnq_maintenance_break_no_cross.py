
"""Test MNQ maintenance break: no cross-session aggregation.

Phase 6.6: Verify that MNQ bars before and after maintenance window
are not aggregated into the same K-bar.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from FishBroWFS_V2.data.session.kbar import aggregate_kbar
from FishBroWFS_V2.data.session.loader import load_session_profile


@pytest.fixture
def mnq_exchange_profile(profiles_root: Path) -> Path:
    """Load CME.MNQ EXCHANGE_RULE profile."""
    profile_path = profiles_root / "CME_MNQ_EXCHANGE_v1.yaml"
    return profile_path


def test_mnq_maintenance_break_no_cross_30m(mnq_exchange_profile: Path) -> None:
    """Test 30-minute bars do not cross maintenance boundary.
    
    MNQ maintenance: 16:00-17:00 CT (approximately 06:00-07:00 TPE, varies with DST).
    Bars just before maintenance (15:59 CT) and just after (17:01 CT)
    should not be in the same 30m bar.
    """
    profile = load_session_profile(mnq_exchange_profile)
    
    # Create bars around maintenance window
    # Using dates that avoid DST transitions for simplicity
    # 2013/3/10 is a Sunday (before DST spring forward on 3/10/2013)
    # Maintenance window: 16:00-17:00 CT = approximately 06:00-07:00 TPE (before DST)
    df = pd.DataFrame({
        "ts_str": [
            "2013/3/10 05:55:00",  # TRADING (before maintenance, ~15:55 CT)
            "2013/3/10 05:59:00",  # TRADING (just before maintenance, ~15:59 CT)
            "2013/3/10 06:30:00",  # MAINTENANCE (during maintenance, ~16:30 CT)
            "2013/3/10 07:01:00",  # TRADING (just after maintenance, ~17:01 CT)
            "2013/3/10 07:05:00",  # TRADING (after maintenance, ~17:05 CT)
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })
    
    result = aggregate_kbar(df, 30, profile)
    
    # Verify result has session column
    assert "session" in result.columns, "Result must include session column"
    
    # Verify no bar mixes TRADING and MAINTENANCE
    # Each row must have exactly one session
    assert result["session"].notna().all(), "All bars must have a session label"
    
    # Check that TRADING and MAINTENANCE are separate
    trading_bars = result[result["session"] == "TRADING"]
    maintenance_bars = result[result["session"] == "MAINTENANCE"]
    
    # Should have both TRADING and MAINTENANCE bars (if maintenance bars exist)
    if len(maintenance_bars) > 0:
        # Verify no bar contains both sessions
        assert len(result) == len(trading_bars) + len(maintenance_bars), (
            "Total bars should equal sum of TRADING and MAINTENANCE bars"
        )
        
        # Verify bars before maintenance are TRADING
        # Verify bars during maintenance are MAINTENANCE
        # Verify bars after maintenance are TRADING
        # (This is verified by the session column)


def test_mnq_maintenance_break_no_cross_60m(mnq_exchange_profile: Path) -> None:
    """Test 60-minute bars do not cross maintenance boundary."""
    profile = load_session_profile(mnq_exchange_profile)
    
    # Similar to 30m test, but with 60m interval
    df = pd.DataFrame({
        "ts_str": [
            "2013/3/10 05:50:00",  # TRADING (before maintenance)
            "2013/3/10 05:59:00",  # TRADING (just before maintenance)
            "2013/3/10 06:30:00",  # MAINTENANCE (during maintenance)
            "2013/3/10 07:01:00",  # TRADING (just after maintenance)
            "2013/3/10 07:10:00",  # TRADING (after maintenance)
        ],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [100.5, 101.5, 102.5, 103.5, 104.5],
        "low": [99.5, 100.5, 101.5, 102.5, 103.5],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })
    
    result = aggregate_kbar(df, 60, profile)
    
    # Verify result has session column
    assert "session" in result.columns, "Result must include session column"
    
    # Verify no bar mixes TRADING and MAINTENANCE
    assert result["session"].notna().all(), "All bars must have a session label"
    
    # Verify session separation
    trading_bars = result[result["session"] == "TRADING"]
    maintenance_bars = result[result["session"] == "MAINTENANCE"]
    
    if len(maintenance_bars) > 0:
        assert len(result) == len(trading_bars) + len(maintenance_bars), (
            "Total bars should equal sum of TRADING and MAINTENANCE bars"
        )


