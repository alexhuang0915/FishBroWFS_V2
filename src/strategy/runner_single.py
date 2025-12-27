
from __future__ import annotations

from typing import Dict

import numpy as np

from data.layout import normalize_bars
from engine.types import BarArrays
from strategy.kernel import DonchianAtrParams, run_kernel


def run_single(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params: DonchianAtrParams,
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
) -> Dict[str, object]:
    """
    Wrapper for Phase 3A (GKV): ensure memory layout + call kernel once.
    """
    bars: BarArrays = normalize_bars(open_, high, low, close)

    # Boundary Layout Check: enforce contiguous arrays before entering kernel.
    if not bars.open.flags["C_CONTIGUOUS"]:
        bars = BarArrays(
            open=np.ascontiguousarray(bars.open, dtype=np.float64),
            high=np.ascontiguousarray(bars.high, dtype=np.float64),
            low=np.ascontiguousarray(bars.low, dtype=np.float64),
            close=np.ascontiguousarray(bars.close, dtype=np.float64),
        )

    return run_kernel(bars, params, commission=commission, slip=slip, order_qty=order_qty)



