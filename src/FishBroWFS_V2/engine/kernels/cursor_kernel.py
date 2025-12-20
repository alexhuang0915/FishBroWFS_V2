"""Cursor kernel - main simulation path for Phase 4.

This is the primary kernel implementation, optimized for performance.
It uses array/struct inputs and deterministic cursor-based matching.
"""

from __future__ import annotations

from typing import Iterable, List

from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, SimResult
from FishBroWFS_V2.engine.engine_jit import simulate as simulate_jit


def simulate_cursor_kernel(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> SimResult:
    """
    Cursor kernel - main simulation path.
    
    This is the primary kernel for Phase 4. It uses the optimized JIT implementation
    from engine_jit, which provides O(B + I + A) complexity.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - Uses arrays/structs internally, no class callbacks
        - Naming and fields are stable for pipeline usage
        - Deterministic behavior guaranteed
    """
    fills: List[Fill] = simulate_jit(bars, intents)
    return SimResult(fills=fills)
