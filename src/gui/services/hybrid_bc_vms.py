"""
Hybrid BC v1.1 ViewModels for Shadow Adoption.

Defines typed ViewModels that cannot carry performance metrics in Layer 1/2.
"""

from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JobIndexVM:
    """
    ViewModel for Layer 1 (Job Index/List).
    
    Contains only operational fields, no performance metrics.
    """
    job_id: str
    short_id: str
    status: str
    status_text: str
    relative_time: str
    duration_text: str  # Operational duration only (not performance signal)
    job_type: str  # "Single" or "WFS"
    note_excerpt: str  # 1-line excerpt
    
    # Additional operational fields from current JobsTableModel
    strategy_name: str = ""
    instrument: str = ""
    timeframe: str = ""
    run_mode: str = ""
    season: str = ""
    created_at: str = ""
    finished_at: str = ""
    
    # Explicitly prohibited fields (for type safety)
    # No score, sharpe, cagr, mdd, drawdown, roi, rank, net_profit, profit, pnl


@dataclass
class JobContextVM:
    """
    ViewModel for Layer 2 (Explain Hub).

    Contains full context for explanation, no performance metrics.
    """
    job_id: str
    full_note: str
    tags: List[str] = field(default_factory=list)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # Health information
    health: Dict[str, Any] = field(default_factory=lambda: {
        "summary": "",
        "error_details_json": None,
        "logs_tail": list()
    })
    
    # Gatekeeper information
    gatekeeper: Dict[str, Any] = field(default_factory=lambda: {
        "total_permutations": 0,
        "valid_candidates": 0,
        "plateau_check": "N/A"  # "Pass", "Fail", or "N/A"
    })
    
    # Additional context fields
    status: str = ""
    error_details: Optional[Dict[str, Any]] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    
    # Job lifecycle state (ACTIVE, ARCHIVED, PURGED)
    lifecycle_state: str = "ACTIVE"
    
    # Explicitly prohibited fields (for type safety)
    # No performance metrics


@dataclass
class JobAnalysisVM:
    """
    ViewModel for Layer 3 (Analysis Drawer).
    
    Contains full analysis payload including performance metrics.
    """
    job_id: str
    payload: Dict[str, Any]  # Raw report data with metrics allowed
    
    # Convenience fields
    report_type: str = ""  # "strategy" or "portfolio"
    metrics: Dict[str, Any] = field(default_factory=dict)
    series: Dict[str, Any] = field(default_factory=dict)


# Type aliases for clarity
PlateauCheck = Literal["Pass", "Fail", "N/A"]