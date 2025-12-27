"""
Dashboard Data Transfer Objects (DTOs) for UI‑1/2 deterministic dashboard.

All DTOs are frozen (immutable) and have deterministic ordering when represented as tuples.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class PortfolioStatusDTO:
    """Portfolio status snapshot (legacy)."""
    candidates_count: int
    deployed_count: int
    pending_count: int


@dataclass(frozen=True)
class DeployStatusDTO:
    """Deployment status snapshot (legacy)."""
    ready: bool
    pending_jobs: int
    last_deploy_time: Optional[datetime]


@dataclass(frozen=True)
class ActiveOpDTO:
    """Active operation (job) snapshot."""
    job_id: str
    status: str  # "running", "completed", "failed", "queued"
    progress_pct: Optional[float]  # 0‑100, None if not applicable
    eta_seconds: Optional[int]  # seconds remaining, None if unknown
    start_time: Optional[datetime]


@dataclass(frozen=True)
class CandidateDTO:
    """Candidate snapshot (top‑k candidates) with intelligence."""
    rank: int
    candidate_id: str
    instance: str
    score: float  # higher is better

    # UI‑1/2 intelligence (all deterministic, server/bridge computed)
    explanations: Tuple[str, ...]       # "Why selected" bullets
    stability_flag: str                 # "OK" | "WARN" | "DROP"
    plateau_hint: str                   # one‑line summary


@dataclass(frozen=True)
class OperationSummaryDTO:
    """Operation summary snapshot."""
    scanned_strategies: int
    evaluated_params: int
    skipped_metrics: int
    notes: Tuple[str, ...]              # optional summary bullets


@dataclass(frozen=True)
class PortfolioDeployStateDTO:
    """Portfolio and deploy state snapshot."""
    portfolio_status: str               # "Empty" | "Pending" | "Ready" | "Unknown"
    deploy_status: str                  # "Undeployed" | "Deployed" | "Unknown"


@dataclass(frozen=True)
class BuildInfoDTO:
    """Build information snapshot."""
    version: str
    commit_hash: str
    build_time: Optional[datetime]


@dataclass(frozen=True)
class DashboardSnapshotDTO:
    """
    Complete dashboard snapshot (UI‑1/2).

    This DTO is the single source of truth for the dashboard.
    All fields are frozen and ordering is deterministic:
    - active_ops: sorted by start_time descending (most recent first)
    - top_candidates: sorted by (-score, candidate_id)
    - log_lines: sorted by timestamp descending (most recent first)
    """
    season_id: str
    system_online: bool
    runs_count: int

    worker_effective: int
    ops_status: str                     # "IDLE" | "RUNNING"
    ops_progress_pct: int               # 0..100
    ops_eta_seconds: Optional[int]

    portfolio_deploy: PortfolioDeployStateDTO
    operation_summary: OperationSummaryDTO

    top_candidates: Tuple[CandidateDTO, ...]  # deterministic ordering
    log_lines: Tuple[str, ...]          # last N lines snapshot

    build_info: Optional[BuildInfoDTO]

    @classmethod
    def empty(cls) -> DashboardSnapshotDTO:
        """Return an empty snapshot (for fallback)."""
        return cls(
            season_id="",
            system_online=False,
            runs_count=0,
            worker_effective=0,
            ops_status="IDLE",
            ops_progress_pct=0,
            ops_eta_seconds=None,
            portfolio_deploy=PortfolioDeployStateDTO(
                portfolio_status="Unknown",
                deploy_status="Unknown",
            ),
            operation_summary=OperationSummaryDTO(
                scanned_strategies=0,
                evaluated_params=0,
                skipped_metrics=0,
                notes=(),
            ),
            top_candidates=(),
            log_lines=(),
            build_info=None,
        )