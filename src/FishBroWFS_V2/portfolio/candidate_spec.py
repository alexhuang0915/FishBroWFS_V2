"""
Phase Portfolio Bridge: CandidateSpec for Research → Market boundary.

Research OS can output CandidateSpecs (research candidates) that contain
only information allowed by the boundary contract:
- No trading details (symbol, timeframe, session_profile, etc.)
- No market-specific parameters
- Only research metrics and identifiers that can be mapped later by Market OS

Boundary contract:
- Research OS MUST NOT know any trading details
- Market OS maps CandidateSpec to PortfolioLeg with trading details
- CandidateSpec is deterministic and auditable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CandidateSpec:
    """
    Research candidate specification (boundary-safe).
    
    Contains only information that Research OS is allowed to know:
    - Research identifiers (strategy_id, param_hash)
    - Research metrics (score, confidence, etc.)
    - Research metadata (season, batch_id, job_id)
    - No trading details (symbol, timeframe, session_profile, etc.)
    
    Attributes:
        candidate_id: Unique candidate identifier (e.g., "candidate_001")
        strategy_id: Strategy identifier (e.g., "sma_cross_v1")
        param_hash: Hash of strategy parameters (deterministic)
        research_score: Research metric score (e.g., 1.5)
        research_confidence: Confidence metric (0.0-1.0)
        season: Season identifier (e.g., "2026Q1")
        batch_id: Batch identifier (e.g., "batchA")
        job_id: Job identifier (e.g., "job1")
        tags: Optional tags for categorization
        metadata: Optional additional research metadata (no trading details)
    """
    candidate_id: str
    strategy_id: str
    param_hash: str
    research_score: float
    research_confidence: float = 1.0
    season: Optional[str] = None
    batch_id: Optional[str] = None
    job_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate candidate spec."""
        if not self.candidate_id:
            raise ValueError("candidate_id cannot be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id cannot be empty")
        if not self.param_hash:
            raise ValueError("param_hash cannot be empty")
        if not isinstance(self.research_score, (int, float)):
            raise ValueError(f"research_score must be numeric, got {type(self.research_score)}")
        if not 0.0 <= self.research_confidence <= 1.0:
            raise ValueError(f"research_confidence must be between 0.0 and 1.0, got {self.research_confidence}")
        
        # Ensure metadata does not contain trading details
        forbidden_keys = {"symbol", "timeframe", "session_profile", "market", "exchange", "trading"}
        for key in self.metadata:
            if key.lower() in forbidden_keys:
                raise ValueError(f"metadata key '{key}' contains trading details (boundary violation)")


@dataclass(frozen=True)
class CandidateExport:
    """
    Collection of CandidateSpecs for export.
    
    Used to export research candidates from Research OS to Market OS.
    
    Attributes:
        export_id: Unique export identifier (e.g., "export_2026Q1_topk")
        generated_at: ISO 8601 timestamp
        season: Season identifier
        candidates: List of CandidateSpecs
        deterministic_order: Ordering guarantee
    """
    export_id: str
    generated_at: str
    season: str
    candidates: List[CandidateSpec]
    deterministic_order: str = "candidate_id asc"
    
    def __post_init__(self) -> None:
        """Validate candidate export."""
        if not self.export_id:
            raise ValueError("export_id cannot be empty")
        if not self.generated_at:
            raise ValueError("generated_at cannot be empty")
        if not self.season:
            raise ValueError("season cannot be empty")
        
        # Check candidate_id uniqueness
        candidate_ids = [c.candidate_id for c in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            duplicates = [cid for cid in candidate_ids if candidate_ids.count(cid) > 1]
            raise ValueError(f"Duplicate candidate_id found: {set(duplicates)}")


def create_candidate_from_research(
    *,
    candidate_id: str,
    strategy_id: str,
    params: Dict[str, float],
    research_score: float,
    research_confidence: float = 1.0,
    season: Optional[str] = None,
    batch_id: Optional[str] = None,
    job_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> CandidateSpec:
    """
    Create a CandidateSpec from research results.
    
    Computes param_hash from params dict (deterministic).
    """
    from FishBroWFS_V2.portfolio.hash_utils import hash_params
    
    param_hash = hash_params(params)
    
    return CandidateSpec(
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        param_hash=param_hash,
        research_score=research_score,
        research_confidence=research_confidence,
        season=season,
        batch_id=batch_id,
        job_id=job_id,
        tags=tags or [],
        metadata=metadata or {},
    )