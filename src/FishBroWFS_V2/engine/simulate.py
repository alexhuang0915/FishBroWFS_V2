
"""Unified simulate entry point for Phase 4.

This module provides the single entry point simulate_run() which routes to
the Cursor kernel (main path) or Reference kernel (testing/debugging only).
"""

from __future__ import annotations

from typing import Iterable

from FishBroWFS_V2.engine.types import BarArrays, OrderIntent, SimResult
from FishBroWFS_V2.engine.kernels.cursor_kernel import simulate_cursor_kernel
from FishBroWFS_V2.engine.kernels.reference_kernel import simulate_reference_matcher


def simulate_run(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
    *,
    use_reference: bool = False,
) -> SimResult:
    """
    Unified simulate entry point - Phase 4 main API.
    
    This is the single entry point for all simulation calls. By default, it uses
    the Cursor kernel (main path). The Reference kernel is only available for
    testing/debugging purposes.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        use_reference: If True, use reference kernel (testing/debug only).
                      Default False uses Cursor kernel (main path).
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - Cursor kernel is the main path for production
        - Reference kernel should only be used for tests/debug
        - This API is stable for pipeline usage
    """
    if use_reference:
        return simulate_reference_matcher(bars, intents)
    return simulate_cursor_kernel(bars, intents)


