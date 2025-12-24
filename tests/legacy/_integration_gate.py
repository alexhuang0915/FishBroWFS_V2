"""Integration Gate for legacy tests.

Provides a unified gate for dashboard-dependent integration tests.
"""

import os
import pytest
import urllib.request
import requests

DEFAULT_BASE_URL = "http://localhost:8080"
CONTROL_API_BASE_URL = "http://127.0.0.1:8000"


def integration_enabled() -> bool:
    """Return True if integration tests are enabled."""
    return os.getenv("FISHBRO_RUN_INTEGRATION") == "1"


def base_url() -> str:
    """Return the base URL for the dashboard."""
    return os.getenv("FISHBRO_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def control_api_base_url() -> str:
    """Return the base URL for the Control API."""
    return os.getenv("FISHBRO_CONTROL_API_BASE", CONTROL_API_BASE_URL).rstrip("/")


def require_integration():
    """Skip test if integration is not enabled or dashboard is not running."""
    if not integration_enabled():
        pytest.skip("integration disabled: set FISHBRO_RUN_INTEGRATION=1")
    
    # Also check dashboard health for integration tests
    # This ensures no tests run when dashboard is not available
    b = base_url()
    try:
        r = urllib.request.urlopen(b + "/health", timeout=2.0)
        code = getattr(r, "status", 200)
        if code >= 500:
            pytest.skip(
                f"dashboard unhealthy: {b}/health => {code}. Start: make dashboard"
            )
    except Exception:
        pytest.skip(
            f"dashboard not running at {b}. Start: make dashboard or set FISHBRO_BASE_URL"
        )


def require_dashboard_health(timeout: float = 2.0) -> str:
    """
    Returns base_url if dashboard is healthy.
    If dashboard isn't running, SKIP with actionable message.
    """
    require_integration()
    b = base_url()
    try:
        r = urllib.request.urlopen(b + "/health", timeout=timeout)
        code = getattr(r, "status", 200)
        if code >= 500:
            pytest.skip(
                f"dashboard unhealthy: {b}/health => {code}. Start: make dashboard"
            )
        return b
    except Exception:
        pytest.skip(
            f"dashboard not running at {b}. Start: make dashboard or set FISHBRO_BASE_URL"
        )


def require_control_api_health(timeout: float = 2.0) -> str:
    """
    Returns Control API base_url if Control API is healthy.
    If Control API isn't running, SKIP with actionable message.
    """
    require_integration()
    b = control_api_base_url()
    try:
        r = requests.get(b + "/health", timeout=timeout)
        if r.status_code >= 500:
            pytest.skip(
                f"Control API unhealthy: {b}/health => {r.status_code}. Start: make control-api"
            )
        return b
    except Exception:
        pytest.skip(
            f"Control API not running at {b}. Start: make control-api or set FISHBRO_CONTROL_API_BASE"
        )