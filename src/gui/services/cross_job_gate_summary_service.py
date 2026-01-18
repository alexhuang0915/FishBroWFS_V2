"""
Cross-job Gate Summary Dashboard Service (DP7).

Provides a matrix view of gate summaries across multiple jobs for dashboard display.
Read-only service that aggregates existing gate summaries without recompute.

Key Features:
- Fetches jobs list from supervisor API
- For each job, fetches consolidated gate summary
- Aggregates into matrix format for dashboard display
- Provides summary statistics (PASS/WARN/FAIL counts)
- No recompute - uses existing gate summary artifacts
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass

from gui.services.supervisor_client import get_jobs
from gui.services.consolidated_gate_summary_service import (
    get_consolidated_gate_summary_service,
    ConsolidatedGateSummaryService,
)
from contracts.portfolio.gate_summary_schemas import (
    GateSummaryV1,
    GateItemV1,
    GateStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class JobGateSummary:
    """Gate summary for a single job in the dashboard matrix."""
    job_id: str
    job_data: Dict[str, Any]  # Raw job data from supervisor
    gate_summary: GateSummaryV1
    fetched_at: datetime


@dataclass
class CrossJobGateSummaryMatrix:
    """Matrix of gate summaries across multiple jobs."""
    jobs: List[JobGateSummary]
    summary_stats: Dict[str, int]  # e.g., {"total": 10, "pass": 8, "warn": 1, "fail": 1}
    fetched_at: datetime
    source: str = "cross_job_gate_summary_service"


class CrossJobGateSummaryService:
    """Service for fetching and aggregating gate summaries across multiple jobs."""
    
    def __init__(
        self,
        consolidated_service: Optional[ConsolidatedGateSummaryService] = None,
        jobs_limit: int = 50,
    ):
        self.consolidated_service = consolidated_service or get_consolidated_gate_summary_service()
        self.jobs_limit = jobs_limit
    
    def fetch_jobs_list(self) -> List[Dict[str, Any]]:
        """Fetch jobs list from supervisor API."""
        try:
            jobs = get_jobs(limit=self.jobs_limit)
            if not isinstance(jobs, list):
                logger.warning(f"Unexpected jobs response type: {type(jobs)}")
                return []
            return jobs
        except Exception as e:
            logger.error(f"Failed to fetch jobs list: {e}")
            return []
    
    def fetch_gate_summary_for_job(self, job_id: str) -> GateSummaryV1:
        """Fetch consolidated gate summary for a specific job. Never returns None."""
        try:
            summary = self.consolidated_service.fetch_consolidated_summary(job_id=job_id)
            if summary is None:
                logger.warning(f"Consolidated service returned None for job {job_id}")
                return self._create_placeholder_summary(job_id)
            return summary
        except Exception as e:
            logger.error(f"Failed to fetch gate summary for job {job_id}: {e}")
            # Create error fallback summary (no-silent failure)
            return self._create_error_summary(job_id, e)
    
    def build_matrix(self) -> CrossJobGateSummaryMatrix:
        """Build cross-job gate summary matrix.
        
        Steps:
        1. Fetch jobs list from supervisor
        2. For each job, fetch consolidated gate summary
        3. Aggregate into matrix format
        4. Calculate summary statistics
        """
        # Fetch jobs list
        jobs_list = self.fetch_jobs_list()
        if not jobs_list:
            logger.warning("No jobs found for cross-job gate summary matrix")
            return self._build_empty_matrix()
        
        # Process each job
        job_summaries = []
        pass_count = 0
        warn_count = 0
        fail_count = 0
        unknown_count = 0
        
        for job_data in jobs_list:
            job_id = job_data.get("job_id")
            if not job_id:
                logger.warning(f"Job data missing job_id: {job_data}")
                continue
            
            # Fetch gate summary for this job (never returns None)
            gate_summary = self.fetch_gate_summary_for_job(job_id)
            
            # Count by overall status
            status = gate_summary.overall_status
            if status == GateStatus.PASS:
                pass_count += 1
            elif status == GateStatus.WARN:
                warn_count += 1
            elif status == GateStatus.REJECT:
                fail_count += 1
            else:
                unknown_count += 1
            
            # Create job summary
            job_summary = JobGateSummary(
                job_id=job_id,
                job_data=job_data,
                gate_summary=gate_summary,
                fetched_at=datetime.now(timezone.utc),
            )
            job_summaries.append(job_summary)
        
        # Build summary statistics
        total = len(job_summaries)
        summary_stats = {
            "total": total,
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "unknown": unknown_count,
        }
        
        return CrossJobGateSummaryMatrix(
            jobs=job_summaries,
            summary_stats=summary_stats,
            fetched_at=datetime.now(timezone.utc),
        )
    
    def _build_empty_matrix(self) -> CrossJobGateSummaryMatrix:
        """Build empty matrix for error cases."""
        return CrossJobGateSummaryMatrix(
            jobs=[],
            summary_stats={
                "total": 0,
                "pass": 0,
                "warn": 0,
                "fail": 0,
                "unknown": 0,
            },
            fetched_at=datetime.now(timezone.utc),
        )
    
    def _create_error_summary(self, job_id: str, error: Exception) -> GateSummaryV1:
        """Create error gate summary for fetch failures (no-silent failure)."""
        from contracts.portfolio.gate_summary_schemas import create_gate_summary_from_gates
        
        # Build error details with L6 telemetry
        error_details = {
            "error_class": error.__class__.__name__,
            "error_message": str(error),
            "error_path": "gui.cross_job_gate_summary_service.fetch_gate_summary_for_job",
            "raw": {},  # Sanitized empty dict
        }
        
        error_gate = GateItemV1(
            gate_id="gate_summary_fetch_error",
            gate_name="Gate Summary Fetch",
            status=GateStatus.REJECT,  # ERROR status (REJECT represents error)
            message=f"Failed to fetch gate summary for job {job_id}: {error.__class__.__name__}",
            reason_codes=["GATE_SUMMARY_FETCH_ERROR"],
            evidence_refs=[],
            evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
            evaluator="cross_job_gate_summary_service",
        )
        # Note: GateItemV1 doesn't have a 'details' field yet - will be added in Patch C
        
        return create_gate_summary_from_gates(
            gates=[error_gate],
            source="cross_job_error_fallback",
            evaluator="cross_job_gate_summary_service",
        )
    
    def _create_placeholder_summary(self, job_id: str) -> GateSummaryV1:
        """Create placeholder gate summary for jobs without gate summary."""
        from contracts.portfolio.gate_summary_schemas import create_gate_summary_from_gates
        
        placeholder_gate = GateItemV1(
            gate_id="gate_summary_unavailable",
            gate_name="Gate Summary",
            status=GateStatus.UNKNOWN,
            message=f"Gate summary not available for job {job_id}",
            reason_codes=["GATE_SUMMARY_UNAVAILABLE"],
            evidence_refs=[],
            evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
            evaluator="cross_job_gate_summary_service",
        )
        
        return create_gate_summary_from_gates(
            gates=[placeholder_gate],
            source="cross_job",
            evaluator="cross_job_gate_summary_service",
        )
    
    def get_job_gate_status(self, job_id: str) -> GateStatus:
        """Get gate status for a specific job (convenience method)."""
        gate_summary = self.fetch_gate_summary_for_job(job_id)
        return gate_summary.overall_status
    
    def get_jobs_by_status(self, status: GateStatus) -> List[str]:
        """Get list of job IDs with specific gate status."""
        matrix = self.build_matrix()
        return [
            job_summary.job_id
            for job_summary in matrix.jobs
            if job_summary.gate_summary.overall_status == status
        ]


# Singleton instance for convenience
_cross_job_gate_summary_service = CrossJobGateSummaryService()


def get_cross_job_gate_summary_service() -> CrossJobGateSummaryService:
    """Return the singleton cross-job gate summary service instance."""
    return _cross_job_gate_summary_service


def fetch_cross_job_gate_summary_matrix() -> CrossJobGateSummaryMatrix:
    """Convenience function to fetch cross-job gate summary matrix."""
    return _cross_job_gate_summary_service.build_matrix()