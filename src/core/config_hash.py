
"""Stable config hash computation.

Provides deterministic hash of configuration objects for reproducibility.
Uses same canonicalization as stable_params_hash for consistency.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonicalize_for_json(obj: Any) -> Any:
    """
    Recursively canonicalize Python objects for deterministic JSON serialization.
    
    Rules:
    - numpy scalar (int64, float64) → Python int/float
    - tuple → list
    - Decimal → str (standard decimal representation)
    - dict keys are sorted (handled by json.dumps sort_keys)
    - list/tuple elements are recursively canonicalized
    - dict values are recursively canonicalized
    """
    # Try to import numpy (optional)
    try:
        import numpy as np
        HAS_NUMPY = True
    except ImportError:
        HAS_NUMPY = False
    
    # Decimal detection
    try:
        from decimal import Decimal
        HAS_DECIMAL = True
    except ImportError:
        HAS_DECIMAL = False
    
    if HAS_NUMPY and isinstance(obj, np.integer):
        return int(obj)
    if HAS_NUMPY and isinstance(obj, np.floating):
        return float(obj)
    if HAS_DECIMAL and isinstance(obj, Decimal):
        # Use standard string representation (no scientific notation)
        return str(obj)
    if isinstance(obj, tuple):
        return [_canonicalize_for_json(item) for item in obj]
    if isinstance(obj, list):
        return [_canonicalize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        # Note: sorting of keys is done by json.dumps with sort_keys=True
        # but we still need to canonicalize values.
        return {key: _canonicalize_for_json(value) for key, value in obj.items()}
    # For any other type, assume it's already JSON serializable (int, float, str, bool, None)
    return obj


def stable_config_hash(obj: Any) -> str:
    """
    Compute stable hash of configuration object.
    
    Uses JSON serialization with sorted keys and fixed separators
    to ensure cross-platform consistency.
    Matches stable_params_hash canonicalization for consistency.
    
    Args:
        obj: Configuration object (dict, list, etc.)
        
    Returns:
        Hex string hash (64 chars, SHA256)
    """
    # Canonicalize payload before serialization
    canonical_obj = _canonicalize_for_json(obj)
    
    # Ensure deterministic JSON serialization matching canonical_json_bytes
    s = json.dumps(
        canonical_obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


