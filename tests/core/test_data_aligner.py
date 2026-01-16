"""Test DataAligner metrics reporting."""

import pandas as pd

from core.data_aligner import DataAligner


def test_aligner_hold_metrics():
    data1 = pd.DataFrame({
        "ts": pd.date_range("2026-01-01T00:00:00", periods=5, freq="T"),
        "open": [1, 2, 3, 4, 5],
        "high": [1, 2, 3, 4, 5],
        "low": [1, 2, 3, 4, 5],
        "close": [1, 2, 3, 4, 5],
        "volume": [10, 10, 10, 10, 10],
    })
    data2 = pd.DataFrame({
        "ts": [pd.Timestamp("2026-01-01T00:00:00"), pd.Timestamp("2026-01-01T00:03:00")],
        "open": [100, 110],
        "high": [100, 111],
        "low": [100, 109],
        "close": [100, 110],
        "volume": [5, 5],
    })

    aligner = DataAligner()
    aligned, metrics = aligner.align(data1, data2)

    assert len(aligned) == len(data1)
    assert metrics.data1_bars_total == 5
    assert metrics.data2_updates_total == 2
    assert metrics.data2_hold_bars_total == 3
    assert metrics.data2_hold_ratio == 0.6
    assert metrics.max_consecutive_hold_bars == 2
    assert metrics.top_hold_runs[0]["count"] == 2
    assert "start_ts" in metrics.top_hold_runs[0]
    assert aligned.loc[1, "close"] == 100
    assert aligned.loc[2, "close"] == 100
    assert aligned.loc[3, "close"] == 110
    assert aligned.loc[4, "close"] == 110
