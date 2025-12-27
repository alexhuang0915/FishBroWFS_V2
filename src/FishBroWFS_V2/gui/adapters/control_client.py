"""Control API HTTP Client for UI.

Zero-Violation Split-Brain Architecture (UI HTTP Client + Control API Authority).

UI must communicate with Control API only via HTTP, zero direct references to DB/spawn symbols.
This client encapsulates all API calls the UI needs.

Contract:
- All methods are async (use httpx.AsyncClient)
- All methods raise ControlAPIError on HTTP errors
- All methods return parsed JSON (dict/list) or Pydantic models
- No business logic, only HTTP transport
- No references to sqlite3, outputs/jobs.db, FishBroWFS_V2.control.*, worker_main, subprocess.Popen
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager
from datetime import date
import httpx
from pydantic import BaseModel, ValidationError

from FishBroWFS_V2.core.service_identity import ServiceIdentity


class ControlAPIError(Exception):
    """Raised when Control API returns an error."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Control API error {status_code}: {detail}")


class ControlAPIClient:
    """HTTP client for Control API."""
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
    
    @asynccontextmanager
    async def _ensure_client(self):
        """Ensure httpx client is created and closed properly."""
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    follow_redirects=True,
                )
            try:
                yield self._client
            except httpx.HTTPStatusError as e:
                # Convert to our error type
                try:
                    detail = e.response.json().get("detail", str(e))
                except Exception:
                    detail = str(e)
                raise ControlAPIError(e.response.status_code, detail)
            except httpx.RequestError as e:
                raise ControlAPIError(0, f"Request failed: {str(e)}")
    
    async def close(self):
        """Close the HTTP client."""
        async with self._lock:
            if self._client:
                await self._client.aclose()
                self._client = None
    
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Union[Dict[str, Any], List[Any]]:
        """Make HTTP request and parse JSON response."""
        async with self._ensure_client() as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            if response.status_code == 204:  # No content
                return {}
            return response.json()
    
    # -----------------------------------------------------------------
    # Health & Identity
    # -----------------------------------------------------------------
    
    async def health(self) -> Dict[str, str]:
        """GET /health"""
        return await self._request("GET", "/health")
    
    async def identity(self) -> ServiceIdentity:
        """GET /__identity"""
        data = await self._request("GET", "/__identity")
        return ServiceIdentity(**data)
    
    # -----------------------------------------------------------------
    # Worker Operations
    # -----------------------------------------------------------------
    
    async def worker_status(self) -> Dict[str, Any]:
        """GET /worker/status - Get worker daemon status."""
        return await self._request("GET", "/worker/status")
    
    async def worker_stop(self, force: bool = True, reason: str = "") -> Dict[str, Any]:
        """POST /worker/stop - Stop worker daemon."""
        payload = {"force": force}
        if reason:
            payload["reason"] = reason
        return await self._request("POST", "/worker/stop", json=payload)
    
    # -----------------------------------------------------------------
    # Generic HTTP Methods (for backward compatibility)
    # -----------------------------------------------------------------
    
    async def get_json(self, path: str, **kwargs) -> Union[Dict[str, Any], List[Any]]:
        """Generic GET request with JSON response."""
        return await self._request("GET", path, **kwargs)
    
    async def post_json(self, path: str, **kwargs) -> Union[Dict[str, Any], List[Any]]:
        """Generic POST request with JSON response."""
        return await self._request("POST", path, **kwargs)
    
    # -----------------------------------------------------------------
    # Meta (Datasets & Strategies)
    # -----------------------------------------------------------------
    
    async def meta_datasets(self) -> Dict[str, Any]:
        """GET /meta/datasets"""
        return await self._request("GET", "/meta/datasets")
    
    async def meta_strategies(self) -> Dict[str, Any]:
        """GET /meta/strategies"""
        return await self._request("GET", "/meta/strategies")
    
    async def prime_registries(self) -> Dict[str, Any]:
        """POST /meta/prime"""
        return await self._request("POST", "/meta/prime")
    
    # -----------------------------------------------------------------
    # Jobs
    # -----------------------------------------------------------------
    
    async def list_jobs(self) -> List[Dict[str, Any]]:
        """GET /jobs"""
        return await self._request("GET", "/jobs")
    
    async def get_job(self, job_id: str) -> Dict[str, Any]:
        """GET /jobs/{job_id}"""
        return await self._request("GET", f"/jobs/{job_id}")
    
    async def submit_job(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """POST /jobs"""
        return await self._request("POST", "/jobs", json=spec)
    
    async def stop_job(self, job_id: str, mode: str = "SOFT") -> Dict[str, Any]:
        """POST /jobs/{job_id}/stop"""
        return await self._request("POST", f"/jobs/{job_id}/stop", params={"mode": mode})
    
    async def pause_job(self, job_id: str, pause: bool = True) -> Dict[str, Any]:
        """POST /jobs/{job_id}/pause"""
        return await self._request("POST", f"/jobs/{job_id}/pause", json={"pause": pause})
    
    async def preflight_job(self, job_id: str) -> Dict[str, Any]:
        """GET /jobs/{job_id}/preflight"""
        return await self._request("GET", f"/jobs/{job_id}/preflight")
    
    async def check_job(self, job_id: str) -> Dict[str, Any]:
        """POST /jobs/{job_id}/check"""
        return await self._request("POST", f"/jobs/{job_id}/check")
    
    async def run_log_tail(self, job_id: str, n: int = 200) -> Dict[str, Any]:
        """GET /jobs/{job_id}/run_log_tail"""
        return await self._request("GET", f"/jobs/{job_id}/run_log_tail", params={"n": n})
    
    async def log_tail(self, job_id: str, n: int = 200) -> Dict[str, Any]:
        """GET /jobs/{job_id}/log_tail"""
        return await self._request("GET", f"/jobs/{job_id}/log_tail", params={"n": n})
    
    async def get_report_link(self, job_id: str) -> Dict[str, Any]:
        """GET /jobs/{job_id}/report_link"""
        return await self._request("GET", f"/jobs/{job_id}/report_link")
    
    # -----------------------------------------------------------------
    # Batch Operations
    # -----------------------------------------------------------------
    
    async def batch_submit(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POST /jobs/batch"""
        return await self._request("POST", "/jobs/batch", json={"jobs": jobs})
    
    async def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """GET /batches/{batch_id}/status"""
        return await self._request("GET", f"/batches/{batch_id}/status")
    
    async def get_batch_summary(self, batch_id: str) -> Dict[str, Any]:
        """GET /batches/{batch_id}/summary"""
        return await self._request("GET", f"/batches/{batch_id}/summary")
    
    async def retry_batch(self, batch_id: str) -> Dict[str, Any]:
        """POST /batches/{batch_id}/retry"""
        return await self._request("POST", f"/batches/{batch_id}/retry", json={})
    
    async def get_batch_index(self, batch_id: str) -> Dict[str, Any]:
        """GET /batches/{batch_id}/index"""
        return await self._request("GET", f"/batches/{batch_id}/index")
    
    async def get_batch_artifacts(self, batch_id: str) -> Dict[str, Any]:
        """GET /batches/{batch_id}/artifacts"""
        return await self._request("GET", f"/batches/{batch_id}/artifacts")
    
    async def get_batch_metadata(self, batch_id: str) -> Dict[str, Any]:
        """GET /batches/{batch_id}/metadata"""
        return await self._request("GET", f"/batches/{batch_id}/metadata")
    
    async def update_batch_metadata(
        self,
        batch_id: str,
        season: Optional[str] = None,
        tags: Optional[List[str]] = None,
        note: Optional[str] = None,
        frozen: Optional[bool] = None
    ) -> Dict[str, Any]:
        """PATCH /batches/{batch_id}/metadata"""
        payload = {}
        if season is not None:
            payload["season"] = season
        if tags is not None:
            payload["tags"] = tags
        if note is not None:
            payload["note"] = note
        if frozen is not None:
            payload["frozen"] = frozen
        return await self._request("PATCH", f"/batches/{batch_id}/metadata", json=payload)
    
    async def freeze_batch(self, batch_id: str) -> Dict[str, Any]:
        """POST /batches/{batch_id}/freeze"""
        return await self._request("POST", f"/batches/{batch_id}/freeze")
    
    # -----------------------------------------------------------------
    # Season Operations
    # -----------------------------------------------------------------
    
    async def get_season_index(self, season: str) -> Dict[str, Any]:
        """GET /seasons/{season}/index"""
        return await self._request("GET", f"/seasons/{season}/index")
    
    async def rebuild_season_index(self, season: str) -> Dict[str, Any]:
        """POST /seasons/{season}/rebuild_index"""
        return await self._request("POST", f"/seasons/{season}/rebuild_index")
    
    async def get_season_metadata(self, season: str) -> Dict[str, Any]:
        """GET /seasons/{season}/metadata"""
        return await self._request("GET", f"/seasons/{season}/metadata")
    
    async def update_season_metadata(
        self,
        season: str,
        tags: Optional[List[str]] = None,
        note: Optional[str] = None,
        frozen: Optional[bool] = None
    ) -> Dict[str, Any]:
        """PATCH /seasons/{season}/metadata"""
        payload = {}
        if tags is not None:
            payload["tags"] = tags
        if note is not None:
            payload["note"] = note
        if frozen is not None:
            payload["frozen"] = frozen
        return await self._request("PATCH", f"/seasons/{season}/metadata", json=payload)
    
    async def freeze_season(self, season: str) -> Dict[str, Any]:
        """POST /seasons/{season}/freeze"""
        return await self._request("POST", f"/seasons/{season}/freeze")
    
    async def season_compare_topk(self, season: str, k: int = 20) -> Dict[str, Any]:
        """GET /seasons/{season}/compare/topk"""
        return await self._request("GET", f"/seasons/{season}/compare/topk", params={"k": k})
    
    async def season_compare_batches(self, season: str) -> Dict[str, Any]:
        """GET /seasons/{season}/compare/batches"""
        return await self._request("GET", f"/seasons/{season}/compare/batches")
    
    async def season_compare_leaderboard(
        self,
        season: str,
        group_by: str = "strategy_id",
        per_group: int = 3
    ) -> Dict[str, Any]:
        """GET /seasons/{season}/compare/leaderboard"""
        return await self._request(
            "GET",
            f"/seasons/{season}/compare/leaderboard",
            params={"group_by": group_by, "per_group": per_group}
        )
    
    async def export_season(self, season: str) -> Dict[str, Any]:
        """POST /seasons/{season}/export"""
        return await self._request("POST", f"/seasons/{season}/export")
    
    # -----------------------------------------------------------------
    # Export Replay Operations
    # -----------------------------------------------------------------
    
    async def export_season_compare_topk(self, season: str, k: int = 20) -> Dict[str, Any]:
        """GET /exports/seasons/{season}/compare/topk"""
        return await self._request("GET", f"/exports/seasons/{season}/compare/topk", params={"k": k})
    
    async def export_season_compare_batches(self, season: str) -> Dict[str, Any]:
        """GET /exports/seasons/{season}/compare/batches"""
        return await self._request("GET", f"/exports/seasons/{season}/compare/batches")
    
    async def export_season_compare_leaderboard(
        self,
        season: str,
        group_by: str = "strategy_id",
        per_group: int = 3
    ) -> Dict[str, Any]:
        """GET /exports/seasons/{season}/compare/leaderboard"""
        return await self._request(
            "GET",
            f"/exports/seasons/{season}/compare/leaderboard",
            params={"group_by": group_by, "per_group": per_group}
        )
    
    # -----------------------------------------------------------------
    # Dataset Snapshots
    # -----------------------------------------------------------------
    
    async def create_snapshot(
        self,
        raw_bars: List[Dict[str, Any]],
        symbol: str,
        timeframe: str,
        transform_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """POST /datasets/snapshots"""
        payload = {
            "raw_bars": raw_bars,
            "symbol": symbol,
            "timeframe": timeframe,
        }
        if transform_version is not None:
            payload["transform_version"] = transform_version
        return await self._request("POST", "/datasets/snapshots", json=payload)
    
    async def list_snapshots(self) -> Dict[str, Any]:
        """GET /datasets/snapshots"""
        return await self._request("GET", "/datasets/snapshots")
    
    async def register_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """POST /datasets/registry/register_snapshot"""
        return await self._request("POST", "/datasets/registry/register_snapshot", json={"snapshot_id": snapshot_id})
    
    # -----------------------------------------------------------------
    # Portfolio Plans
    # -----------------------------------------------------------------
    
    async def create_portfolio_plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /portfolio/plans"""
        return await self._request("POST", "/portfolio/plans", json=payload)
    
    async def list_portfolio_plans(self) -> Dict[str, Any]:
        """GET /portfolio/plans"""
        return await self._request("GET", "/portfolio/plans")
    
    async def get_portfolio_plan(self, plan_id: str) -> Dict[str, Any]:
        """GET /portfolio/plans/{plan_id}"""
        return await self._request("GET", f"/portfolio/plans/{plan_id}")
    
    async def get_plan_quality(self, plan_id: str) -> Dict[str, Any]:
        """GET /portfolio/plans/{plan_id}/quality"""
        return await self._request("GET", f"/portfolio/plans/{plan_id}/quality")
    
    async def write_plan_quality(self, plan_id: str) -> Dict[str, Any]:
        """POST /portfolio/plans/{plan_id}/quality"""
        return await self._request("POST", f"/portfolio/plans/{plan_id}/quality")
    
    # -----------------------------------------------------------------
    # Convenience Methods (UI-friendly)
    # -----------------------------------------------------------------
    
    async def get_job_summary(self, job_id: str) -> Dict[str, Any]:
        """Get job status and logs combined (UI convenience)."""
        status = await self.get_job(job_id)
        logs = await self.log_tail(job_id, n=20)
        return {
            **status,
            "logs": logs.get("lines", []),
            "log_tail": "\n".join(logs.get("lines", [])[-10:]) if logs.get("lines") else "No logs available"
        }
    
    async def list_jobs_with_progress(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List jobs with progress information (UI convenience)."""
        jobs = await self.list_jobs()
        # Sort by created_at descending (most recent first)
        sorted_jobs = sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)
        return sorted_jobs[:limit]
    
    async def check_season_not_frozen(self, season: str, action: str = "submit_job") -> bool:
        """Check if season is frozen (UI convenience)."""
        try:
            # Use season metadata endpoint
            meta = await self.get_season_metadata(season)
            if meta.get("frozen", False):
                return False
            return True
        except ControlAPIError as e:
            if e.status_code == 404:
                # Season not found, assume not frozen
                return True
            raise


# Singleton instance
_control_client_instance: Optional[ControlAPIClient] = None


def get_control_client() -> ControlAPIClient:
    """Get singleton ControlAPIClient instance."""
    global _control_client_instance
    if _control_client_instance is None:
        _control_client_instance = ControlAPIClient()
    return _control_client_instance


async def close_control_client() -> None:
    """Close the singleton client."""
    global _control_client_instance
    if _control_client_instance is not None:
        await _control_client_instance.close()
        _control_client_instance = None