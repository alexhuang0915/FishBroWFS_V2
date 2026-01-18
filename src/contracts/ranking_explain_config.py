"""
Ranking Explain Configuration for DP6 Phase II.

Defines configuration thresholds for concentration, plateau quality, and robustness checks.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class RankingExplainConfig(BaseModel):
    """Configuration for ranking explain Phase II governance/risk layer."""
    
    schema_version: str = Field(
        default="1",
        description="Config schema version for forward compatibility"
    )
    
    concentration_topk: int = Field(
        default=20,
        description="Number of top items to consider for concentration analysis",
        ge=1,
        le=100
    )
    
    concentration_top1_error: float = Field(
        default=0.50,
        description="Top1 share threshold for ERROR severity (>= this value)",
        ge=0.0,
        le=1.0
    )
    
    concentration_top1_warn: float = Field(
        default=0.35,
        description="Top1 share threshold for WARN severity (>= this value)",
        ge=0.0,
        le=1.0
    )
    
    plateau_stability_warn_below: float = Field(
        default=0.60,
        description="Plateau stability score threshold for WARN (score < this value)",
        ge=0.0,
        le=1.0
    )
    
    trades_min_warn: int = Field(
        default=10,
        description="Minimum trades threshold for WARN severity",
        ge=1
    )
    
    mdd_abs_min_error: float = Field(
        default=1e-12,
        description="Minimum absolute MDD value to avoid division illusions (ERROR if <= this)",
        ge=0.0
    )
    
    avg_profit_min_error: Optional[float] = Field(
        default=None,
        description="Minimum average profit threshold for ERROR (if None, use scoring_guard_cfg.min_avg_profit)"
    )
    
    def get_avg_profit_threshold(self, scoring_guard_min_avg_profit: float) -> float:
        """Get the average profit threshold to use."""
        if self.avg_profit_min_error is not None:
            return self.avg_profit_min_error
        return scoring_guard_min_avg_profit


# Default configuration instance
DEFAULT_RANKING_EXPLAIN_CONFIG = RankingExplainConfig()


__all__ = [
    "RankingExplainConfig",
    "DEFAULT_RANKING_EXPLAIN_CONFIG",
]