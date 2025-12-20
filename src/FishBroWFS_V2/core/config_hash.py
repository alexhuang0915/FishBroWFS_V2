"""Stable config hash computation.

Provides deterministic hash of configuration objects for reproducibility.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_config_hash(obj: Any) -> str:
    """
    Compute stable hash of configuration object.
    
    Uses JSON serialization with sorted keys and fixed separators
    to ensure cross-platform consistency.
    
    Args:
        obj: Configuration object (dict, list, etc.)
        
    Returns:
        Hex string hash (64 chars, SHA256)
    """
    s = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
