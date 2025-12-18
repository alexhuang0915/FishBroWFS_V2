"""KPI Evidence Registry.

Maps KPI names to EvidenceLink (artifact + JSON pointer).
"""

from __future__ import annotations

from typing import Literal

from FishBroWFS_V2.gui.viewer.schema import EvidenceLink

ArtifactName = Literal["manifest", "winners_v2", "governance"]


# KPI Evidence Registry (first version hardcoded, extensible later)
KPI_EVIDENCE_REGISTRY: dict[str, EvidenceLink] = {
    "net_profit": EvidenceLink(
        artifact="winners_v2",
        json_pointer="/summary/net_profit",
        description="Total net profit from winners_v2 summary",
    ),
    "max_drawdown": EvidenceLink(
        artifact="winners_v2",
        json_pointer="/summary/max_drawdown",
        description="Maximum drawdown over full backtest",
    ),
    "num_trades": EvidenceLink(
        artifact="winners_v2",
        json_pointer="/summary/num_trades",
        description="Total number of executed trades",
    ),
    "final_score": EvidenceLink(
        artifact="governance",
        json_pointer="/scoring/final_score",
        description="Governance final score used for KEEP/FREEZE/DROP",
    ),
}


def get_evidence_link(kpi_name: str) -> EvidenceLink | None:
    """
    Get EvidenceLink for KPI name.
    
    Args:
        kpi_name: KPI name to look up
        
    Returns:
        EvidenceLink if found, None otherwise
        
    Contract:
        - Never raises exceptions
        - Returns None for unknown KPI names
    """
    try:
        return KPI_EVIDENCE_REGISTRY.get(kpi_name)
    except Exception:
        return None


def has_evidence(kpi_name: str) -> bool:
    """
    Check if KPI has evidence link.
    
    Args:
        kpi_name: KPI name to check
        
    Returns:
        True if KPI has evidence link, False otherwise
        
    Contract:
        - Never raises exceptions
    """
    try:
        return kpi_name in KPI_EVIDENCE_REGISTRY
    except Exception:
        return False
