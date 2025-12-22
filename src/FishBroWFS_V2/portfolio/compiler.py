
"""Portfolio compiler - compile PortfolioSpec to Funnel job configs.

Phase 8: Convert portfolio specification to executable job configurations.
"""

from __future__ import annotations

from typing import Dict, List

from FishBroWFS_V2.portfolio.spec import PortfolioSpec


def compile_portfolio(spec: PortfolioSpec) -> List[Dict[str, any]]:
    """Compile portfolio specification to job configurations.
    
    Each enabled leg produces one job_cfg dict.
    
    Args:
        spec: Portfolio specification
        
    Returns:
        List of job configuration dicts (one per enabled leg)
    """
    jobs = []
    
    for leg in spec.legs:
        if not leg.enabled:
            continue
        
        # Build job configuration
        job_cfg: Dict[str, any] = {
            # Portfolio metadata
            "portfolio_id": spec.portfolio_id,
            "portfolio_version": spec.version,
            
            # Leg metadata
            "leg_id": leg.leg_id,
            "symbol": leg.symbol,
            "timeframe_min": leg.timeframe_min,
            "session_profile": leg.session_profile,  # Path, passed as-is to pipeline
            
            # Strategy metadata
            "strategy_id": leg.strategy_id,
            "strategy_version": leg.strategy_version,
            
            # Strategy parameters
            "params": dict(leg.params),  # Copy dict
            
            # Optional: tags for categorization
            "tags": list(leg.tags),  # Copy list
        }
        
        jobs.append(job_cfg)
    
    return jobs


