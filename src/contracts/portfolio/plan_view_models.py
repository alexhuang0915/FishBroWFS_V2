
"""Plan view models for human-readable portfolio plan representation."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class PortfolioPlanView(BaseModel):
    """Human-readable view of a portfolio plan."""
    
    # Core identification
    plan_id: str
    generated_at_utc: str
    
    # Source information
    source: Dict[str, Any]
    
    # Configuration summary
    config_summary: Dict[str, Any]
    
    # Universe statistics
    universe_stats: Dict[str, Any]
    
    # Weight distribution
    weight_distribution: Dict[str, Any]
    
    # Top candidates (for display)
    top_candidates: List[Dict[str, Any]]
    
    # Constraints report
    constraints_report: Dict[str, Any]
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


