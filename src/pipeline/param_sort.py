
from __future__ import annotations

import numpy as np


def sort_params_cache_friendly(params: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Cache-friendly sorting for parameter matrix.

    params: shape (n, k) float64.
      Convention (Phase 3B v1):
        col0 = channel_len
        col1 = atr_len
        col2 = stop_mult

    Returns:
      sorted_params: params reordered (view/copy depending on numpy)
      order: indices such that sorted_params = params[order]
    """
    if params.ndim != 2 or params.shape[1] < 3:
        raise ValueError("params must be (n, >=3) array")

    # Primary: channel_len (int-like)
    # Secondary: atr_len (int-like)
    # Tertiary: stop_mult
    ch = params[:, 0]
    atr = params[:, 1]
    sm = params[:, 2]

    order = np.lexsort((sm, atr, ch))
    return params[order], order



