"""
Desktop GUI configuration constants.

This module defines the single source of truth for supervisor endpoint
and other desktop configuration values.

All desktop code MUST import constants from here, never hardcode URLs.
"""

# Supervisor API endpoint (FIXED, NON-NEGOTIABLE)
SUPERVISOR_BASE_URL = "http://127.0.0.1:8000"

# Health check endpoint path (relative to base URL)
SUPERVISOR_HEALTH_PATH = "/health"

# Default timeout for supervisor operations (seconds)
SUPERVISOR_TIMEOUT_SEC = 10

# Default retry configuration for supervisor startup
SUPERVISOR_STARTUP_RETRY_COUNT = 3
SUPERVISOR_STARTUP_RETRY_DELAY_SEC = 1.0

# Log file paths for supervisor runtime logs
from core.paths import get_runtime_root
SUPERVISOR_RUNTIME_LOG = str(get_runtime_root() / "logs" / "desktop_supervisor_runtime.log")
SUPERVISOR_ENTRYPOINT_LOG = str(get_runtime_root() / "logs" / "phase_d_supervisor_entrypoint.txt")