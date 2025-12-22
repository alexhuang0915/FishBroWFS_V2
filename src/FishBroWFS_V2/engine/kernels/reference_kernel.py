
"""Reference kernel - adapter for matcher_core (testing/debugging only).

This kernel wraps matcher_core.simulate() and should only be used for:
- Testing alignment between kernels
- Debugging semantic correctness
- Reference implementation verification

It is NOT the main path for production simulation.
"""

from __future__ import annotations

from typing import Iterable, List

from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, SimResult
from FishBroWFS_V2.engine.matcher_core import simulate as simulate_reference


def simulate_reference_matcher(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> SimResult:
    """
    Reference matcher adapter - wraps matcher_core.simulate().
    
    This is an adapter that wraps the reference implementation in matcher_core.
    It should only be used for testing/debugging, not as the main simulation path.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - This wraps matcher_core.simulate() which is the semantic truth source
        - Use only for tests/debug, not for production
    """
    fills: List[Fill] = simulate_reference(bars, intents)
    return SimResult(fills=fills)


