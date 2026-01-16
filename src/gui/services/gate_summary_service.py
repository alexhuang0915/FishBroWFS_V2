"""
Gate Summary Service for UI observability.

Provides a single SSOT client utility that fetches gate statuses from supervisor API
and returns a pure data model suitable for UI display.

Eight gates:
1. API Health (/health)
2. API Readiness (/api/v1/readiness)
3. Supervisor DB SSOT (/api/v1/jobs)
4. Worker Execution Reality (presence of RUNNING jobs)
5. Registry Surface (/api/v1/registry/timeframes)
6. Policy Enforcement (/api/v1/jobs/<job_id>/artifacts/policy_check.json)
7. Data Alignment (data_alignment_report.json)
8. Resource / OOM (resource_usage.json / oom_gate_decision.json)
9. Portfolio Admission (admission_decision.json)

Each gate returns a GateResult with status (PASS/WARN/FAIL), human message,
and optional drill‑down actions.
"""

import logging
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from control.job_artifacts import artifact_url_if_exists, job_artifact_url

from gui.services.data_alignment_status import (
    ARTIFACT_NAME,
    resolve_data_alignment_status,
)
from gui.services.resource_status import (
    resolve_resource_status,
    RESOURCE_USAGE_ARTIFACT,
    DEFAULT_MEMORY_WARN_THRESHOLD_MB,
)
from gui.services.portfolio_admission_status import (
    resolve_portfolio_admission_status,
    ADMISSION_DECISION_FILE,
    DEFAULT_CORRELATION_THRESHOLD,
    DEFAULT_MDD_THRESHOLD,
)
from gui.services.gate_reason_cards_registry import build_reason_cards_for_gate
from gui.services.explain_adapter import ExplainAdapter, FALLBACK_SUMMARY, JobReason
from gui.services.explain_cache import get_cache_instance
from gui.services.supervisor_client import SupervisorClient, SupervisorClientError

logger = logging.getLogger(__name__)

_explain_adapter = ExplainAdapter(cache=get_cache_instance())

DATA_ALIGNMENT_FORWARD_FILL_WARN_THRESHOLD = 0.5  # Warn when more than 50% of bars are held


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
    
    def _get_recent_job_id(self) -> Optional[str]:
        """Get a recent job ID for gates that need job-specific reason cards."""
        try:
            jobs = self.client.get_jobs(limit=20)
            if isinstance(jobs, list):
                for job in jobs:
                    job_id = job.get("job_id")
                    if job_id:
                        return job_id
        except SupervisorClientError:
            pass
        return None

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
                gates.append(self._fetch_data_alignment_gate())
                gates.append(self._fetch_resource_gate())
                gates.append(self._fetch_portfolio_admission_gate())
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
                # Build reason cards (empty for system health gates)
                reason_cards = build_reason_cards_for_gate(gate_id, "")
                reason_cards_dict = [card.__dict__ for card in reason_cards]
                
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message="API health endpoint responds with status ok.",
                    details={"response": response, "reason_cards": reason_cards_dict},
                    actions=list(({"label": "View Health", "url": "/health"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                # Build reason cards
                reason_cards = build_reason_cards_for_gate(gate_id, "")
                reason_cards_dict = [card.__dict__ for card in reason_cards]
                
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"Unexpected health response: {response}",
                    details={"response": response, "reason_cards": reason_cards_dict},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except SupervisorClientError as e:
            # Build reason cards
            reason_cards = build_reason_cards_for_gate(gate_id, "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Health endpoint unreachable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code, "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_api_readiness(self) -> GateResult:
        """Gate 2: API Readiness."""
        gate_id = "api_readiness"
        gate_name = "API Readiness"
        try:
            url = f"{self.client.base_url}/api/v1/readiness"
            response = self.client.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            # Get recent job ID for readiness gate reason cards
            recent_job_id = self._get_recent_job_id() or ""
            
            # Build reason cards
            reason_cards = build_reason_cards_for_gate(gate_id, recent_job_id)
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            if isinstance(data, dict) and data.get("status") == "ok":
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message="API readiness endpoint responds with status ok.",
                    details={"response": data, "reason_cards": reason_cards_dict},
                    actions=list(({"label": "View Readiness", "url": "/api/v1/readiness"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"Unexpected readiness response: {data}",
                    details={"response": data, "reason_cards": reason_cards_dict},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as e:
            # Map to SupervisorClientError-like
            status_code = getattr(e, 'response', None) and e.response.status_code
            error_type = "network" if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)) else "server"
            
            # Build reason cards even on error
            recent_job_id = self._get_recent_job_id() or ""
            reason_cards = build_reason_cards_for_gate(gate_id, recent_job_id)
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Readiness endpoint unreachable: {str(e)}",
                details={"error_type": error_type, "status_code": status_code, "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_supervisor_db_ssot(self) -> GateResult:
        """Gate 3: Supervisor DB SSOT (jobs list)."""
        gate_id = "supervisor_db_ssot"
        gate_name = "Supervisor DB SSOT"
        try:
            jobs = self.client.get_jobs(limit=1)
            
            # Build reason cards (empty for system gates)
            reason_cards = build_reason_cards_for_gate(gate_id, "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            # If we get a list (even empty), DB is accessible
            if isinstance(jobs, list):
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message=f"Supervisor DB accessible, {len(jobs)} total jobs.",
                    details={"jobs_count": len(jobs), "reason_cards": reason_cards_dict},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"Unexpected jobs response type: {type(jobs)}",
                    details={"response": jobs, "reason_cards": reason_cards_dict},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except SupervisorClientError as e:
            # Build reason cards even on error
            reason_cards = build_reason_cards_for_gate(gate_id, "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Supervisor DB unreachable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code, "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_worker_execution_reality(self) -> GateResult:
        """Gate 4: Worker Execution Reality (presence of RUNNING jobs)."""
        gate_id = "worker_execution_reality"
        gate_name = "Worker Execution Reality"
        try:
            jobs = self.client.get_jobs(limit=50)
            
            # Build reason cards (empty for system gates)
            reason_cards = build_reason_cards_for_gate(gate_id, "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            if not isinstance(jobs, list):
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message="Could not parse jobs list.",
                    details={"response": jobs, "reason_cards": reason_cards_dict},
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
                    details={"running_count": len(running), "queued_count": len(queued), "reason_cards": reason_cards_dict},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            elif queued:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.WARN,
                    message=f"No RUNNING jobs, but {len(queued)} job(s) QUEUED (workers may be idle).",
                    details={"running_count": 0, "queued_count": len(queued), "reason_cards": reason_cards_dict},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=GateStatus.PASS,
                    message="No RUNNING or QUEUED jobs (system idle).",
                    details={"running_count": 0, "queued_count": 0, "reason_cards": reason_cards_dict},
                    actions=list(({"label": "View Jobs", "url": "/api/v1/jobs"},)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except SupervisorClientError as e:
            # Build reason cards even on error
            reason_cards = build_reason_cards_for_gate(gate_id, "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Failed to fetch jobs for worker reality: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code, "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_registry_surface(self) -> GateResult:
        """Gate 5: Registry Surface (timeframes list)."""
        # Use defensive adapter to prevent crashes from missing methods
        from gui.services.registry_adapter import fetch_registry_gate_result
        try:
            result = fetch_registry_gate_result()
            # Add reason cards to the result
            reason_cards = build_reason_cards_for_gate("registry_surface", "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            # Update details to include reason cards
            if result.details is None:
                result.details = {"reason_cards": reason_cards_dict}
            elif isinstance(result.details, dict):
                result.details["reason_cards"] = reason_cards_dict
            return result
        except Exception as e:
            # Fallback if adapter itself fails
            logger.error(f"Registry surface adapter failed: {e}", exc_info=True)
            # Build reason cards even on error
            reason_cards = build_reason_cards_for_gate("registry_surface", "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            return GateResult(
                gate_id="registry_surface",
                gate_name="Registry Surface",
                status=GateStatus.FAIL,
                message=f"Registry surface check failed: {e}",
                details={"error_type": "adapter_failure", "traceback": str(e), "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _fetch_policy_enforcement_gate(self) -> GateResult:
        """Gate 6: Policy Enforcement (policy_check.json evidence)."""
        gate_id = "policy_enforcement"
        gate_name = "Policy Enforcement"
        try:
            jobs = self.client.get_jobs(limit=20)
        except SupervisorClientError as e:
            # Build reason cards even on error
            reason_cards = build_reason_cards_for_gate(gate_id, "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.FAIL,
                message=f"Policy enforcement gate unavailable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code, "reason_cards": reason_cards_dict},
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
                
                # Build reason cards for this job
                reason_cards = build_reason_cards_for_gate(gate_id, job_id)
                reason_cards_dict = [card.__dict__ for card in reason_cards]
                
                details = {
                    "job_id": job_id,
                    "failure_code": job.get("failure_code"),
                    "policy_stage": policy_stage,
                    "reason_cards": reason_cards_dict,
                }
                if explain_payload:
                    details["human_tag"] = explain_payload.human_tag
                    details["decision_layer"] = explain_payload.decision_layer
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
                
                # Build reason cards for this job
                reason_cards = build_reason_cards_for_gate(gate_id, job_id)
                reason_cards_dict = [card.__dict__ for card in reason_cards]
                
                details = {
                    "job_id": job_id,
                    "failure_code": job.get("failure_code"),
                    "policy_stage": policy_stage,
                    "reason_cards": reason_cards_dict,
                }
                if explain_payload:
                    details["human_tag"] = explain_payload.human_tag
                    details["decision_layer"] = explain_payload.decision_layer
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
                message, actions, explain_payload = self._policy_explain_context(job_id)
                
                # Build reason cards for this job
                reason_cards = build_reason_cards_for_gate(gate_id, job_id)
                reason_cards_dict = [card.__dict__ for card in reason_cards]
                
                details = {"job_id": job_id, "overall_status": job.get("status"), "reason_cards": reason_cards_dict}
                if explain_payload:
                    details["decision_layer"] = explain_payload.decision_layer
                    details["human_tag"] = explain_payload.human_tag

                status = GateStatus.WARN if explain_payload and explain_payload.fallback else GateStatus.PASS
                return GateResult(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=status,
                    message=message,
                    details=details,
                    actions=actions,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

        # No matching jobs found, return PASS with empty reason cards
        reason_cards = build_reason_cards_for_gate(gate_id, "")
        reason_cards_dict = [card.__dict__ for card in reason_cards]
        
        return GateResult(
            gate_id=gate_id,
            gate_name=gate_name,
            status=GateStatus.PASS,
            message="No policy enforcements detected yet.",
            details={"reason_cards": reason_cards_dict},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _fetch_data_alignment_gate(self) -> GateResult:
        """Gate 7: Data Alignment (forward-fill metrics)."""
        gate_id = "data_alignment"
        gate_name = "Data Alignment"
        try:
            jobs = self.client.get_jobs(limit=20)
        except SupervisorClientError as e:
            # Build reason cards even on error
            reason_cards = build_reason_cards_for_gate("data_alignment", "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.WARN,
                message=f"Data alignment gate unavailable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code, "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        sorted_jobs = sorted(jobs, key=lambda entry: entry.get("created_at", ""), reverse=True)
        for job in sorted_jobs:
            job_id = job.get("job_id")
            if not job_id:
                continue

            alignment_status = resolve_data_alignment_status(job_id)
            artifact_url = (
                artifact_url_if_exists(job_id, alignment_status.artifact_relpath)
                or job_artifact_url(job_id, alignment_status.artifact_relpath)
            )

            # Build reason cards using registry
            reason_cards = build_reason_cards_for_gate("data_alignment", job_id)
            reason_cards_dict = [card.__dict__ for card in reason_cards]

            if alignment_status.status == "OK":
                ratio = alignment_status.metrics.get("forward_fill_ratio")
                dropped = alignment_status.metrics.get("dropped_rows", 0)
                ratio_display = f"{ratio:.1%}" if isinstance(ratio, (int, float)) else "N/A"
                gate_status = (
                    GateStatus.WARN
                    if isinstance(ratio, (int, float))
                    and ratio > DATA_ALIGNMENT_FORWARD_FILL_WARN_THRESHOLD
                    else GateStatus.PASS
                )
                message = f"Forward fill ratio {ratio_display}; dropped {dropped} rows."
                details = {
                    "forward_fill_ratio": ratio,
                    "dropped_rows": dropped,
                    "job_id": job_id,
                    "reason_cards": reason_cards_dict,
                }
            else:
                gate_status = GateStatus.WARN
                message = alignment_status.message
                details = {
                    "status": alignment_status.status,
                    "job_id": job_id,
                    "reason_cards": reason_cards_dict,
                }

            actions = [{"label": "Open data alignment report", "url": artifact_url}]
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=gate_status,
                message=message,
                details=details,
                actions=actions,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # No recent jobs found, return with empty reason cards
        reason_cards = build_reason_cards_for_gate("data_alignment", "")
        reason_cards_dict = [card.__dict__ for card in reason_cards]
        return GateResult(
            gate_id=gate_id,
            gate_name=gate_name,
            status=GateStatus.WARN,
            message="Data alignment report not available for recent jobs.",
            details={"reason_cards": reason_cards_dict},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _fetch_resource_gate(self) -> GateResult:
        """Gate 8: Resource / OOM (resource usage and OOM decisions)."""
        gate_id = "resource"
        gate_name = "Resource / OOM"
        try:
            jobs = self.client.get_jobs(limit=20)
        except SupervisorClientError as e:
            # Build reason cards even on error
            reason_cards = build_reason_cards_for_gate("resource", "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.WARN,
                message=f"Resource gate unavailable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code, "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        sorted_jobs = sorted(jobs, key=lambda entry: entry.get("created_at", ""), reverse=True)
        for job in sorted_jobs:
            job_id = job.get("job_id")
            if not job_id:
                continue

            resource_status = resolve_resource_status(job_id)
            artifact_url = (
                artifact_url_if_exists(job_id, resource_status.artifact_relpath)
                or job_artifact_url(job_id, resource_status.artifact_relpath)
            )

            # Build reason cards using registry
            reason_cards = build_reason_cards_for_gate("resource", job_id)
            reason_cards_dict = [card.__dict__ for card in reason_cards]

            if resource_status.status == "OK":
                peak_memory = resource_status.metrics.get("peak_memory_mb")
                limit_mb = resource_status.metrics.get("limit_mb")
                worker_crash = resource_status.metrics.get("worker_crash", False)
                gate_status = GateStatus.PASS
                if peak_memory is not None and limit_mb is not None and peak_memory > limit_mb:
                    gate_status = GateStatus.WARN
                if worker_crash:
                    gate_status = GateStatus.FAIL
                message = f"Peak memory {peak_memory}MB, limit {limit_mb}MB"
                details = {
                    "peak_memory_mb": peak_memory,
                    "limit_mb": limit_mb,
                    "worker_crash": worker_crash,
                    "job_id": job_id,
                    "reason_cards": reason_cards_dict,
                }
            else:
                gate_status = GateStatus.WARN if resource_status.status == "WARN" else GateStatus.FAIL
                message = resource_status.message
                details = {
                    "status": resource_status.status,
                    "job_id": job_id,
                    "reason_cards": reason_cards_dict,
                }

            actions = [{"label": "Open resource report", "url": artifact_url}]
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=gate_status,
                message=message,
                details=details,
                actions=actions,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # No recent jobs found, return with empty reason cards
        reason_cards = build_reason_cards_for_gate("resource", "")
        reason_cards_dict = [card.__dict__ for card in reason_cards]
        return GateResult(
            gate_id=gate_id,
            gate_name=gate_name,
            status=GateStatus.WARN,
            message="Resource usage report not available for recent jobs.",
            details={"reason_cards": reason_cards_dict},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _fetch_portfolio_admission_gate(self) -> GateResult:
        """Gate 9: Portfolio Admission (admission decision)."""
        gate_id = "portfolio_admission"
        gate_name = "Portfolio Admission"
        try:
            jobs = self.client.get_jobs(limit=20)
        except SupervisorClientError as e:
            # Build reason cards even on error
            reason_cards = build_reason_cards_for_gate("portfolio_admission", "")
            reason_cards_dict = [card.__dict__ for card in reason_cards]
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=GateStatus.WARN,
                message=f"Portfolio admission gate unavailable: {e.message}",
                details={"error_type": e.error_type, "status_code": e.status_code, "reason_cards": reason_cards_dict},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        sorted_jobs = sorted(jobs, key=lambda entry: entry.get("created_at", ""), reverse=True)
        for job in sorted_jobs:
            job_id = job.get("job_id")
            if not job_id:
                continue

            admission_status = resolve_portfolio_admission_status(job_id)
            artifact_url = (
                artifact_url_if_exists(job_id, admission_status.artifact_relpath)
                or job_artifact_url(job_id, admission_status.artifact_relpath)
            )

            # Build reason cards using registry
            reason_cards = build_reason_cards_for_gate("portfolio_admission", job_id)
            reason_cards_dict = [card.__dict__ for card in reason_cards]

            if admission_status.status == "OK":
                verdict = admission_status.metrics.get("verdict")
                correlation_violations = admission_status.metrics.get("correlation_violations", [])
                risk_budget_steps = admission_status.metrics.get("risk_budget_steps", [])
                gate_status = GateStatus.PASS
                if verdict == "REJECTED":
                    gate_status = GateStatus.FAIL
                elif correlation_violations or risk_budget_steps:
                    gate_status = GateStatus.WARN
                message = f"Portfolio admission verdict: {verdict}"
                details = {
                    "verdict": verdict,
                    "correlation_violations": correlation_violations,
                    "risk_budget_steps": risk_budget_steps,
                    "job_id": job_id,
                    "reason_cards": reason_cards_dict,
                }
            else:
                gate_status = GateStatus.WARN if admission_status.status == "WARN" else GateStatus.FAIL
                message = admission_status.message
                details = {
                    "status": admission_status.status,
                    "job_id": job_id,
                    "reason_cards": reason_cards_dict,
                }

            actions = [{"label": "Open admission decision", "url": artifact_url}]
            return GateResult(
                gate_id=gate_id,
                gate_name=gate_name,
                status=gate_status,
                message=message,
                details=details,
                actions=actions,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # No recent jobs found, return with empty reason cards
        reason_cards = build_reason_cards_for_gate("portfolio_admission", "")
        reason_cards_dict = [card.__dict__ for card in reason_cards]
        return GateResult(
            gate_id=gate_id,
            gate_name=gate_name,
            status=GateStatus.WARN,
            message="Portfolio admission decision not available for recent jobs.",
            details={"reason_cards": reason_cards_dict},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _policy_explain_context(
        self,
        job_id: str,
        *,
        fallback_message: str = FALLBACK_SUMMARY,
    ) -> tuple[str, Optional[List[Dict[str, str]]], JobReason]:
        """Return summary message, actions, and JobReason for a job."""
        try:
            reason = _explain_adapter.get_job_reason(job_id)
        except SupervisorClientError:
            reason = _explain_adapter.fallback_reason(job_id)
        message = reason.summary or fallback_message
        if reason.action_hint:
            message = f"{message} Next: {reason.action_hint}"
        action_url = reason.evidence_urls.get("policy_check_url")
        actions = (
            [{"label": "View policy evidence", "url": action_url}]
            if action_url
            else None
        )
        return message, actions, reason

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