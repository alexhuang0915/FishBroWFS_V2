from __future__ import annotations

import numpy as np

from FishBroWFS_V2.stage0.ma_proxy import stage0_score_ma_proxy


def test_stage0_scores_shape_and_ordering_trend_series() -> None:
    # Simple upward trend: MA(5)-MA(20) should be mostly positive => positive score
    n = 500
    close = np.linspace(100.0, 200.0, n, dtype=np.float64)

    params = np.array(
        [
            [5.0, 20.0, 0.0],
            [20.0, 5.0, 0.0],  # inverted => should score worse
            [1.0, 2.0, 0.0],
        ],
        dtype=np.float64,
    )

    scores = stage0_score_ma_proxy(close, params)
    assert scores.shape == (3,)
    assert np.isfinite(scores[0])
    assert np.isfinite(scores[1])
    assert np.isfinite(scores[2])
    assert scores[0] > scores[1]


def test_stage0_rejects_invalid_lengths() -> None:
    close = np.linspace(100.0, 101.0, 50, dtype=np.float64)
    params = np.array([[0.0, 10.0], [10.0, 0.0], [1000.0, 5.0]], dtype=np.float64)
    scores = stage0_score_ma_proxy(close, params)
    assert scores.shape == (3,)
    assert scores[0] == -np.inf
    assert scores[1] == -np.inf
    assert scores[2] == -np.inf


