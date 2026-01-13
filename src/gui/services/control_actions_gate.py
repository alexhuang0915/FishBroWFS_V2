"""
Control Actions Gate – SSOT for UI control actions (abort, etc.) safety gating.

Implements deterministic, testable gate functions that decide whether
control actions (job abort, etc.) are allowed in the current environment.

Rules:
- Enabled if and only if environment indicates DEV/LOCAL mode OR explicit opt-in flag is set.
- Default behavior: disabled (safe).
- Must be deterministic and unit-testable.
- No network calls, no state changes.

Gate decision is based on environment variable FISHBRO_ENABLE_CONTROL_ACTIONS=1.
This follows the project's environment variable pattern (FISHBRO_*).
"""

import os
from typing import Optional, Dict, Any


def is_control_actions_enabled() -> bool:
    """
    Return True if control actions (abort, etc.) are allowed in the current environment.
    
    Decision rules:
    1. Enabled if FISHBRO_ENABLE_CONTROL_ACTIONS environment variable equals "1"
    2. Otherwise disabled (safe default)
    
    Returns:
        bool: True if control actions are allowed, False otherwise.
    """
    return os.environ.get("FISHBRO_ENABLE_CONTROL_ACTIONS", "").strip() == "1"


def get_control_actions_block_reason() -> Optional[str]:
    """
    Return a human-readable reason why control actions are blocked, or None if enabled.
    
    This provides deterministic, stable strings for UI tooltips and logging.
    
    Returns:
        Optional[str]: Block reason string if disabled, None if enabled.
    """
    if is_control_actions_enabled():
        return None
    
    # Provide specific reason based on environment
    env_value = os.environ.get("FISHBRO_ENABLE_CONTROL_ACTIONS")
    if env_value is None:
        return "Control actions disabled by default (FISHBRO_ENABLE_CONTROL_ACTIONS not set)"
    elif env_value.strip() == "":
        return "Control actions disabled (FISHBRO_ENABLE_CONTROL_ACTIONS is empty)"
    else:
        return f"Control actions disabled (FISHBRO_ENABLE_CONTROL_ACTIONS={env_value!r}, expected '1')"


# Convenience function for checking if a specific job status is abortable
def is_job_abortable(job_status: str) -> bool:
    """
    Return True if a job with the given status can be aborted.
    
    This is a pure function based on job status only.
    Does NOT consider the control actions gate - caller must combine with is_control_actions_enabled().
    
    Args:
        job_status: Job status string from API (e.g., "QUEUED", "RUNNING", "SUCCEEDED")
    
    Returns:
        bool: True if status is abortable (QUEUED or RUNNING equivalents)
    """
    # Map of abortable statuses based on supervisor API
    abortable_statuses = {"QUEUED", "RUNNING", "PENDING", "STARTED"}
    return job_status in abortable_statuses


# Convenience function for combined check
def is_abort_allowed(job_status: str) -> bool:
    """
    Combined check: returns True if both control actions are enabled AND job is abortable.
    
    This is the primary function UI should use to decide whether to show/enable abort action.
    
    Args:
        job_status: Job status string from API
    
    Returns:
        bool: True if abort action should be available
    """
    return is_control_actions_enabled() and is_job_abortable(job_status)


def get_control_actions_indicator_text() -> tuple[str, str]:
    """
    Generate text for the control actions status indicator (D1).
    
    Returns:
        tuple[str, str]: (primary_label, secondary_text)
        When gate disabled:
            primary: "Control Actions: DISABLED"
            secondary: "Disabled (safe default)"
        When gate enabled:
            primary: "Control Actions: ENABLED"
            secondary: "Enabled by: ENV (FISHBRO_ENABLE_CONTROL_ACTIONS=1)"
    """
    if is_control_actions_enabled():
        primary = "Control Actions: ENABLED"
        secondary = "Enabled by: ENV (FISHBRO_ENABLE_CONTROL_ACTIONS=1)"
    else:
        primary = "Control Actions: DISABLED"
        secondary = "Disabled (safe default)"
    
    return primary, secondary


def get_control_actions_indicator_tooltip() -> str:
    """
    Generate tooltip text for the control actions status indicator.
    
    Returns:
        str: Tooltip text with hint about enabling.
    """
    if is_control_actions_enabled():
        return "Control actions are enabled via environment variable."
    else:
        return "Control actions are disabled by default for safety. Enable via ENV FISHBRO_ENABLE_CONTROL_ACTIONS=1"


def get_abort_button_tooltip(is_enabled: bool, job_status: str = "") -> str:
    """
    Generate tooltip text for the Abort button (D2).

    Args:
        is_enabled: Whether the abort button is enabled/visible
        job_status: Job status string (optional, for context)

    Returns:
        str: Tooltip text per contract:
            When enabled: "Requests job abort\nRequires confirmation\nWrites an audit record\nJob may take time to stop"
            When disabled: "Control actions are disabled\nEnable via ENV FISHBRO_ENABLE_CONTROL_ACTIONS=1"
    """
    if is_enabled:
        lines = [
            "Requests job abort",
            "Requires confirmation",
            "Writes an audit record",
            "Job may take time to stop"
        ]
        return "\n".join(lines)
    else:
        lines = [
            "Control actions are disabled",
            "Enable via ENV FISHBRO_ENABLE_CONTROL_ACTIONS=1"
        ]
        return "\n".join(lines)


def get_abort_attribution_summary(job_status: str, error_details: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a read-only attribution summary for aborted jobs (D3).

    This provides a deterministic, stable string that can be displayed in job detail
    surfaces (e.g., failure explanation dialog) to clarify why a job was aborted.

    Args:
        job_status: Job status string (should be "ABORTED" for meaningful output)
        error_details: Structured error details from API (optional)

    Returns:
        str: Attribution summary, e.g.:
            - "User manually aborted the job."
            - "Job was aborted by supervisor (heartbeat timeout)."
            - "Job was orphaned (worker disappeared)."
            - "Abort reason unknown."
    """
    from typing import Dict, Any
    if job_status != "ABORTED":
        return ""
    
    if not error_details or not isinstance(error_details, dict):
        return "Abort reason unknown."
    
    error_type = error_details.get("type")
    msg = error_details.get("msg", "")
    
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