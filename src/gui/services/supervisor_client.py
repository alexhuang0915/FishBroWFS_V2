"""
Supervisor client for GUI services.

Implements HTTP client for the versioned API v1 endpoints.
All endpoints are under /api/v1/... except /health.

Resiliency features:
- Connect timeout: 3 seconds
- Read timeout: 30 seconds
- Retry for 429 (rate limiting) and 5xx (server errors)
- Exponential backoff with jitter
- Error classification (network vs validation vs server)
"""

import json
import logging
import time
import random
from typing import Any, Optional, List, Dict, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gui.desktop.config import SUPERVISOR_BASE_URL

logger = logging.getLogger(__name__)


class SupervisorClientError(Exception):
    """Custom exception for supervisor client errors."""
    def __init__(self, status_code: Optional[int] = None, message: str = "", error_type: str = "unknown"):
        self.status_code = status_code
        self.message = message
        self.error_type = error_type  # "network", "validation", "server", "rate_limit"
        super().__init__(f"SupervisorClientError[{error_type}]: {status_code} - {message}")


class SupervisorClient:
    """HTTP client for supervisor API v1 with resiliency."""

    def __init__(self, base_url: str = SUPERVISOR_BASE_URL):
        self.base_url = base_url.rstrip('/')
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,  # Maximum number of retries
            backoff_factor=1.0,  # Exponential backoff: 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on rate limit and server errors
            allowed_methods=["GET", "POST"],  # Only retry safe methods
            raise_on_status=False  # Don't raise exception on status codes
        )
        
        # Create session with adapter
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Timeout configuration
        self.connect_timeout = 3.0  # Connection timeout in seconds
        self.read_timeout = 30.0    # Read timeout in seconds
        self.session.timeout = (self.connect_timeout, self.read_timeout)

    def _get(self, path: str) -> Any:
        """GET request and parse JSON with error classification."""
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            error_type = self._classify_error(status_code)
            error_message = self._extract_error_message(e)
            logger.error(f"GET {url} failed with status {status_code} ({error_type}): {error_message}")
            raise SupervisorClientError(status_code, error_message, error_type)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.error(f"GET {url} network error: {e}")
            raise SupervisorClientError(message=f"Network error: {e}", error_type="network")
        except requests.RequestException as e:
            logger.error(f"GET {url} failed: {e}")
            raise SupervisorClientError(message=str(e), error_type="unknown")

    def _post(self, path: str, payload: dict) -> Any:
        """POST request with JSON payload with error classification."""
        url = f"{self.base_url}{path}"
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            error_type = self._classify_error(status_code)
            error_message = self._extract_error_message(e)
            logger.error(f"POST {url} failed with status {status_code} ({error_type}): {error_message}")
            raise SupervisorClientError(status_code, error_message, error_type)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.error(f"POST {url} network error: {e}")
            raise SupervisorClientError(message=f"Network error: {e}", error_type="network")
        except requests.RequestException as e:
            logger.error(f"POST {url} failed: {e}")
            raise SupervisorClientError(message=str(e), error_type="unknown")

    def _classify_error(self, status_code: Optional[int]) -> str:
        """Classify HTTP error for better UI messaging."""
        if status_code is None:
            return "network"
        elif status_code == 429:
            return "rate_limit"
        elif 400 <= status_code < 500:
            return "validation"
        elif 500 <= status_code < 600:
            return "server"
        else:
            return "unknown"

    def _extract_error_message(self, http_error: requests.exceptions.HTTPError) -> str:
        """Extract detailed error message from HTTPError response."""
        try:
            response = http_error.response
            if response is None:
                return str(http_error)
            
            # Try to parse JSON error response
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                error_data = response.json()
                # Handle Pydantic validation errors (422)
                if response.status_code == 422 and 'detail' in error_data:
                    details = error_data['detail']
                    if isinstance(details, list) and len(details) > 0:
                        # Extract field errors
                        field_errors = list()
                        for detail in details:
                            loc = detail.get('loc', list())
                            msg = detail.get('msg', '')
                            field = loc[-1] if len(loc) > 1 else str(loc)
                            field_errors.append(f"{field}: {msg}")
                        return f"Validation error: {', '.join(field_errors)}"
                    elif isinstance(details, str):
                        return details
                
                # Handle other JSON error formats
                if 'message' in error_data:
                    return error_data['message']
                elif 'error' in error_data:
                    return error_data['error']
                elif 'detail' in error_data:
                    return str(error_data['detail'])
            
            # Fall back to response text
            return response.text[:500] or str(http_error)
        except Exception:
            return str(http_error)

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

    def get_job_explain(self, job_id: str) -> dict:
        """Return explain payload for a job."""
        return self._get(f"/api/v1/jobs/{job_id}/explain")

    def submit_job(self, payload: dict) -> dict:
        """Submit a job."""
        logger.info("submit_job payload: %s", payload)
        return self._post("/api/v1/jobs", payload)

    def abort_job(self, job_id: str) -> dict:
        """Request abort of a job (QUEUED or RUNNING)."""
        return self._post(f"/api/v1/jobs/{job_id}/abort", {})

    def get_artifacts(self, job_id: str) -> dict:
        """Return artifact index for a job."""
        return self._get(f"/api/v1/jobs/{job_id}/artifacts")

    def get_artifact_file(self, job_id: str, filename: str) -> bytes:
        """Download artifact file content with error classification."""
        url = f"{self.base_url}/api/v1/jobs/{job_id}/artifacts/{filename}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.content
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            error_type = self._classify_error(status_code)
            error_message = self._extract_error_message(e)
            logger.error(f"GET {url} failed with status {status_code} ({error_type}): {error_message}")
            raise SupervisorClientError(status_code, error_message, error_type)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.error(f"GET {url} network error: {e}")
            raise SupervisorClientError(message=f"Network error: {e}", error_type="network")
        except requests.RequestException as e:
            logger.error(f"GET {url} failed: {e}")
            raise SupervisorClientError(message=str(e), error_type="unknown")

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

    def get_registry_timeframes(self) -> List[str]:
        """Return list of available timeframes."""
        return self._get("/api/v1/registry/timeframes")

    def get_raw_files(self) -> List[str]:
        """Return list of raw file names from FishBroData/raw/."""
        return self._get("/api/v1/registry/raw")

    def get_wfs_policies(self) -> list[dict]:
        """Return WFS policy registry entries."""
        result = self._get("/api/v1/wfs/policies")
        if isinstance(result, dict):
            return result.get("entries", [])
        return result

    # Phase D: Portfolio Build API methods
    def post_portfolio_build(self, request_dict: dict) -> dict:
        """Submit a portfolio build request."""
        return self._post("/api/v1/portfolios/build", request_dict)

    def get_portfolio_artifacts(self, portfolio_id: str) -> dict:
        """Return portfolio artifacts index."""
        return self._get(f"/api/v1/portfolios/{portfolio_id}/artifacts")

    def reveal_portfolio_admission_path(self, portfolio_id: str) -> dict:
        """Return approved admission path for portfolio."""
        return self._get(f"/api/v1/portfolios/{portfolio_id}/reveal_admission_path")

    def get_portfolio(self, portfolio_id: str) -> dict:
        """Get portfolio metadata."""
        return self._get(f"/api/v1/portfolios/{portfolio_id}")

    def get_outputs_summary(self) -> dict:
        """Get outputs summary for clean UI navigation."""
        return self._get("/api/v1/outputs/summary")

    # P2-A: Season SSOT + Boundary Validator methods
    def create_season_ssot(self, payload: dict) -> dict:
        """Create a new Season SSOT entity."""
        return self._post("/api/v1/seasons/ssot/create", payload)

    def list_seasons_ssot(self) -> dict:
        """List all Season SSOT entities."""
        return self._get("/api/v1/seasons/ssot")

    def get_season_ssot(self, season_id: str) -> dict:
        """Get detailed information about a Season SSOT entity."""
        return self._get(f"/api/v1/seasons/ssot/{season_id}")

    def attach_job_to_season_ssot(self, season_id: str, job_id: str) -> dict:
        """Attach a job to a Season SSOT with hard boundary validation."""
        payload = {"job_id": job_id}
        return self._post(f"/api/v1/seasons/ssot/{season_id}/attach", payload)

    def freeze_season_ssot(self, season_id: str) -> dict:
        """Freeze a Season SSOT (transition from OPEN to FROZEN)."""
        return self._post(f"/api/v1/seasons/ssot/{season_id}/freeze", {})

    def archive_season_ssot(self, season_id: str) -> dict:
        """Archive a Season SSOT (transition from FROZEN/DECIDING to ARCHIVED)."""
        return self._post(f"/api/v1/seasons/ssot/{season_id}/archive", {})

    # P2-B/C/D: Season Analysis, Admission, Export methods
    def analyze_season_ssot(self, season_id: str) -> dict:
        """Analyze a Season SSOT (P2-B: Season Viewer/Analysis Aggregator)."""
        return self._post(f"/api/v1/seasons/ssot/{season_id}/analyze", {})

    def admit_candidates_to_season_ssot(self, season_id: str, decisions: List[dict]) -> dict:
        """Admit candidates to a Season SSOT (P2-C: Admission Decisions)."""
        payload = {"decisions": decisions}
        return self._post(f"/api/v1/seasons/ssot/{season_id}/admit", payload)

    def export_candidates_from_season_ssot(self, season_id: str) -> dict:
        """Export candidate set from a Season SSOT (P2-D: Export Portfolio Candidate Set)."""
        return self._post(f"/api/v1/seasons/ssot/{season_id}/export_candidates", {})


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


def get_job_explain(job_id: str) -> dict:
    """Return explain payload for a job."""
    return _client.get_job_explain(job_id)


def submit_job(payload: dict) -> dict:
    """Submit a job."""
    logger.info("submit_job payload (public): %s", payload)
    return _client.submit_job(payload)


def abort_job(job_id: str) -> dict:
    """Request abort of a job (QUEUED or RUNNING)."""
    return _client.abort_job(job_id)


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

def get_registry_timeframes() -> List[str]:
    """Return list of available timeframes."""
    return _client.get_registry_timeframes()


def get_raw_files() -> List[str]:
    """Return list of raw file names from FishBroData/raw/."""
    return _client.get_raw_files()


def get_wfs_policies() -> list[dict]:
    """Return WFS policy registry entries."""
    return _client.get_wfs_policies()


# Phase D: Portfolio Build API public functions
def post_portfolio_build(request_dict: dict) -> dict:
    """Submit a portfolio build request."""
    return _client.post_portfolio_build(request_dict)

def get_portfolio_artifacts(portfolio_id: str) -> dict:
    """Return portfolio artifacts index."""
    return _client.get_portfolio_artifacts(portfolio_id)

def reveal_portfolio_admission_path(portfolio_id: str) -> dict:
    """Return approved admission path for portfolio."""
    return _client.reveal_portfolio_admission_path(portfolio_id)

def get_portfolio(portfolio_id: str) -> dict:
    """Get portfolio metadata."""
    return _client.get_portfolio(portfolio_id)

def get_outputs_summary() -> dict:
    """Get outputs summary for clean UI navigation."""
    return _client.get_outputs_summary()

# P2-A: Season SSOT + Boundary Validator public functions
def create_season_ssot(payload: dict) -> dict:
    """Create a new Season SSOT entity."""
    return _client.create_season_ssot(payload)

def list_seasons_ssot() -> dict:
    """List all Season SSOT entities."""
    return _client.list_seasons_ssot()

def get_season_ssot(season_id: str) -> dict:
    """Get detailed information about a Season SSOT entity."""
    return _client.get_season_ssot(season_id)

def attach_job_to_season_ssot(season_id: str, job_id: str) -> dict:
    """Attach a job to a Season SSOT with hard boundary validation."""
    return _client.attach_job_to_season_ssot(season_id, job_id)

def freeze_season_ssot(season_id: str) -> dict:
    """Freeze a Season SSOT (transition from OPEN to FROZEN)."""
    return _client.freeze_season_ssot(season_id)

def archive_season_ssot(season_id: str) -> dict:
    """Archive a Season SSOT (transition from FROZEN/DECIDING to ARCHIVED)."""
    return _client.archive_season_ssot(season_id)

# P2-B/C/D: Season Analysis, Admission, Export public functions
def analyze_season_ssot(season_id: str) -> dict:
    """Analyze a Season SSOT (P2-B: Season Viewer/Analysis Aggregator)."""
    return _client.analyze_season_ssot(season_id)

def admit_candidates_to_season_ssot(season_id: str, decisions: List[dict]) -> dict:
    """Admit candidates to a Season SSOT (P2-C: Admission Decisions)."""
    return _client.admit_candidates_to_season_ssot(season_id, decisions)

def export_candidates_from_season_ssot(season_id: str) -> dict:
    """Export candidate set from a Season SSOT (P2-D: Export Portfolio Candidate Set)."""
    return _client.export_candidates_from_season_ssot(season_id)


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
    "abort_job",
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
    "get_registry_timeframes",
    "get_raw_files",
    "get_wfs_policies",
    # Phase D additions
    "post_portfolio_build",
    "get_portfolio_artifacts",
    "reveal_portfolio_admission_path",
    "get_portfolio",
    # Phase E.4 additions
    "get_outputs_summary",
    # P2-A: Season SSOT additions
    "create_season_ssot",
    "list_seasons_ssot",
    "get_season_ssot",
    "attach_job_to_season_ssot",
    "freeze_season_ssot",
    "archive_season_ssot",
    # P2-B/C/D additions
    "analyze_season_ssot",
    "admit_candidates_to_season_ssot",
    "export_candidates_from_season_ssot",
]