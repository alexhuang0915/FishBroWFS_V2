"""
Core portfolio module for gate evaluation and evidence aggregation.

This module provides the gate evaluation engine for portfolio governance.
"""

# Version constant for gate evaluation engine
__version__ = "v1.5.0"

# Re-export key components
from .evidence_aggregator import (
    EvidenceAggregator,
    EvidenceIndexV1,
    JobEvidenceSummaryV1,
    GateStatus,
    JobLifecycle,
    DataStatus,
    GatekeeperMetricsV1,
    DataStateV1,
)

from .portfolio_orchestrator import PortfolioOrchestrator

__all__ = [
    "EvidenceAggregator",
    "EvidenceIndexV1",
    "JobEvidenceSummaryV1",
    "GateStatus",
    "JobLifecycle",
    "DataStatus",
    "GatekeeperMetricsV1",
    "DataStateV1",
    "PortfolioOrchestrator",
    "__version__",
]