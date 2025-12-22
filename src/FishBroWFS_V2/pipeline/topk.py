
"""Top-K selector - deterministic parameter selection.

Selects top K parameters based on Stage0 proxy_value.
Tie-breaking uses param_id to ensure deterministic results.
"""

from __future__ import annotations

from typing import List

from FishBroWFS_V2.config.constants import TOPK_K
from FishBroWFS_V2.pipeline.stage0_runner import Stage0Result


def select_topk(
    stage0_results: List[Stage0Result],
    k: int = TOPK_K,
) -> List[int]:
    """
    Select top K parameters based on proxy_value.
    
    Args:
        stage0_results: List of Stage0Result from Stage0 runner
        k: number of top parameters to select (default: TOPK_K from config)
        
    Returns:
        List of param_id values (indices) for top K parameters.
        Results are sorted by proxy_value (descending), then by param_id (ascending) for tie-break.
        
    Note:
        - Sorting is deterministic: same input always produces same output
        - Tie-break uses param_id (ascending) to ensure stability
        - No manual include/exclude - purely based on proxy_value
    """
    if k <= 0:
        return []
    
    if len(stage0_results) == 0:
        return []
    
    # Sort by proxy_value (descending), then param_id (ascending) for tie-break
    sorted_results = sorted(
        stage0_results,
        key=lambda r: (-r.proxy_value, r.param_id),  # Negative for descending value
    )
    
    # Take top K
    topk_results = sorted_results[:k]
    
    # Return param_id list
    return [r.param_id for r in topk_results]


