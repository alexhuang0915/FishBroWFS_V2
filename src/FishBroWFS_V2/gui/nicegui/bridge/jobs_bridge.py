"""
JobsBridge - Single audited gateway for UI pages to access job listing and statistics.

UI pages must ONLY call methods on this class; no direct ControlAPIClient calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobSummary:
    """Job summary data structure."""
    job_id: str
    status: str
    created_at: str
    dataset_id: Optional[str] = None
    strategy_id: Optional[str] = None
    progress: Optional[float] = None
    error: Optional[str] = None


class JobsBridge:
    """
    Single audited gateway for UI pages to access job listing and statistics.
    
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
            from .worker_bridge import _get_control_client_safe
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
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        List all jobs.
        
        Returns:
            List of job dictionaries.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                "/jobs",
                "/jobs/list", 
                "/batches",
                "/batches/list"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=3.0))
                    # Normalize to list
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        for key in ("jobs", "items", "batches", "data"):
                            if key in data and isinstance(data[key], list):
                                return data[key]
                except Exception:
                    continue
            
            # Fallback: try the explicit method if available
            try:
                return self._run_async(client.list_jobs())
            except Exception:
                pass
                
            return []
        except Exception as e:
            logger.exception("JobsBridge.list_jobs failed")
            return []
    
    def get_jobs_stats(self) -> Dict[str, Any]:
        """
        Get job statistics.
        
        Returns:
            Dictionary with job statistics.
        """
        jobs = self.list_jobs()
        
        # Calculate basic stats
        total = len(jobs)
        status_counts = {}
        for job in jobs:
            status = job.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total": total,
            "status_counts": status_counts,
            "running": status_counts.get("running", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
        }
    
    def get_job_summaries(self) -> List[JobSummary]:
        """
        Get job summaries as typed objects.
        
        Returns:
            List of JobSummary objects.
        """
        jobs = self.list_jobs()
        summaries = []
        
        for job in jobs:
            summaries.append(JobSummary(
                job_id=job.get("job_id", ""),
                status=job.get("status", "unknown"),
                created_at=job.get("created_at", ""),
                dataset_id=job.get("dataset_id"),
                strategy_id=job.get("strategy_id"),
                progress=job.get("progress"),
                error=job.get("error")
            ))
        
        return summaries
    
    def start_job(self, job_id: str) -> Dict[str, Any]:
        """
        Start a queued job.
        
        Args:
            job_id: Job identifier.
            
        Returns:
            Dictionary with start result.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                f"/jobs/{job_id}/start",
                f"/jobs/{job_id}/run",
                f"/batches/{job_id}/start",
                f"/batches/{job_id}/run"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.post_json(path, json={}, timeout=5.0))
                    if data:
                        return data
                except Exception:
                    continue
            
            # Fallback: try the explicit method if available
            try:
                return self._run_async(client.start_job(job_id))
            except Exception:
                pass
                
            return {"success": False, "error": "Could not start job"}
        except Exception as e:
            logger.exception(f"JobsBridge.start_job failed for job_id={job_id}")
            return {"success": False, "error": str(e)}


# Singleton instance
_jobs_bridge_instance: Optional[JobsBridge] = None


def get_jobs_bridge() -> JobsBridge:
    """
    Get singleton JobsBridge instance.
    
    This is the main entry point for UI pages.
    
    Returns:
        JobsBridge instance.
    """
    global _jobs_bridge_instance
    if _jobs_bridge_instance is None:
        _jobs_bridge_instance = JobsBridge()
    return _jobs_bridge_instance


def reset_jobs_bridge() -> None:
    """Reset the singleton JobsBridge instance (for testing)."""
    global _jobs_bridge_instance
    _jobs_bridge_instance = None