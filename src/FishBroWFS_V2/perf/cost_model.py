
"""Cost model for performance estimation.

Provides predictable cost estimation: given bars and params, estimate execution time.
"""

from __future__ import annotations


def estimate_seconds(
    bars: int,
    params: int,
    cost_ms_per_param: float,
) -> float:
    """
    Estimate execution time in seconds based on cost model.
    
    Cost model assumption:
    - Time is linear in number of parameters only
    - Cost per parameter is measured in milliseconds
    - Formula: time_seconds = (params * cost_ms_per_param) / 1000.0
    - Note: bars parameter is for reference only and does not affect the calculation
    
    Args:
        bars: number of bars (for reference only, not used in calculation)
        params: number of parameters
        cost_ms_per_param: cost per parameter in milliseconds
        
    Returns:
        Estimated time in seconds
        
    Note:
        - This is a simple linear model: time = params * cost_per_param_ms / 1000.0
        - Bars are provided for reference but NOT used in the calculation
        - The model assumes cost per parameter is constant (measured from actual runs)
    """
    if params <= 0:
        return 0.0
    
    if cost_ms_per_param <= 0:
        return 0.0
    
    # Linear model: time = params * cost_per_param_ms / 1000.0
    estimated_seconds = (params * cost_ms_per_param) / 1000.0
    
    return estimated_seconds


