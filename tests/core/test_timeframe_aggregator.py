"""
Test the TimeframeAggregator with roll-time anchoring.
"""

from datetime import datetime, time

import pandas as pd

from core.timeframe_aggregator import TimeframeAggregator


def test_aggregator_windows_around_roll():
    # 1m bars spanning the 15:00 roll
    bars = pd.DataFrame([
        {"ts": "2026-01-01T14:58:00", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
        {"ts": "2026-01-01T14:59:00", "open": 11, "high": 12, "low": 11, "close": 12, "volume": 2},
        {"ts": "2026-01-01T15:00:00", "open": 12, "high": 13, "low": 12, "close": 13, "volume": 3},
        {"ts": "2026-01-01T15:01:00", "open": 13, "high": 14, "low": 13, "close": 14, "volume": 4},
        {"ts": "2026-01-01T15:02:00", "open": 14, "high": 15, "low": 14, "close": 15, "volume": 5},
    ])

    aggregator = TimeframeAggregator(timeframe_min=2, roll_time=time(15, 0))
    result = aggregator.aggregate(bars)

    assert len(result) == 3
    assert result.iloc[0]["ts"] == pd.Timestamp("2026-01-01T15:00:00")
    assert result.iloc[0]["open"] == 10
    assert result.iloc[0]["high"] == 12
    assert result.iloc[0]["low"] == 10
    assert result.iloc[0]["close"] == 12
    assert result.iloc[0]["volume"] == 3

    assert result.iloc[1]["ts"] == pd.Timestamp("2026-01-01T15:02:00")
    assert result.iloc[1]["open"] == 12
    assert result.iloc[1]["close"] == 14
    assert result.iloc[1]["volume"] == 7

    assert result.iloc[2]["ts"] == pd.Timestamp("2026-01-01T15:04:00")
    assert result.iloc[2]["open"] == 14
    assert result.iloc[2]["close"] == 15
    assert result.iloc[2]["volume"] == 5
