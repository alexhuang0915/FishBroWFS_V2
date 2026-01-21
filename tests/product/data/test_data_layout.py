
import numpy as np
import pytest
from data.layout import normalize_bars


def test_normalize_bars_dtype_and_contiguous():
    o = np.arange(10, dtype=np.float32)[::2]
    h = o + 1
    l = o - 1
    c = o + 0.5

    bars = normalize_bars(o, h, l, c)

    for arr in (bars.open, bars.high, bars.low, bars.close):
        assert arr.dtype == np.float64
        assert arr.flags["C_CONTIGUOUS"]


def test_normalize_bars_reject_nan():
    o = np.array([1.0, np.nan])
    h = np.array([1.0, 2.0])
    l = np.array([0.5, 1.5])
    c = np.array([0.8, 1.8])

    with pytest.raises(ValueError):
        normalize_bars(o, h, l, c)



