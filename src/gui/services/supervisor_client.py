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


class SupervisorClientError(Exception):
    """Custom exception for supervisor client errors."""
    def __init__(self, status_code: Optional[int] = None, message: str = ""):
        self.status_code = status_code
        self.message = message
        super().__init__(f"SupervisorClientError: {status_code} - {message}")


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
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            logger.error(f"GET {url} failed with status {status_code}: {e}")
            raise SupervisorClientError(status_code, str(e))
        except requests.RequestException as e:
            logger.error(f"GET {url} failed: {e}")
            raise SupervisorClientError(message=str(e))

    def _post(self, path: str, payload: dict) -> Any:
        """POST request with JSON payload."""
        url = f"{self.base_url}{path}"
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            logger.error(f"POST {url} failed with status {status_code}: {e}")
            raise SupervisorClientError(status_code, str(e))
        except requests.RequestException as e:
            logger.error(f"POST {url} failed: {e}")
            raise SupervisorClientError(message=str(e))

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
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            logger.error(f"GET {url} failed with status {status_code}: {e}")
            raise SupervisorClientError(status_code, str(e))
        except requests.RequestException as e:
            logger.error(f"GET {url} failed: {e}")
            raise SupervisorClientError(message=str(e))

    def get_stdout_tail(self, job_id: str, n: int = 200) -> str:
        """Return stdout tail lines as string."""
        result = self._get(f"/api/v1/jobs/{job_id}/logs/stdout_tail?n={n}")
        # API returns dict with 'lines' key
        if isinstance(result, dict) and 'lines' in result:
            return '\n'.join(result['lines'])
        elif isinstance(result, list):
            return '\n'.join(result)
        else:
            return str(result)

    def get_reveal_evidence_path(self, job_id: str) -> dict:
        """Return approved evidence path."""
        return self._get(f"/api/v1/jobs/{job_id}/reveal_evidence_path")

    def check_readiness(self, season: str, dataset_id: str, timeframe: str) -> dict:
        """Check bars and features readiness."""
        return self._get(f"/api/v1/readiness/{season}/{dataset_id}/{timeframe}")

    def get_job_artifacts(self, job_id: str) -> dict:
        """Return artifact index for a job (alias for get_artifacts)."""
        return self.get_artifacts(job_id)

    def get_strategy_report_v1(self, job_id: str) -> dict:
        """Get StrategyReportV1 for a job."""
        return self._get(f"/api/v1/reports/strategy/{job_id}")

    def get_portfolio_report_v1(self, portfolio_id: str) -> dict:
        """Get PortfolioReportV1 for a portfolio."""
        return self._get(f"/api/v1/reports/portfolio/{portfolio_id}")

    def get_registry_strategies(self) -> List[dict]:
        """Return list of registry strategies with details."""
        # API returns list of strings or dicts; we'll handle both
        result = self._get("/api/v1/registry/strategies")
        if result and isinstance(result[0], dict):
            return result
        else:
            # Convert list of strings to list of dicts with id field
            return [{"id": s, "name": s} for s in result]

    def get_registry_instruments(self) -> List[str]:
        """Return list of instrument symbols (alias for get_instruments)."""
        return self.get_instruments()

    def get_registry_datasets(self) -> List[str]:
        """Return list of dataset IDs (alias for get_datasets)."""
        return self.get_datasets()


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


def get_stdout_tail(job_id: str, n: int = 200) -> str:
    """Return stdout tail lines as string."""
    return _client.get_stdout_tail(job_id, n)


def get_reveal_evidence_path(job_id: str) -> dict:
    """Return approved evidence path."""
    return _client.get_reveal_evidence_path(job_id)


def check_readiness(season: str, dataset_id: str, timeframe: str) -> dict:
    """Check bars and features readiness."""
    return _client.check_readiness(season, dataset_id, timeframe)


def get_job_artifacts(job_id: str) -> dict:
    """Return artifact index for a job (alias for get_artifacts)."""
    return _client.get_job_artifacts(job_id)


def get_strategy_report_v1(job_id: str) -> dict:
    """Get StrategyReportV1 for a job."""
    return _client.get_strategy_report_v1(job_id)


def get_portfolio_report_v1(portfolio_id: str) -> dict:
    """Get PortfolioReportV1 for a portfolio."""
    return _client.get_portfolio_report_v1(portfolio_id)


def get_registry_strategies() -> List[dict]:
    """Return list of registry strategies with details."""
    return _client.get_registry_strategies()


def get_registry_instruments() -> List[str]:
    """Return list of instrument symbols."""
    return _client.get_registry_instruments()


def get_registry_datasets() -> List[str]:
    """Return list of dataset IDs."""
    return _client.get_registry_datasets()


__all__ = [
    "SupervisorClient",
    "SupervisorClientError",
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
    "get_job_artifacts",
    "get_strategy_report_v1",
    "get_portfolio_report_v1",
    "get_registry_strategies",
    "get_registry_instruments",
    "get_registry_datasets",
]