"""
ArtifactsBridge - Single audited gateway for UI pages to access artifacts.

UI pages must ONLY call methods on this class; no direct ControlAPIClient calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArtifactInfo:
    """Artifact information data structure."""
    artifact_id: str
    job_id: str
    artifact_type: str
    created_at: str
    size_bytes: Optional[int] = None
    description: Optional[str] = None
    path: Optional[str] = None


class ArtifactsBridge:
    """
    Single audited gateway for UI pages to access artifacts.
    
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
    
    def list_artifacts(self, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List artifacts, optionally filtered by job ID.
        
        Args:
            job_id: Optional job identifier to filter artifacts.
            
        Returns:
            List of artifact dictionaries.
        """
        try:
            client = self._get_client()
            
            if job_id:
                # Try job-specific artifact endpoints
                endpoint_candidates = [
                    f"/jobs/{job_id}/artifacts",
                    f"/batches/{job_id}/artifacts",
                    f"/artifacts?job_id={job_id}"
                ]
            else:
                # Try general artifact endpoints
                endpoint_candidates = [
                    "/artifacts",
                    "/artifacts/list",
                    "/jobs/artifacts"
                ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=3.0))
                    # Normalize to list
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        for key in ("artifacts", "items", "data", "files"):
                            if key in data and isinstance(data[key], list):
                                return data[key]
                except Exception:
                    continue
            
            # Fallback: try the explicit method if available
            if job_id:
                try:
                    return self._run_async(client.get_batch_artifacts(job_id))
                except Exception:
                    pass
                    
            return []
        except Exception as e:
            logger.exception(f"ArtifactsBridge.list_artifacts failed for job_id={job_id}")
            return []
    
    def get_artifact(self, artifact_id: str) -> Dict[str, Any]:
        """
        Get artifact by ID.
        
        Args:
            artifact_id: Artifact identifier.
            
        Returns:
            Dictionary with artifact details.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                f"/artifacts/{artifact_id}",
                f"/files/{artifact_id}",
                f"/data/{artifact_id}"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=3.0))
                    if data:
                        return data
                except Exception:
                    continue
                
            return {}
        except Exception as e:
            logger.exception(f"ArtifactsBridge.get_artifact failed for artifact_id={artifact_id}")
            return {"error": str(e)}
    
    def get_artifact_data(self, artifact_id: str) -> Dict[str, Any]:
        """
        Get artifact data (content) by ID.
        
        Args:
            artifact_id: Artifact identifier.
            
        Returns:
            Dictionary with artifact data.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates for data
            endpoint_candidates = [
                f"/artifacts/{artifact_id}/data",
                f"/artifacts/{artifact_id}/content",
                f"/files/{artifact_id}/data"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=5.0))
                    if data:
                        return data
                except Exception:
                    continue
            
            # Fallback: try the regular artifact endpoint
            return self.get_artifact(artifact_id)
        except Exception as e:
            logger.exception(f"ArtifactsBridge.get_artifact_data failed for artifact_id={artifact_id}")
            return {"error": str(e)}
    
    def get_artifact_info(self, artifact_id: str) -> ArtifactInfo:
        """
        Get artifact information as typed object.
        
        Args:
            artifact_id: Artifact identifier.
            
        Returns:
            ArtifactInfo object.
        """
        artifact = self.get_artifact(artifact_id)
        
        return ArtifactInfo(
            artifact_id=artifact_id,
            job_id=artifact.get("job_id", ""),
            artifact_type=artifact.get("type", "unknown"),
            created_at=artifact.get("created_at", ""),
            size_bytes=artifact.get("size_bytes"),
            description=artifact.get("description"),
            path=artifact.get("path")
        )
    
    def get_job_artifacts_summary(self, job_id: str) -> Dict[str, Any]:
        """
        Get summary of artifacts for a job.
        
        Args:
            job_id: Job identifier.
            
        Returns:
            Dictionary with artifact summary.
        """
        artifacts = self.list_artifacts(job_id)
        
        # Calculate summary
        total = len(artifacts)
        type_counts = {}
        total_size = 0
        
        for artifact in artifacts:
            artifact_type = artifact.get("type", "unknown")
            type_counts[artifact_type] = type_counts.get(artifact_type, 0) + 1
            size = artifact.get("size_bytes", 0)
            if isinstance(size, (int, float)):
                total_size += size
        
        return {
            "total": total,
            "type_counts": type_counts,
            "total_size_bytes": total_size,
            "artifacts": artifacts[:10]  # First 10 artifacts
        }
    
    def list_research_units(self, season: str, job_id: str) -> List[Dict[str, Any]]:
        """
        List research units for a job.
        
        Args:
            season: Season identifier.
            job_id: Job identifier.
            
        Returns:
            List of research unit dictionaries.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                f"/research/{season}/{job_id}/units",
                f"/jobs/{job_id}/research/units",
                f"/seasons/{season}/jobs/{job_id}/units",
                f"/artifacts/{job_id}/units"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=5.0))
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        for key in ("units", "items", "data"):
                            if key in data and isinstance(data[key], list):
                                return data[key]
                except Exception:
                    continue
            
            # Fallback: return empty list
            return []
        except Exception as e:
            logger.exception(f"ArtifactsBridge.list_research_units failed for season={season}, job_id={job_id}")
            return []
    
    def get_research_artifacts(self, season: str, job_id: str, unit_key: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get research artifacts for a unit.
        
        Args:
            season: Season identifier.
            job_id: Job identifier.
            unit_key: Unit key dictionary.
            
        Returns:
            Dictionary with artifact paths.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                f"/research/{season}/{job_id}/artifacts",
                f"/jobs/{job_id}/research/artifacts",
                f"/artifacts/{job_id}/unit"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.post_json(path, json={
                        "season": season,
                        "job_id": job_id,
                        "unit_key": unit_key
                    }, timeout=5.0))
                    if data:
                        return data
                except Exception:
                    continue
            
            # Fallback: return empty dict
            return {}
        except Exception as e:
            logger.exception(f"ArtifactsBridge.get_research_artifacts failed for season={season}, job_id={job_id}")
            return {}
    
    def get_portfolio_index(self, season: str, job_id: str) -> Dict[str, Any]:
        """
        Get portfolio index for a job.
        
        Args:
            season: Season identifier.
            job_id: Job identifier.
            
        Returns:
            Dictionary with portfolio index.
        """
        try:
            client = self._get_client()
            # Try different endpoint candidates
            endpoint_candidates = [
                f"/portfolio/{season}/{job_id}/index",
                f"/jobs/{job_id}/portfolio",
                f"/seasons/{season}/jobs/{job_id}/portfolio"
            ]
            
            for path in endpoint_candidates:
                try:
                    data = self._run_async(client.get_json(path, timeout=5.0))
                    if data:
                        return data
                except Exception:
                    continue
            
            # Fallback: return empty dict
            return {}
        except Exception as e:
            logger.exception(f"ArtifactsBridge.get_portfolio_index failed for season={season}, job_id={job_id}")
            return {}


# Singleton instance
_artifacts_bridge_instance: Optional[ArtifactsBridge] = None


def get_artifacts_bridge() -> ArtifactsBridge:
    """
    Get singleton ArtifactsBridge instance.
    
    This is the main entry point for UI pages.
    
    Returns:
        ArtifactsBridge instance.
    """
    global _artifacts_bridge_instance
    if _artifacts_bridge_instance is None:
        _artifacts_bridge_instance = ArtifactsBridge()
    return _artifacts_bridge_instance


def reset_artifacts_bridge() -> None:
    """Reset the singleton ArtifactsBridge instance (for testing)."""
    global _artifacts_bridge_instance
    _artifacts_bridge_instance = None