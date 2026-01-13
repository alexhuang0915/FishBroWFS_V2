"""
Job Status Semantic Translator – pure function mapping (status, error_details) to human-readable explanation.

This is a presentation‑layer utility that derives explanations from existing data only.
No network calls, no state changes, no branching on new fields.
"""

from typing import Optional, Dict, Any


def translate_job_status(status: str, error_details: Optional[Dict[str, Any]] = None) -> str:
    """
    Return a short human‑readable explanation for a job status.

    Parameters
    ----------
    status : str
        Job status as returned by API (e.g., "SUCCEEDED", "FAILED", "ABORTED", "RUNNING").
    error_details : dict or None
        Structured error details as defined in the supervisor DB schema.
        Expected keys: "type", "msg", "pid", "traceback", "phase", "timestamp".

    Returns
    -------
    str
        Explanation suitable for UI display.
        Unknown patterns fall back to a generic message.
    """
    if not error_details or not isinstance(error_details, dict):
        # No error details or malformed – generic status descriptions
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

    # Use error_details.type to refine explanation
    error_type = error_details.get("type")
    msg = error_details.get("msg", "")
    phase = error_details.get("phase", "")

    # Mapping based on error_type and status
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
        # Policy rejection
        if error_type == "ValidationError":
            return "Job rejected due to parameter validation failure."
        else:
            return "Job rejected (policy violation)."

    elif status == "SUCCEEDED":
        # Should not have error_details, but if present, ignore
        return "Job completed successfully."

    # Fallback for unknown status/type combinations
    if error_type:
        return f"{status} – {error_type}: {msg[:60]}"
    else:
        return f"{status} – {msg[:60]}" if msg else f"Job status: {status}."


# Convenience function for UI that receives a job dict
def explain_job(job: Dict[str, Any]) -> str:
    """
    Extract status and error_details from a job dict and return explanation.

    Parameters
    ----------
    job : dict
        Job dictionary as returned by /api/v1/jobs (must contain "status"
        and optionally "error_details").

    Returns
    -------
    str
        Human‑readable explanation.
    """
    status = job.get("status", "UNKNOWN")
    error_details = job.get("error_details")
    return translate_job_status(status, error_details)