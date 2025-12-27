
"""Test session classification for CME.MNQ."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.session.classify import classify_session
from data.session.loader import load_session_profile


@pytest.fixture
def mnq_profile(profiles_root: Path) -> Path:
    """Load CME.MNQ session profile."""
    profile_path = profiles_root / "CME_MNQ_TPE_v1.yaml"
    return profile_path


def test_mnq_day_session(mnq_profile: Path) -> None:
    """Test DAY session classification for CME.MNQ."""
    profile = load_session_profile(mnq_profile)
    
    # Test DAY session times
    assert classify_session("2013/1/1 08:45:00", profile) == "DAY"
    assert classify_session("2013/1/1 10:00:00", profile) == "DAY"
    assert classify_session("2013/1/1 13:44:59", profile) == "DAY"
    
    # Test boundary (end is exclusive)
    assert classify_session("2013/1/1 13:45:00", profile) is None


def test_mnq_night_session(mnq_profile: Path) -> None:
    """Test NIGHT session classification for CME.MNQ."""
    profile = load_session_profile(mnq_profile)
    
    # Test NIGHT session times (spans midnight)
    assert classify_session("2013/1/1 21:00:00", profile) == "NIGHT"
    assert classify_session("2013/1/1 23:59:59", profile) == "NIGHT"
    assert classify_session("2013/1/2 00:00:00", profile) == "NIGHT"
    assert classify_session("2013/1/2 05:59:59", profile) == "NIGHT"
    
    # Test boundary (end is exclusive)
    assert classify_session("2013/1/2 06:00:00", profile) is None


def test_mnq_outside_session(mnq_profile: Path) -> None:
    """Test timestamps outside trading sessions."""
    profile = load_session_profile(mnq_profile)
    
    # Between sessions
    assert classify_session("2013/1/1 14:00:00", profile) is None
    assert classify_session("2013/1/1 20:59:59", profile) is None


