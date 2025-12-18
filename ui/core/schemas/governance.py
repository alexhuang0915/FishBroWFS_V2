"""Pydantic schema for governance.json validation.

Validates governance decisions with KEEP/DROP/FREEZE and evidence chain.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional, Literal

from ui.core.evidence import EvidenceLink


Decision = Literal["KEEP", "DROP", "FREEZE"]


class EvidenceLinkModel(BaseModel):
    """Evidence link model for governance."""
    source_path: str
    json_pointer: str
    note: str = ""


class GovernanceDecisionRow(BaseModel):
    """
    Governance decision row schema.
    
    Represents a single governance decision with rule_id and evidence chain.
    """
    strategy_id: str
    decision: Decision
    rule_id: str  # "R1"/"R2"/"R3"
    reason: str = ""
    run_id: str
    stage: str
    config_hash: Optional[str] = None
    
    evidence: List[EvidenceLinkModel] = Field(default_factory=list)
    metrics_snapshot: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from existing schema (for backward compatibility)
    candidate_id: Optional[str] = None
    reasons: Optional[List[str]] = None
    created_at: Optional[str] = None
    git_sha: Optional[str] = None
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields for backward compatibility


class GovernanceReport(BaseModel):
    """
    Governance report schema.
    
    Validates governance.json structure with decision rows and metadata.
    Supports both items format and rows format.
    """
    config_hash: str  # Required top-level field for DIRTY check contract
    schema_version: Optional[str] = None
    run_id: str
    rows: List[GovernanceDecisionRow] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from existing schema (for backward compatibility)
    items: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields for backward compatibility
