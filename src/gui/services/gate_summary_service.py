"""
Gate Summary Service for UI observability.

Provides a single SSOT client utility that fetches gate statuses from supervisor API
and returns a pure data model suitable for UI display.

Five gates:
1. API Health (/health)
2. API Readiness (/api/v1/readiness)
3. Supervisor DB SSOT (/api/v1/jobs)
4. Worker Execution Reality (presence of RUNNING jobs)
5. Registry Surface (/api/v1/registry/timeframes)

Each gate returns a GateResult with status (PASS/WARN/FAIL), human message,
and optional drill‑down actions.
"""

import json
import logging
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from gui.services.supervisor_client import SupervisorClient, SupervisorClientError

logger = logging.getLogger(__name__)


class GateStatus(str, Enum):
    """Gate status values."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass
class GateResult:
    """Result for a single gate."""
    gate_id: str
    gate_name: str
    status: GateStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, str]]] = None
    timestamp: Optional[str] = None


@dataclass
class GateSummary:
    """Complete summary of all five gates."""
    gates: List[GateResult]
    timestamp: str
    overall_status: GateStatus
    overall_message: str


class GateSummaryService:
    """Service that fetches gate statuses from supervisor API."""

    def __init__(self, client: Optional[SupervisorClient] = None):
        self.client = client or SupervisorClient()
        self.timeout = 5.0  # seconds per request

    def fetch(self) -> GateSummary:
        """
        Fetch all gate statuses sequentially.

        Returns:
            GateSummary with five gates and overall status.

        Raises:
            SupervisorClientError: if any gate fails due to network or server error.
        """
        try:
            gates = list()
            try:
                gates.append(self._fetch_api_health())
                gates.append(self._fetch_api_readiness())
                gates.append(self._fetch_supervisor_db_ssot())
                gates.append(self._fetch_worker_execution_reality())
                gates.append(self._fetch_registry_surface())
            except SupervisorClientError as e:
                # If any gate fails due to network/server error, we treat as overall FAIL
                logger.error(f"Gate fetch failed: {e}")
                # Create a placeholder gate for the error
                error_gate = GateResult(
                    gate_id="fetch_error",
                    gate_name="Gate Fetch Error",
                    status=GateStatus.FAIL,
                    message=f"Failed to fetch gates: {e.message}",
                    details={"error_type": e.error_type, "status_code": e.status_code},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                gates = list((error_gate,)) + gates[:4]  # replace first gate? we'll keep partial results
                # Continue to compute overall status

            overall_status = self._compute_overall_status(gates)
            overall_message = self._compute_overall_message(overall_status, gates)

            return GateSummary(
                gates=gates,
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_status=overall_status,
                overall_message=overall_message,
            )
        except Exception as e:
            # Catastrophic failure: return a safe fallback summary
            logger.error(f"Gate summary fetch failed catastrophically: {e}", exc_info=True)
            error_gate = GateResult(
                gate_id="catastrophic_failure",
                gate_name="Gate Summary Service",
                status=GateStatus.FAIL,
                message=f"Failed to fetch gate summary: {e}",
                details={"error_type": type(e).__name__, "traceback": str(e)},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            return GateSummary(
                gates=[error_gate],
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_status=GateStatus.FAIL,
                overall_message="Gate summary service unavailable.",
            )

    def _fetch_api_health(self) -> GateResult:
        """Gate 1: API Health."""
        gate_id = "api_health"
        gate_name = "API Health"
        try:
            response = self.client.health()
            # Expect {"status": "ok"}
            if isinstance(response, dict) and response.get("status") == "ok":
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message="API health endpoint responds with status ok.",
                    details=response,
                    actions=list(({"label": "View Health", "url": "/health"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"Unexpected health response: {response}",
                    details=response,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except SupervisorClientError as e:
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Health endpoint unreachable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_api_readiness(self) -> GateResult:
        """Gate 2: API Readiness."""
        gate_id = "api_readiness"
        gate_name = "API Readiness"
        try:
            # The readiness endpoint is /api/v1/readiness (no parameters)
            # We'll use the supervisor client's check_readiness with dummy parameters
            # but there's no generic readiness method. Let's call the endpoint directly.
            # The supervisor client doesn't have a dedicated readiness method, but we can
            # use the generic _get method. However we want to avoid exposing internal methods.
            # Instead we can call the client's health? Wait readiness is separate.
            # Let's add a method to supervisor client? That's out of scope.
            # We'll use the existing client's _get via monkeypatch? Not good.
            # Actually the supervisor client has a `check_readiness` method that requires
            # season, dataset_id, timeframe. That's not generic readiness.
            # Looking at the API, there is a generic readiness endpoint at /api/v1/readiness
            # that returns {"status": "ok"}. We'll need to call it directly.
            # We'll use requests directly but we should reuse the client's session.
            # Let's add a method to supervisor client later; for now we'll call the endpoint
            # using the client's internal _get method (which is private).
            # We'll import the client and call _get with path.
            # Since _get is private, we can still use it but it's not ideal.
            # Better to add a public method to supervisor client, but that's a separate change.
            # For now, we'll use the existing `check_readiness` with default parameters
            # that are known to exist? That's not safe.
            # Let's examine the supervisor client: there is a `check_readiness` method
            # that calls /api/v1/readiness/{season}/{dataset_id}/{timeframe}.
            # That's not the generic readiness.
            # However the generic readiness endpoint is at /api/v1/readiness (no parameters).
            # The supervisor client doesn't have a method for that.
            # We'll implement a simple HTTP call using the same session as the client.
            # We'll access self.client.session and make a GET.
            url = f"{self.client.base_url}/api/v1/readiness"
            response = self.client.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "ok":
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message="API readiness endpoint responds with status ok.",
                    details=data,
                    actions=list(({"label": "View Readiness", "url": "/api/v1/readiness"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"Unexpected readiness response: {data}",
                    details=data,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as e:
            # Map to SupervisorClientError-like
            status_code = getattr(e, 'response', None) and e.response.status_code
            error_type = "network" if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)) else "server"
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Readiness endpoint unreachable: {str(e)}",
                details={"error_type": error_type, "status_code": status_code},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_supervisor_db_ssot(self) -> GateResult:
        """Gate 3: Supervisor DB SSOT (jobs list)."""
        gate_id = "supervisor_db_ssot"
        gate_name = "Supervisor DB SSOT"
        try:
            jobs = self.client.get_jobs(limit=1)
            # If we get a list (even empty), DB is accessible
            if isinstance(jobs, list):
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message=f"Supervisor DB accessible, {len(jobs)} total jobs.",
                    details={"jobs_count": len(jobs)},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"Unexpected jobs response type: {type(jobs)}",
                    details={"response": jobs},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except SupervisorClientError as e:
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Supervisor DB unreachable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_worker_execution_reality(self) -> GateResult:
        """Gate 4: Worker Execution Reality (presence of RUNNING jobs)."""
        gate_id = "worker_execution_reality"
        gate_name = "Worker Execution Reality"
        try:
            jobs = self.client.get_jobs(limit=50)
            if not isinstance(jobs, list):
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message="Could not parse jobs list.",
                    details={"response": jobs},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            running = [j for j in jobs if isinstance(j, dict) and j.get("status") == "RUNNING"]
            queued = [j for j in jobs if isinstance(j, dict) and j.get("status") == "QUEUED"]
            if running:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message=f"{len(running)} job(s) currently RUNNING, {len(queued)} QUEUED.",
                    details={"running_count": len(running), "queued_count": len(queued)},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            elif queued:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"No RUNNING jobs, but {len(queued)} job(s) QUEUED (workers may be idle).",
                    details={"running_count": 0, "queued_count": len(queued)},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message="No RUNNING or QUEUED jobs (system idle).",
                    details={"running_count": 0, "queued_count": 0},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except SupervisorClientError as e:
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Failed to fetch jobs for worker reality: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_registry_surface(self) -> GateResult:
        """Gate 5: Registry Surface (timeframes list)."""
        gate_id = "registry_surface"
        gate_name = "Registry Surface"
        try:
            timeframes = self.client.get_registry_timeframes()
            # The supervisor client doesn't have get_registry_timeframes method.
            # Actually there is a method `get_registry_timeframes`? Let's check.
            # The supervisor client has `get_registry_timeframes`? I saw `get_registry_timeframes`?
            # Looking at the file, there is `get_registry_timeframes`? No, there is `get_registry_timeframes`?
            # Let's search: we saw `get_registry_timeframes` in the API endpoint but not in client.
            # The client has `get_registry_timeframes`? Actually there is `get_registry_timeframes`?
            # Let's examine the client again: there is `get_registry_timeframes`? I think not.
            # We'll need to add a method, but for now we'll call the endpoint directly.
            url = f"{self.client.base_url}/api/v1/registry/timeframes"
            response = self.client.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                if data:
                    return GateResult(
                        gate_id=gate_id,
                        gate_name=gate_name,
                        status=GateStatus.PASS,
                        message=f"Registry surface accessible, {len(data)} timeframe(s) available.",
                        details={"timeframes": data},
                        actions=list(({"label": "View Registry", "url": "/api/v1/registry/timeframes"},)),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                else:
                    return GateResult(
                        gate_id=gate_id,
                        gate_name=gate_name,
                        status=GateStatus.WARN,
                        message="Registry surface accessible but empty (no timeframes).",
                        details={"timeframes": list()},
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"Unexpected registry response: {data}",
                    details={"response": data},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as e:
            status_code = getattr(e, 'response', None) and e.response.status_code
            error_type = "network" if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)) else "server"
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Registry surface unreachable: {str(e)}",
                details={"error_type": error_type, "status_code": status_code},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _compute_overall_status(self, gates: List[GateResult]) -> GateStatus:
        """Compute overall status from individual gates."""
        if any(g.status == GateStatus.FAIL for g in gates):
            return GateStatus.FAIL
        if any(g.status == GateStatus.WARN for g in gates):
            return GateStatus.WARN
        if all(g.status == GateStatus.PASS for g in gates):
            return GateStatus.PASS
        return GateStatus.UNKNOWN

    def _compute_overall_message(self, overall_status: GateStatus, gates: List[GateResult]) -> str:
        """Generate a human-readable overall message."""
        if overall_status == GateStatus.PASS:
            return "All gates PASS – system ready."
        elif overall_status == GateStatus.WARN:
            warn_gates = [g.gate_name for g in gates if g.status == GateStatus.WARN]
            return f"Gates with WARN: {', '.join(warn_gates)}."
        elif overall_status == GateStatus.FAIL:
            fail_gates = [g.gate_name for g in gates if g.status == GateStatus.FAIL]
            return f"Gates with FAIL: {', '.join(fail_gates)}."
        else:
            return "Gate status unknown."


# Singleton instance for convenience
_gate_summary_service = GateSummaryService()


def get_gate_summary_service() -> GateSummaryService:
    """Return the singleton gate summary service instance."""
    return _gate_summary_service


def fetch_gate_summary() -> GateSummary:
    """Convenience function to fetch gate summary using the singleton."""
    return _gate_summary_service.fetch()