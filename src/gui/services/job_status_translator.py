"""
Job Status Semantic Translator – pure function mapping (status, error_details) to human-readable explanation.

This is a presentation-layer utility that derives explanations from existing data only.
It relies on ExplainAdapter when job_id is available to surface SSOT summaries.
"""

from typing import Optional, Dict, Any

from gui.services.explain_adapter import ExplainAdapter, FALLBACK_SUMMARY
from gui.services.supervisor_client import SupervisorClientError
from gui.services.explain_cache import get_cache_instance


_explain_adapter = ExplainAdapter(cache=get_cache_instance())


def _try_explain_summary(job_id: Optional[str]) -> tuple[Optional[str], Optional[str], bool]:
    """Attempt to fetch ExplainAdapter summary + action hint for a job."""
    if not job_id:
        return None, None, False
    try:
        reason = _explain_adapter.get_job_reason(job_id)
        return reason.summary, reason.action_hint, reason.fallback
    except SupervisorClientError:
        return None, None, True


def translate_job_status(
    status: str,
    error_details: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
) -> str:
    """
    Return a short human-readable explanation for a job status.

    Parameters
    ----------
    status : str
        Job status as returned by API (e.g., "SUCCEEDED", "FAILED", "ABORTED", "RUNNING").
    error_details : dict or None
        Structured error details as defined in the supervisor DB schema.
        Expected keys: "type", "msg", "pid", "traceback", "phase", "timestamp".
    job_id : Optional[str]
        Job ID used to fetch Explain SSOT payload when available.
    """
    summary, action_hint, explain_failed = _try_explain_summary(job_id)
    if summary:
        text = summary
        if action_hint:
            text = f"{summary} Next: {action_hint}"
        return text
    if explain_failed:
        return FALLBACK_SUMMARY

    if not error_details or not isinstance(error_details, dict):
        if status == "SUCCEEDED":
            return "Job completed successfully."
        elif status == "RUNNING":
            return "Job is currently running."
        elif status == "QUEUED":
            return "Job is queued, waiting for a worker."
        elif status == "PENDING":
            return "Job is pending (not yet started)."
        elif status == "FAILED":
            return "Job failed (unknown reason)."
        elif status == "ABORTED":
            return "Job was aborted (unknown reason)."
        elif status == "REJECTED":
            return "Job was rejected (policy violation)."
        else:
            return f"Job status: {status}."

    error_type = error_details.get("type")
    msg = error_details.get("msg", "")

    if status == "ABORTED":
        if error_type == "AbortRequested":
            if "user_abort" in msg or "user" in msg.lower():
                return "User manually aborted the job."
            else:
                return "Job was aborted by supervisor."
        elif error_type == "HeartbeatTimeout":
            return "Job timed out (heartbeat lost) and was aborted by watchdog."
        elif error_type == "Orphaned":
            return "Job was orphaned (worker disappeared) and aborted."
        else:
            return "Job was aborted."

    elif status == "FAILED":
        if error_type == "ExecutionError":
            if "timeout" in msg.lower():
                return "Worker execution timed out."
            elif "import" in msg.lower() or "module" in msg.lower():
                return "Environment or dependency error (missing module)."
            else:
                return f"Execution error: {msg[:60]}"
        elif error_type == "ValidationError":
            return "Job parameters failed validation."
        elif error_type == "SpecParseError":
            return "Job specification could not be parsed."
        elif error_type == "UnknownHandler":
            return "Unknown job handler (internal error)."
        elif error_type == "HeartbeatTimeout":
            return "Worker heartbeat timeout – job failed."
        else:
            return f"Job failed: {msg[:60]}"

    elif status == "REJECTED":
        if error_type == "ValidationError":
            return "Job rejected due to parameter validation failure."
        else:
            return "Job rejected (policy violation)."

    elif status == "SUCCEEDED":
        return "Job completed successfully."

    if error_type:
        return f"{status} – {error_type}: {msg[:60]}"
    else:
        return f"{status} – {msg[:60]}" if msg else f"Job status: {status}."


def explain_job(job: Dict[str, Any]) -> str:
    status = job.get("status", "UNKNOWN")
    error_details = job.get("error_details")
    job_id = job.get("job_id")
    return translate_job_status(status, error_details, job_id=job_id)