
"""Governance schema for decision tracking and auditability.

Single Source of Truth (SSOT) for governance decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from core.schemas.governance import Decision


@dataclass(frozen=True)
class EvidenceRef:
    """
    Reference to evidence used in governance decision.
    
    Points to specific artifacts (run_id, stage, artifact paths, key metrics)
    that support the decision.
    """
    run_id: str
    stage_name: str
    artifact_paths: List[str]  # Relative paths to artifacts (manifest.json, metrics.json, etc.)
    key_metrics: Dict[str, Any]  # Key metrics extracted from artifacts


@dataclass(frozen=True)
class GovernanceItem:
    """
    Governance decision for a single candidate.
    
    Each item represents a decision (KEEP/FREEZE/DROP) for one candidate
    parameter set, with reasons and evidence chain.
    """
    candidate_id: str  # Stable identifier: strategy_id:params_hash[:12]
    decision: Decision
    reasons: List[str]  # Human-readable reasons for decision
    evidence: List[EvidenceRef]  # Evidence chain supporting decision
    created_at: str  # ISO8601 with Z suffix (UTC)
    git_sha: str  # Git SHA at time of governance evaluation


@dataclass(frozen=True)
class GovernanceReport:
    """
    Complete governance report for a set of candidates.
    
    Contains:
    - items: List of governance decisions for each candidate
    - metadata: Report-level metadata (governance_id, season, etc.)
    """
    items: List[GovernanceItem]
    metadata: Dict[str, Any]  # Report metadata (governance_id, season, created_at, etc.)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "items": [
                {
                    "candidate_id": item.candidate_id,
                    "decision": item.decision.value,
                    "reasons": item.reasons,
                    "evidence": [
                        {
                            "run_id": ev.run_id,
                            "stage_name": ev.stage_name,
                            "artifact_paths": ev.artifact_paths,
                            "key_metrics": ev.key_metrics,
                        }
                        for ev in item.evidence
                    ],
                    "created_at": item.created_at,
                    "git_sha": item.git_sha,
                }
                for item in self.items
            ],
            "metadata": self.metadata,
        }


