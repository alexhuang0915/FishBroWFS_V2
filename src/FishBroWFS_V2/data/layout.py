import numpy as np
from FishBroWFS_V2.engine.types import BarArrays


def ensure_float64_contiguous(x: np.ndarray) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    if not arr.flags["C_CONTIGUOUS"]:
        arr = np.ascontiguousarray(arr)
    return arr


def normalize_bars(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> BarArrays:
    arrays = [open_, high, low, close]
    for a in arrays:
        if np.isnan(a).any():
            raise ValueError("NaN detected in input data")

    o = ensure_float64_contiguous(open_)
    h = ensure_float64_contiguous(high)
    l = ensure_float64_contiguous(low)
    c = ensure_float64_contiguous(close)

    return BarArrays(open=o, high=h, low=l, close=c)

