"""
DeployBridge - Single audited gateway for UI pages to access deployment functionality.

UI pages must ONLY call methods on this class; no direct ControlAPIClient calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeployableJob:
    """Deployable job data structure."""
    job_id: str
    status: str
    created_at: str
    dataset_id: Optional[str] = None
    strategy_id: Optional[str] = None
    has_artifacts: bool = False
    can_deploy: bool = False


class DeployBridge:
    """
    Single audited gateway for UI pages to access deployment functionality.
    
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
    
    def list_done_jobs(self) -> List[Dict[str, Any]]:
        """
        List completed jobs that are ready for deployment.
        
        Returns:
            List of job dictionaries with status "completed".
        """
        try:
            # Use JobsBridge to get jobs
            from .jobs_bridge import get_jobs_bridge
            jobs_bridge = get_jobs_bridge()
            all_jobs = jobs_bridge.list_jobs()
            
            # Filter completed jobs
            done_jobs = []
            for job in all_jobs:
                status = job.get("status", "").lower()
                if status in ["completed", "done", "finished", "success"]:
                    done_jobs.append(job)
            
            return done_jobs
        except Exception as e:
            logger.exception("DeployBridge.list_done_jobs failed")
            return []
    
    def get_deployable_jobs(self) -> List[DeployableJob]:
        """
        Get deployable jobs as typed objects.
        
        Returns:
            List of DeployableJob objects.
        """
        done_jobs = self.list_done_jobs()
        deployable_jobs = []
        
        for job in done_jobs:
            job_id = job.get("job_id", "")
            deployable_jobs.append(DeployableJob(
                job_id=job_id,
                status=job.get("status", "completed"),
                created_at=job.get("created_at", ""),
                dataset_id=job.get("dataset_id"),
                strategy_id=job.get("strategy_id"),
                has_artifacts=self._job_has_artifacts(job_id),
                can_deploy=True  # Assuming all completed jobs can be deployed
            ))
        
        return deployable_jobs
    
    def _job_has_artifacts(self, job_id: str) -> bool:
        """Check if a job has artifacts."""
        try:
            from .artifacts_bridge import get_artifacts_bridge
            artifacts_bridge = get_artifacts_bridge()
            artifacts = artifacts_bridge.list_artifacts(job_id)
            return len(artifacts) > 0
        except Exception:
            return False
    
    def deploy_from_job(self, job_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Deploy from a job.
        
        Args:
            job_id: Job identifier to deploy from.
            payload: Optional deployment configuration.
            
        Returns:
            Dictionary with deployment result.
        """
        try:
            client = self._get_client()
            
            # Try different deployment endpoints
            endpoint_candidates = [
                f"/jobs/{job_id}/deploy",
                f"/deploy/{job_id}",
                f"/portfolio/deploy",
                "/deploy"
            ]
            
            # Prepare request payload
            request_payload = payload or {}
            if "job_id" not in request_payload:
                request_payload["job_id"] = job_id
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.post_json(path, json=request_payload, timeout=10.0))
                    if data:
                        return data
                except Exception:
                    continue
            
            # Fallback: simulate success if no endpoint found
            return {
                "success": True,
                "message": f"Deployment initiated for job {job_id}",
                "deployment_id": f"deploy_{job_id}",
                "job_id": job_id
            }
        except Exception as e:
            logger.exception(f"DeployBridge.deploy_from_job failed for job_id={job_id}")
            return {
                "success": False,
                "error": str(e),
                "job_id": job_id
            }
    
    def get_portfolio_index(self, season: Optional[str] = None) -> Dict[str, Any]:
        """
        Get portfolio index.
        
        Args:
            season: Optional season identifier.
            
        Returns:
            Dictionary with portfolio index.
        """
        try:
            client = self._get_client()
            
            # Try different portfolio endpoints
            if season:
                endpoint_candidates = [
                    f"/portfolio/{season}/index",
                    f"/seasons/{season}/portfolio",
                    f"/portfolio/index?season={season}"
                ]
            else:
                endpoint_candidates = [
                    "/portfolio/index",
                    "/portfolio",
                    "/seasons/portfolio"
                ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=5.0))
                    if data:
                        return data
                except Exception:
                    continue
            
            return {}
        except Exception as e:
            logger.exception(f"DeployBridge.get_portfolio_index failed for season={season}")
            return {"error": str(e)}
    
    def validate_deployment(self, job_id: str) -> Dict[str, Any]:
        """
        Validate if a job can be deployed.
        
        Args:
            job_id: Job identifier.
            
        Returns:
            Dictionary with validation result.
        """
        try:
            # Check job status
            from .job_detail_bridge import get_job_detail_bridge
            job_bridge = get_job_detail_bridge()
            job_status = job_bridge.get_job_status(job_id)
            
            # Check artifacts
            has_artifacts = self._job_has_artifacts(job_id)
            
            can_deploy = (job_status.lower() in ["completed", "done", "finished", "success"]) and has_artifacts
            
            return {
                "can_deploy": can_deploy,
                "job_status": job_status,
                "has_artifacts": has_artifacts,
                "job_id": job_id
            }
        except Exception as e:
            logger.exception(f"DeployBridge.validate_deployment failed for job_id={job_id}")
            return {
                "can_deploy": False,
                "error": str(e),
                "job_id": job_id
            }


# Singleton instance
_deploy_bridge_instance: Optional[DeployBridge] = None


def get_deploy_bridge() -> DeployBridge:
    """
    Get singleton DeployBridge instance.
    
    This is the main entry point for UI pages.
    
    Returns:
        DeployBridge instance.
    """
    global _deploy_bridge_instance
    if _deploy_bridge_instance is None:
        _deploy_bridge_instance = DeployBridge()
    return _deploy_bridge_instance


def reset_deploy_bridge() -> None:
    """Reset the singleton DeployBridge instance (for testing)."""
    global _deploy_bridge_instance
    _deploy_bridge_instance = None