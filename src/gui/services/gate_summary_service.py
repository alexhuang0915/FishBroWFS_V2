"""
Gate Summary Service for UI observability.

Provides a single SSOT client utility that fetches gate statuses from supervisor API
and returns a pure data model suitable for UI display.

Six gates:
1. API Health (/health)
2. API Readiness (/api/v1/readiness)
3. Supervisor DB SSOT (/api/v1/jobs)
4. Worker Execution Reality (presence of RUNNING jobs)
5. Registry Surface (/api/v1/registry/timeframes)
6. Policy Enforcement (/api/v1/jobs/<job_id>/artifacts/policy_check.json)

Each gate returns a GateResult with status (PASS/WARN/FAIL), human message,
and optional drill‑down actions.
"""

import logging
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from gui.services.explain_cache import get_job_explain
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
                gates.append(self._fetch_policy_enforcement_gate())
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
        # Use defensive adapter to prevent crashes from missing methods
        from gui.services.registry_adapter import fetch_registry_gate_result
        try:
            return fetch_registry_gate_result()
        except Exception as e:
            # Fallback if adapter itself fails
            logger.error(f"Registry surface adapter failed: {e}", exc_info=True)
            return GateResult(
                gate_id="registry_surface",
                gate_name="Registry Surface",
                status=GateStatus.FAIL,
                message=f"Registry surface check failed: {e}",
                details={"error_type": "adapter_failure", "traceback": str(e)},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_policy_enforcement_gate(self) -> GateResult:
        """Gate 6: Policy Enforcement (policy_check.json evidence)."""
        gate_id = "policy_enforcement"
        gate_name = "Policy Enforcement"
        try:
            jobs = self.client.get_jobs(limit=20)
        except SupervisorClientError as e:
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Policy enforcement gate unavailable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        def job_id_from(entry: dict) -> str:
            return entry.get("job_id", "<unknown>")

        sorted_jobs = sorted(jobs, key=lambda entry: entry.get("created_at", ""), reverse=True)

        for job in sorted_jobs:
            status = job.get("status")
            policy_stage = job.get("policy_stage") or ""
            if status == "REJECTED" and policy_stage == "preflight":
                job_id = job_id_from(job)
                message, actions, explain_payload = self._policy_explain_context(job_id)
                details = {
                    "job_id": job_id,
                    "failure_code": job.get("failure_code"),
                    "policy_stage": policy_stage,
                }
                if explain_payload:
                    details["human_tag"] = explain_payload.get("human_tag")
                    details["decision_layer"] = explain_payload.get("decision_layer")
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.FAIL,
                    message=message,
                    details=details,
                    actions=actions,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            if status == "FAILED" and policy_stage == "postflight":
                job_id = job_id_from(job)
                message, actions, explain_payload = self._policy_explain_context(job_id)
                details = {
                    "job_id": job_id,
                    "failure_code": job.get("failure_code"),
                    "policy_stage": policy_stage,
                }
                if explain_payload:
                    details["human_tag"] = explain_payload.get("human_tag")
                    details["decision_layer"] = explain_payload.get("decision_layer")
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.FAIL,
                    message=message,
                    details=details,
                    actions=actions,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

        for job in sorted_jobs:
            if job.get("status") == "SUCCEEDED":
                job_id = job_id_from(job)
                try:
                    payload = get_job_explain(job_id)
                except SupervisorClientError as e:
                    message, actions, _ = self._policy_explain_context(
                        job_id,
                        fetch=False,
                    )
                    return GateResult(
                        gate_id=gate_id,
                        gate_name=gate_name,
                        status=GateStatus.WARN,
                        message=message,
                        details={"job_id": job_id, "error": e.message},
                        actions=actions,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                except Exception as exc:
                    message, actions, _ = self._policy_explain_context(
                        job_id,
                        fetch=False,
                    )
                    return GateResult(
                        gate_id=gate_id,
                        gate_name=gate_name,
                        status=GateStatus.WARN,
                        message=message,
                        details={"job_id": job_id, "error": str(exc)},
                        actions=actions,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )

                overall_status = payload.get("final_status", "")
                message, actions, _ = self._policy_explain_context(job_id, payload=payload)
                details = {"job_id": job_id, "overall_status": overall_status}
                if payload:
                    details["decision_layer"] = payload.get("decision_layer")
                    details["human_tag"] = payload.get("human_tag")

                if overall_status == "SUCCEEDED":
                    return GateResult(
                        gate_id=gate_id,
                        gate_name=gate_name,
                        status=GateStatus.PASS,
                        message=message,
                        details=details,
                        actions=actions,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.FAIL,
                    message=message,
                    details=details,
                    actions=actions,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

        return GateResult(
            gate_id=gate_id,
            gate_name=gate_name,
            status=GateStatus.PASS,
            message="No policy enforcements detected yet.",
            details={},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _policy_explain_context(
        self,
        job_id: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        fetch: bool = True,
        fallback_message: str = "Explain unavailable; open policy evidence if present.",
    ) -> tuple[str, Optional[List[Dict[str, str]]], Optional[Dict[str, Any]]]:
        """Return summary message, actions, and explain payload for a job."""
        message = fallback_message
        action_url = f"/api/v1/jobs/{job_id}/artifacts/policy_check.json"
        explain_payload: Optional[Dict[str, Any]] = payload
        if explain_payload is None and fetch:
            try:
                explain_payload = get_job_explain(job_id)
            except SupervisorClientError:
                explain_payload = None

        if explain_payload:
            summary = explain_payload.get("summary")
            if summary:
                message = summary
            evidence = explain_payload.get("evidence") or {}
            action_url = evidence.get("policy_check_url") or action_url

        actions = (
            [{"label": "View policy evidence", "url": action_url}]
            if action_url
            else None
        )
        return message, actions, explain_payload

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