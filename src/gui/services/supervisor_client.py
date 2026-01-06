"""
Supervisor client for GUI services.

Implements HTTP client for the versioned API v1 endpoints.
All endpoints are under /api/v1/... except /health.
"""

import json
import logging
from typing import Any, Optional, List, Dict

import requests

from src.gui.desktop.config import SUPERVISOR_BASE_URL

logger = logging.getLogger(__name__)


class SupervisorClient:
    """HTTP client for supervisor API v1."""

    def __init__(self, base_url: str = SUPERVISOR_BASE_URL):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 5.0

    def _get(self, path: str) -> Any:
        """GET request and parse JSON."""
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"GET {url} failed: {e}")
            raise

    def _post(self, path: str, payload: dict) -> Any:
        """POST request with JSON payload."""
        url = f"{self.base_url}{path}"
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"POST {url} failed: {e}")
            raise

    def health(self) -> dict:
        """Check supervisor health."""
        return self._get("/health")

    def get_datasets(self) -> List[str]:
        """Return list of dataset IDs."""
        return self._get("/api/v1/registry/datasets")

    def get_strategies(self) -> List[str]:
        """Return list of strategy IDs."""
        return self._get("/api/v1/registry/strategies")

    def get_instruments(self) -> List[str]:
        """Return list of instrument symbols."""
        return self._get("/api/v1/registry/instruments")

    def get_jobs(self, limit: int = 50) -> List[dict]:
        """Return list of jobs."""
        return self._get(f"/api/v1/jobs?limit={limit}")

    def get_job(self, job_id: str) -> dict:
        """Return job details."""
        return self._get(f"/api/v1/jobs/{job_id}")

    def submit_job(self, payload: dict) -> dict:
        """Submit a job."""
        return self._post("/api/v1/jobs", payload)

    def get_artifacts(self, job_id: str) -> dict:
        """Return artifact index for a job."""
        return self._get(f"/api/v1/jobs/{job_id}/artifacts")

    def get_artifact_file(self, job_id: str, filename: str) -> bytes:
        """Download artifact file content."""
        url = f"{self.base_url}/api/v1/jobs/{job_id}/artifacts/{filename}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            logger.error(f"GET {url} failed: {e}")
            raise

    def get_stdout_tail(self, job_id: str, n: int = 200) -> dict:
        """Return stdout tail lines."""
        return self._get(f"/api/v1/jobs/{job_id}/logs/stdout_tail?n={n}")

    def get_reveal_evidence_path(self, job_id: str) -> dict:
        """Return approved evidence path."""
        return self._get(f"/api/v1/jobs/{job_id}/reveal_evidence_path")

    def check_readiness(self, season: str, dataset_id: str, timeframe: str) -> dict:
        """Check bars and features readiness."""
        return self._get(f"/api/v1/readiness/{season}/{dataset_id}/{timeframe}")


# Singleton client instance
_client = SupervisorClient()


# Public API functions (backward compatibility)
def get_client() -> SupervisorClient:
    """Return the singleton supervisor client."""
    return _client


def health() -> dict:
    """Check supervisor health."""
    return _client.health()


def get_datasets() -> List[str]:
    """Return list of dataset IDs."""
    return _client.get_datasets()


def get_strategies() -> List[str]:
    """Return list of strategy IDs."""
    return _client.get_strategies()


def get_instruments() -> List[str]:
    """Return list of instrument symbols."""
    return _client.get_instruments()


def get_jobs(limit: int = 50) -> List[dict]:
    """Return list of jobs."""
    return _client.get_jobs(limit)


def get_job(job_id: str) -> dict:
    """Return job details."""
    return _client.get_job(job_id)


def submit_job(payload: dict) -> dict:
    """Submit a job."""
    return _client.submit_job(payload)


def get_artifacts(job_id: str) -> dict:
    """Return artifact index for a job."""
    return _client.get_artifacts(job_id)


def get_artifact_file(job_id: str, filename: str) -> bytes:
    """Download artifact file content."""
    return _client.get_artifact_file(job_id, filename)


def get_stdout_tail(job_id: str, n: int = 200) -> dict:
    """Return stdout tail lines."""
    return _client.get_stdout_tail(job_id, n)


def get_reveal_evidence_path(job_id: str) -> dict:
    """Return approved evidence path."""
    return _client.get_reveal_evidence_path(job_id)


def check_readiness(season: str, dataset_id: str, timeframe: str) -> dict:
    """Check bars and features readiness."""
    return _client.check_readiness(season, dataset_id, timeframe)


__all__ = [
    "SupervisorClient",
    "get_client",
    "health",
    "get_datasets",
    "get_strategies",
    "get_instruments",
    "get_jobs",
    "get_job",
    "submit_job",
    "get_artifacts",
    "get_artifact_file",
    "get_stdout_tail",
    "get_reveal_evidence_path",
    "check_readiness",
]