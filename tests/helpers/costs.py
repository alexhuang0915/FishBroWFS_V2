"""Test helpers for cost models."""
from typing import Tuple

def get_test_costs(symbol: str) -> Tuple[float, float]:
    """
    Returns a non-zero, deterministic commission and slippage for testing.
    This avoids test dependency on live config files.

    Args:
        symbol: The instrument symbol (e.g., "CME.MNQ"). It's not used in this
                mock implementation but kept for API compatibility.

    Returns:
        A tuple of (commission, slippage).
    """
    # Using non-zero, deterministic values for tests
    commission = 0.5  # $0.50 per side
    slippage = 1.25   # $1.25 per side
    return commission, slippage

def get_test_commission(symbol: str) -> float:
    """Returns a non-zero, deterministic commission for testing."""
    return get_test_costs(symbol)[0]

def get_test_slippage(symbol: str) -> float:
    """Returns a non-zero, deterministic slippage for testing."""
    return get_test_costs(symbol)[1]