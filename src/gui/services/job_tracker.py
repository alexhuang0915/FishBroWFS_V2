"""
Job Tracker Service - Provides job tracking functionality for UI components.

This service wraps supervisor client functions to provide job tracking
capabilities for the JobTrackerDialog and other UI components.
"""

import logging
from typing import List, Dict, Any

from gui.services.supervisor_client import get_jobs, abort_job

logger = logging.getLogger(__name__)


class JobTracker:
    """Job tracker service for UI components."""
    
    def __init__(self):
        """Initialize job tracker."""
        pass
    
    def get_job_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get list of jobs from supervisor.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of job dictionaries
        """
        try:
            jobs = get_jobs(limit=limit)
            if not isinstance(jobs, list):
                logger.warning(f"Unexpected jobs response type: {type(jobs)}")
                return []
            return jobs
        except Exception as e:
            logger.error(f"Failed to get job list: {e}")
            return []
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.
        
        Args:
            job_id: ID of job to cancel
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        try:
            result = abort_job(job_id)
            # The abort_job API returns a dict, we consider it successful
            # if we get a response without exception
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    def clear_completed_jobs(self) -> int:
        """
        Clear completed jobs.
        
        Note: This is a stub implementation since the supervisor API
        doesn't have a direct "clear completed" endpoint. In a real
        implementation, this would archive or delete completed jobs.
        
        Returns:
            Number of jobs cleared (stub returns 0)
        """
        logger.info("clear_completed_jobs called (stub implementation)")
        return 0


# Singleton instance for convenience
_job_tracker_instance = JobTracker()


def get_job_tracker() -> JobTracker:
    """Get the singleton job tracker instance."""
    return _job_tracker_instance


__all__ = ["JobTracker", "get_job_tracker"]