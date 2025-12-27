
"""Run ID generation for audit trail.

Provides deterministic, sortable run IDs with timestamp and short token.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def make_run_id(prefix: str | None = None) -> str:
    """
    Generate a sortable, readable run ID.
    
    Format: {prefix-}YYYYMMDDTHHMMSSZ-{token}
    - Timestamp ensures chronological ordering (UTC)
    - Short token (8 hex chars) provides uniqueness
    
    Args:
        prefix: Optional prefix string (e.g., "test", "prod")
        
    Returns:
        Run ID string, e.g., "20251218T135221Z-a1b2c3d4"
        or "test-20251218T135221Z-a1b2c3d4" if prefix provided
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tok = secrets.token_hex(4)  # 8 hex chars
    
    if prefix:
        return f"{prefix}-{ts}-{tok}"
    else:
        return f"{ts}-{tok}"


