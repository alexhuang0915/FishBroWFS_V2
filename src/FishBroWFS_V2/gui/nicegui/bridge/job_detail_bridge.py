"""
JobDetailBridge - Single audited gateway for UI pages to access job details and logs.

UI pages must ONLY call methods on this class; no direct ControlAPIClient calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobDetail:
    """Job detail data structure."""
    job_id: str
    status: str
    created_at: str
    dataset_id: Optional[str] = None
    strategy_id: Optional[str] = None
    symbols: Optional[List[str]] = None
    timeframe_min: Optional[int] = None
    progress: Optional[float] = None
    error: Optional[str] = None
    logs: Optional[List[str]] = None
    artifacts: Optional[List[Dict[str, Any]]] = None


class JobDetailBridge:
    """
    Single audited gateway for UI pages to access job details and logs.
    
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
    
    def get_job_summary(self, job_id: str) -> Dict[str, Any]:
        """
        Get job summary by ID.
        
        Args:
            job_id: Job identifier.
            
        Returns:
            Dictionary with job summary.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                f"/jobs/{job_id}",
                f"/jobs/{job_id}/summary",
                f"/batches/{job_id}",
                f"/batches/{job_id}/summary"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=3.0))
                    if data:
                        return data
                except Exception:
                    continue
            
            # Fallback: try the explicit method if available
            try:
                return self._run_async(client.get_job(job_id))
            except Exception:
                pass
                
            return {}
        except Exception as e:
            logger.exception(f"JobDetailBridge.get_job_summary failed for job_id={job_id}")
            return {"error": str(e)}
    
    def get_job_logs(self, job_id: str, lines: int = 50) -> List[str]:
        """
        Get job logs by ID.
        
        Args:
            job_id: Job identifier.
            lines: Number of log lines to retrieve.
            
        Returns:
            List of log lines.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                f"/jobs/{job_id}/logs",
                f"/jobs/{job_id}/log_tail",
                f"/jobs/{job_id}/run_log_tail",
                f"/batches/{job_id}/logs"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, params={"n": lines}, timeout=3.0))
                    if isinstance(data, dict):
                        # Extract log lines from response
                        for key in ("lines", "logs", "data"):
                            if key in data and isinstance(data[key], list):
                                return [str(line) for line in data[key]]
                    elif isinstance(data, list):
                        return [str(line) for line in data]
                except Exception:
                    continue
            
            # Fallback: try the explicit method if available
            try:
                data = self._run_async(client.log_tail(job_id, n=lines))
                if isinstance(data, dict) and "lines" in data:
                    return data["lines"]
            except Exception:
                pass
                
            return []
        except Exception as e:
            logger.exception(f"JobDetailBridge.get_job_logs failed for job_id={job_id}")
            return [f"Error retrieving logs: {str(e)}"]
    
    def get_job_detail(self, job_id: str) -> JobDetail:
        """
        Get complete job detail including logs.
        
        Args:
            job_id: Job identifier.
            
        Returns:
            JobDetail object.
        """
        summary = self.get_job_summary(job_id)
        logs = self.get_job_logs(job_id)
        
        return JobDetail(
            job_id=job_id,
            status=summary.get("status", "unknown"),
            created_at=summary.get("created_at", ""),
            dataset_id=summary.get("dataset_id"),
            strategy_id=summary.get("strategy_id"),
            symbols=summary.get("symbols"),
            timeframe_min=summary.get("timeframe_min"),
            progress=summary.get("progress"),
            error=summary.get("error"),
            logs=logs,
            artifacts=summary.get("artifacts")
        )
    
    def get_job_status(self, job_id: str) -> str:
        """
        Get job status by ID.
        
        Args:
            job_id: Job identifier.
            
        Returns:
            Job status string.
        """
        summary = self.get_job_summary(job_id)
        return summary.get("status", "unknown")


# Singleton instance
_job_detail_bridge_instance: Optional[JobDetailBridge] = None


def get_job_detail_bridge() -> JobDetailBridge:
    """
    Get singleton JobDetailBridge instance.
    
    This is the main entry point for UI pages.
    
    Returns:
        JobDetailBridge instance.
    """
    global _job_detail_bridge_instance
    if _job_detail_bridge_instance is None:
        _job_detail_bridge_instance = JobDetailBridge()
    return _job_detail_bridge_instance


def reset_job_detail_bridge() -> None:
    """Reset the singleton JobDetailBridge instance (for testing)."""
    global _job_detail_bridge_instance
    _job_detail_bridge_instance = None