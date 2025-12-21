"""Hash utilities for deterministic portfolio ID generation."""

import hashlib
import json
from typing import Any


def stable_json_dumps(obj: Any) -> str:
    """Deterministic JSON dumps: sort_keys=True, separators=(',', ':'), ensure_ascii=False"""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        default=str  # Handle non-serializable types
    )


def sha1_text(s: str) -> str:
    """SHA1 hex digest for text."""
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def hash_params(params: dict[str, float]) -> str:
    """
    Deterministic hash of strategy parameters.
    
    Uses stable JSON serialization and SHA1.
    """
    if not params:
        return "empty"
    return sha1_text(stable_json_dumps(params))