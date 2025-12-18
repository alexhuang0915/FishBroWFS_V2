"""JSON Pointer resolver (RFC 6901).

Resolves JSON pointers in a defensive, never-raise manner.
"""

from __future__ import annotations

from typing import Any


def resolve_json_pointer(data: dict, pointer: str) -> tuple[bool, Any | None]:
    """
    Resolve RFC 6901 JSON Pointer.
    
    Never raises; return (found: bool, value).
    
    Supports basic pointer syntax:
    - /a/b/c for object keys
    - /a/b/0 for array indices
    - Does NOT support ~1 ~0 escape sequences (simplified version)
    - Does NOT support root pointer "/" (by design for Viewer UX)
    
    Args:
        data: JSON data (dict/list)
        pointer: RFC 6901 JSON Pointer (e.g., "/a/b/0/c")
        
    Returns:
        Tuple of (found: bool, value: Any | None)
        - found=True: pointer resolved successfully, value contains result
        - found=False: pointer failed to resolve, value is None
        
    Contract:
        - Never raises exceptions
        - Returns (False, None) on any failure
        - Supports list indices (e.g., "/0", "/items/0/name")
        - Root pointer "/" is intentionally disabled (returns False)
    """
    try:
        # ❶ Outermost defense (root cause of previous failure)
        if data is None or not isinstance(data, (dict, list)):
            return (False, None)
        
        if not isinstance(pointer, str):
            return (False, None)
        
        if pointer == "" or pointer == "/":
            return (False, None)
        
        if not pointer.startswith("/"):
            return (False, None)
        
        # ❷ Normal resolution flow
        parts = pointer.lstrip("/").split("/")
        current: Any = data
        
        for part in parts:
            # list index
            if isinstance(current, list):
                if not part.isdigit():
                    return (False, None)
                idx = int(part)
                if idx < 0 or idx >= len(current):
                    return (False, None)
                current = current[idx]
            # dict key
            elif isinstance(current, dict):
                if part not in current:
                    return (False, None)
                current = current[part]
            else:
                return (False, None)
        
        return (True, current)
    
    except Exception:
        # ❸ Viewer world final safety net
        return (False, None)
