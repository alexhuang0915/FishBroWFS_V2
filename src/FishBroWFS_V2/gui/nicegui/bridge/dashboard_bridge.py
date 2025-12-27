"""
DashboardBridge - Single audited gateway for UI pages to access dashboard snapshot.

UI pages must ONLY call methods on this class; no direct ControlAPIClient calls.
This eliminates "whack-a-mole" NameErrors by providing a stable, validated contract.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from FishBroWFS_V2.gui.contracts.dashboard_dto import (
    DashboardSnapshotDTO,
    PortfolioStatusDTO,
    DeployStatusDTO,
    ActiveOpDTO,
    CandidateDTO,
    OperationSummaryDTO,
    PortfolioDeployStateDTO,
    BuildInfoDTO,
)

logger = logging.getLogger(__name__)


def _get_control_client_safe():
    """Get ControlAPIClient instance safely for use by other bridges."""
    from .worker_bridge import _get_control_client_safe as worker_safe
    return worker_safe()


# Intelligence generation constants (deterministic)
SCORE_OK = 1.2
SCORE_WARN = 0.9
TOP_N = 5


def _stability_flag(score: float) -> str:
    """Determine stability flag based on score."""
    if score >= SCORE_OK:
        return "OK"
    if score >= SCORE_WARN:
        return "WARN"
    return "DROP"


def _plateau_hint(rank: int, score: float) -> str:
    """Generate plateau hint based on rank."""
    if rank == 1:
        return "Primary candidate (highest score)."
    return f"Backup candidate (rank #{rank})."


def _explanations(rank: int, score: float) -> Tuple[str, ...]:
    """Generate deterministic explanations for a candidate."""
    out: List[str] = []
    if rank == 1:
        out.append("Top candidate by score.")
    if rank <= 3:
        out.append("Top‑3 candidate in latest snapshot.")
    if score >= SCORE_OK:
        out.append(f"Score above OK threshold ({SCORE_OK:.2f}).")
    elif score >= SCORE_WARN:
        out.append(f"Score in WARN band ({SCORE_WARN:.2f}–{SCORE_OK:.2f}).")
    else:
        out.append(f"Score below WARN threshold ({SCORE_WARN:.2f}).")
    out.append("Snapshot‑based; refresh to update.")
    return tuple(out)


class DashboardBridge:
    """
    Single audited gateway for UI pages to access dashboard snapshot.
    
    UI pages must ONLY call methods on this class; no direct ControlAPIClient calls.
    All methods are synchronous for UI compatibility.
    """
    
    def __init__(self, client_factory=None):
        """
        Initialize with a client factory.
        
        Args:
            client_factory: Function that returns a ControlAPIClient instance.
        """
        if client_factory is None:
            client_factory = _get_control_client_safe
        self._client_factory = client_factory
        self._client = None
    
    def _get_client(self):
        """Get or create ControlAPIClient instance."""
        if self._client is None:
            self._client = self._client_factory()
        return self._client
    
    def _run_async(self, coro):
        """Run async coroutine synchronously for UI compatibility."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # Create new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(coro)
    
    def get_snapshot(self) -> DashboardSnapshotDTO:
        """
        Return a complete snapshot of dashboard data with intelligence.
        
        This method:
        - MUST be deterministic (same inputs → same output)
        - MUST NOT perform any side effects (read‑only)
        - MUST fetch data from Control API via existing bridges (JobsBridge, MetaBridge, etc.)
        - MUST NOT introduce any auto‑polling or timers
        - MUST return a frozen DTO with intelligence fields
        """
        try:
            # 1. Season (hardcoded for UI‑1; will be dynamic in UI‑2)
            season_id = "2026Q1"
            
            # 2. System online (health check)
            system_online = self._check_system_online()
            
            # 3. Total runs (count of jobs in season)
            runs_count = self._count_total_runs(season_id)
            
            # 4. Active operations (running jobs)
            active_ops = self._get_active_ops(season_id)
            
            # 5. Worker effective & ops status
            worker_effective = len(active_ops)
            ops_status = "RUNNING" if worker_effective > 0 else "IDLE"
            ops_progress_pct, ops_eta_seconds = self._compute_ops_progress(active_ops)
            
            # 6. Portfolio & deploy state
            portfolio_deploy = self._get_portfolio_deploy_state(season_id)
            
            # 7. Operation summary
            operation_summary = self._get_operation_summary(season_id)
            
            # 8. Top candidates with intelligence
            top_candidates = self._get_top_candidates_with_intelligence(season_id, k=TOP_N)
            
            # 9. System logs (latest 10 lines)
            log_lines = self._get_system_logs()
            
            # 10. Build info (stub)
            build_info = self._get_build_info()
            
            return DashboardSnapshotDTO(
                season_id=season_id,
                system_online=system_online,
                runs_count=runs_count,
                worker_effective=worker_effective,
                ops_status=ops_status,
                ops_progress_pct=ops_progress_pct,
                ops_eta_seconds=ops_eta_seconds,
                portfolio_deploy=portfolio_deploy,
                operation_summary=operation_summary,
                top_candidates=top_candidates,
                log_lines=log_lines,
                build_info=build_info,
            )
        except Exception as e:
            logger.exception("DashboardBridge.get_snapshot failed")
            # Return empty snapshot (fallback)
            return DashboardSnapshotDTO.empty()
    
    def _check_system_online(self) -> bool:
        """Check if Control API is reachable."""
        try:
            client = self._get_client()
            health = self._run_async(client.get_json("/health", timeout=2.0))
            return health.get("status") == "ok"
        except Exception:
            return False
    
    def _count_total_runs(self, season: str) -> int:
        """Count total runs (jobs) in the given season."""
        try:
            from .jobs_bridge import get_jobs_bridge
            bridge = get_jobs_bridge()
            jobs = bridge.list_jobs()
            # Filter by season (if job has season field)
            # For now, assume all jobs belong to the current season
            return len(jobs)
        except Exception:
            return 0
    
    def _get_active_ops(self, season: str) -> Tuple[ActiveOpDTO, ...]:
        """Get active operations (running jobs)."""
        try:
            from .jobs_bridge import get_jobs_bridge
            bridge = get_jobs_bridge()
            jobs = bridge.list_jobs()
            active_ops = []
            for job in jobs:
                status = job.get("status", "").lower()
                if status == "running":
                    job_id = job.get("job_id", "")
                    progress = job.get("progress")
                    # Convert progress percentage (0‑100)
                    progress_pct = float(progress) if progress is not None else None
                    # ETA not available in UI‑1
                    eta_seconds = None
                    # Start time (if available)
                    start_time_str = job.get("start_time")
                    start_time = None
                    if start_time_str:
                        try:
                            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    active_ops.append(ActiveOpDTO(
                        job_id=job_id,
                        status=status,
                        progress_pct=progress_pct,
                        eta_seconds=eta_seconds,
                        start_time=start_time,
                    ))
            # Sort by start_time descending (most recent first)
            active_ops.sort(key=lambda op: op.start_time or datetime.min, reverse=True)
            return tuple(active_ops)
        except Exception:
            return ()
    
    def _compute_ops_progress(self, active_ops: Tuple[ActiveOpDTO, ...]) -> Tuple[int, Optional[int]]:
        """Compute overall ops progress percentage and ETA."""
        if not active_ops:
            return 0, None
        # Average progress (ignore None)
        progresses = [op.progress_pct for op in active_ops if op.progress_pct is not None]
        if progresses:
            avg = sum(progresses) / len(progresses)
            progress_pct = int(round(avg))
        else:
            progress_pct = 0
        # Max ETA (ignore None)
        etas = [op.eta_seconds for op in active_ops if op.eta_seconds is not None]
        eta_seconds = max(etas) if etas else None
        return progress_pct, eta_seconds
    
    def _get_portfolio_deploy_state(self, season: str) -> PortfolioDeployStateDTO:
        """Get portfolio and deploy state."""
        try:
            from .deploy_bridge import get_deploy_bridge
            bridge = get_deploy_bridge()
            portfolio_index = bridge.get_portfolio_index(season)
            # Determine portfolio status
            candidates_count = portfolio_index.get("candidates_count", 0)
            deployed_count = portfolio_index.get("deployed_count", 0)
            pending_count = portfolio_index.get("pending_count", 0)
            if candidates_count == 0:
                portfolio_status = "Empty"
            elif pending_count > 0:
                portfolio_status = "Pending"
            elif deployed_count > 0:
                portfolio_status = "Ready"
            else:
                portfolio_status = "Unknown"
            
            # Determine deploy status
            deployable_jobs = bridge.get_deployable_jobs()
            pending_jobs = len([j for j in deployable_jobs if not j.deployed])
            deploy_status = "Undeployed" if pending_jobs > 0 else "Deployed"
            
            return PortfolioDeployStateDTO(
                portfolio_status=portfolio_status,
                deploy_status=deploy_status,
            )
        except Exception:
            # Fallback stub
            return PortfolioDeployStateDTO(
                portfolio_status="Unknown",
                deploy_status="Unknown",
            )
    
    def _get_operation_summary(self, season: str) -> OperationSummaryDTO:
        """Get operation summary (stub)."""
        # TODO: Implement real operation summary
        return OperationSummaryDTO(
            scanned_strategies=0,
            evaluated_params=0,
            skipped_metrics=0,
            notes=(),
        )
    
    def _get_top_candidates_with_intelligence(self, season: str, k: int) -> Tuple[CandidateDTO, ...]:
        """Get top‑k candidates with intelligence fields."""
        try:
            client = self._get_client()
            # Use season compare topk endpoint
            data = self._run_async(client.get_json(
                f"/seasons/{season}/compare/topk",
                params={"k": k},
                timeout=5.0,
            ))
            items = data.get("items", [])
            raw_candidates = []
            for item in items:
                candidate_id = item.get("candidate_id", "")
                score = item.get("score", 0.0)
                strategy_name = item.get("strategy_id", "")
                dataset = item.get("dataset_id", "")
                timestamp_str = item.get("timestamp")
                timestamp = datetime.now()  # fallback
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    except Exception:
                        pass
                raw_candidates.append({
                    "candidate_id": candidate_id,
                    "instance": candidate_id,  # instance same as candidate_id for now
                    "score": score,
                    "strategy_name": strategy_name,
                    "dataset": dataset,
                    "timestamp": timestamp,
                })
            # Sort by (-score, candidate_id)
            raw_candidates.sort(key=lambda c: (-c["score"], c["candidate_id"]))
            # Enrich with intelligence
            enriched = []
            for i, cand in enumerate(raw_candidates, start=1):
                enriched.append(CandidateDTO(
                    rank=i,
                    candidate_id=cand["candidate_id"],
                    instance=cand["instance"],
                    score=cand["score"],
                    explanations=_explanations(i, cand["score"]),
                    stability_flag=_stability_flag(cand["score"]),
                    plateau_hint=_plateau_hint(i, cand["score"]),
                ))
            return tuple(enriched[:k])
        except Exception:
            return ()
    
    def _get_system_logs(self) -> Tuple[str, ...]:
        """Get latest system logs (UI‑1 stub)."""
        # TODO: Implement proper system logs bridge
        # For UI‑1, return empty tuple
        return ()
    
    def _get_build_info(self) -> Optional[BuildInfoDTO]:
        """Get build information (stub)."""
        # TODO: Implement real build info
        return None


# Singleton instance
_dashboard_bridge_instance: Optional[DashboardBridge] = None


def get_dashboard_bridge() -> DashboardBridge:
    """
    Get singleton DashboardBridge instance.
    
    This is the main entry point for UI pages.
    
    Returns:
        DashboardBridge instance.
    """
    global _dashboard_bridge_instance
    if _dashboard_bridge_instance is None:
        _dashboard_bridge_instance = DashboardBridge()
    return _dashboard_bridge_instance


def reset_dashboard_bridge() -> None:
    """Reset the singleton DashboardBridge instance (for testing)."""
    global _dashboard_bridge_instance
    _dashboard_bridge_instance = None