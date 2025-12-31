"""JSON-safe sanitization utilities for NiceGUI tables."""
import json
from typing import Any, Dict, List, Union
from nicegui import ui


def _json_safe(value: Any) -> Any:
    """
    Convert a value to JSON-safe representation.
    
    Rules:
    1. If value is a ui.element (Button, etc.), return a placeholder string
    2. If value is a dict/list, recursively sanitize
    3. Otherwise return as-is (primitives)
    
    Args:
        value: Any value that might be placed in table rows
        
    Returns:
        JSON-serializable value
    """
    # Check if it's a ui.element (crude detection)
    if hasattr(value, '__class__') and hasattr(value.__class__, '__module__'):
        module = value.__class__.__module__
        if module and ('nicegui' in module or 'ui' in module):
            # Return a placeholder that can be replaced with a slot later
            return f"__ui_element_{id(value)}__"
    
    # Handle dicts
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    
    # Handle lists
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    
    # Return primitives as-is
    return value


def sanitize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sanitize a list of row dictionaries to ensure JSON serializability.
    
    Args:
        rows: List of row dicts that may contain ui.elements
        
    Returns:
        List of sanitized row dicts
    """
    return [_json_safe(row) for row in rows]


def verify_json_serializable(obj: Any) -> bool:
    """
    Verify that an object is JSON serializable.
    
    Args:
        obj: Any object to test
        
    Returns:
        True if json.dumps succeeds, False otherwise
    """
    try:
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False