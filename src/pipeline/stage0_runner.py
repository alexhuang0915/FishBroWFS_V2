
"""Stage0 runner - proxy ranking without PnL metrics.

Stage0 is a fast proxy filter that ranks parameters without running full backtests.
It MUST NOT compute any PnL-related metrics (Net/MDD/SQN/Sharpe/WinRate/Equity/DD).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from config.constants import STAGE0_PROXY_NAME
from stage0.ma_proxy import stage0_score_ma_proxy


@dataclass(frozen=True)
class Stage0Result:
    """
    Stage0 result - proxy ranking only.
    
    Contains ONLY:
    - param_id: parameter index
    - proxy_value: proxy ranking value (higher is better)
    - warmup_ok: optional warmup validation flag
    - meta: optional metadata dict
    
    FORBIDDEN fields (must not exist):
    - Any PnL metrics: Net, MDD, SQN, Sharpe, WinRate, Equity, DD, etc.
    """
    param_id: int
    proxy_value: float
    warmup_ok: Optional[bool] = None
    meta: Optional[dict] = None


def run_stage0(
    close: np.ndarray,
    params_matrix: np.ndarray,
    *,
    proxy_name: str = STAGE0_PROXY_NAME,
) -> List[Stage0Result]:
    """
    Run Stage0 proxy ranking.
    
    Args:
        close: float32 or float64 1D array (n_bars,) - close prices (will use float32 internally)
        params_matrix: float32 or float64 2D array (n_params, >=2) (will use float32 internally)
            - col0: fast_len (for MA proxy)
            - col1: slow_len (for MA proxy)
            - additional columns allowed and ignored
        proxy_name: name of proxy to use (default: ma_proxy_v0)
        
    Returns:
        List of Stage0Result, one per parameter set.
        Results are in same order as params_matrix rows.
        
    Note:
        - This function MUST NOT compute any PnL metrics
        - Only proxy_value is computed for ranking purposes
        - Uses float32 internally for memory optimization
    """
    if proxy_name != "ma_proxy_v0":
        raise ValueError(f"Unsupported proxy: {proxy_name}. Only 'ma_proxy_v0' is supported in Phase 4.")
    
    # Compute proxy scores
    scores = stage0_score_ma_proxy(close, params_matrix)
    
    # Build results
    n_params = params_matrix.shape[0]
    results: List[Stage0Result] = []
    
    for i in range(n_params):
        score = float(scores[i])
        
        # Check warmup: if score is -inf, warmup failed
        warmup_ok = not np.isinf(score) if not np.isnan(score) else False
        
        results.append(
            Stage0Result(
                param_id=i,
                proxy_value=score,
                warmup_ok=warmup_ok,
                meta=None,
            )
        )
    
    return results


