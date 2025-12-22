
"""Test session classification for TWF.MXF."""

from __future__ import annotations

from pathlib import Path

import pytest

from FishBroWFS_V2.data.session.classify import classify_session
from FishBroWFS_V2.data.session.loader import load_session_profile


@pytest.fixture
def mxf_profile() -> Path:
    """Load TWF.MXF session profile."""
    profile_path = Path(__file__).parent.parent / "src" / "FishBroWFS_V2" / "data" / "profiles" / "TWF_MXF_TPE_v1.yaml"
    return profile_path


def test_mxf_day_session(mxf_profile: Path) -> None:
    """Test DAY session classification for TWF.MXF."""
    profile = load_session_profile(mxf_profile)
    
    # Test DAY session times
    assert classify_session("2013/1/1 08:45:00", profile) == "DAY"
    assert classify_session("2013/1/1 10:00:00", profile) == "DAY"
    assert classify_session("2013/1/1 13:44:59", profile) == "DAY"
    
    # Test boundary (end is exclusive)
    assert classify_session("2013/1/1 13:45:00", profile) is None


def test_mxf_night_session(mxf_profile: Path) -> None:
    """Test NIGHT session classification for TWF.MXF."""
    profile = load_session_profile(mxf_profile)
    
    # Test NIGHT session times (spans midnight)
    assert classify_session("2013/1/1 15:00:00", profile) == "NIGHT"
    assert classify_session("2013/1/1 23:59:59", profile) == "NIGHT"
    assert classify_session("2013/1/2 00:00:00", profile) == "NIGHT"
    assert classify_session("2013/1/2 04:59:59", profile) == "NIGHT"
    
    # Test boundary (end is exclusive)
    assert classify_session("2013/1/2 05:00:00", profile) is None


def test_mxf_outside_session(mxf_profile: Path) -> None:
    """Test timestamps outside trading sessions."""
    profile = load_session_profile(mxf_profile)
    
    # Between sessions
    assert classify_session("2013/1/1 14:00:00", profile) is None
    assert classify_session("2013/1/1 14:59:59", profile) is None


