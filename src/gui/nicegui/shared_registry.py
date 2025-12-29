"""
Shared UI registry state (singleton across all UI modules).
This module holds the mutable state for UI element counting and scoping,
ensuring that all imports of ui_compat share the same data.
"""
from __future__ import annotations
import sys
import os
from typing import Dict, Any

from .contract.ui_contract import PAGE_IDS

# UI element registry v2 (scoped counts)
_UI_REGISTRY_SCOPED = {
    "pages": list(PAGE_IDS),
    "global": {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0},
    "by_page": {page_id: {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0} for page_id in PAGE_IDS},
    "totals": {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0},
}
_current_scope_stack = ["global"]


def registry_reset() -> None:
    """Reset the scoped registry (for probe)."""
    global _UI_REGISTRY_SCOPED, _current_scope_stack
    if os.environ.get("FISHBRO_UI_FORENSICS"):
        sys.stderr.write(f"[shared_registry] registry_reset before reset stack={_current_scope_stack} stack id={id(_current_scope_stack)}\n")
    _UI_REGISTRY_SCOPED = {
        "pages": list(PAGE_IDS),
        "global": {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0},
        "by_page": {page_id: {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0} for page_id in PAGE_IDS},
        "totals": {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0},
    }
    _current_scope_stack = ["global"]
    if os.environ.get("FISHBRO_UI_FORENSICS"):
        sys.stderr.write(f"[shared_registry] registry_reset after reset stack={_current_scope_stack} stack id={id(_current_scope_stack)}\n")


def registry_begin_scope(scope: str) -> None:
    """Start a new scope (push onto stack)."""
    _current_scope_stack.append(scope)
    if os.environ.get("FISHBRO_UI_FORENSICS"):
        sys.stderr.write(f"[shared_registry] registry_begin_scope {scope} stack={_current_scope_stack}\n")
        sys.stderr.write(f"[shared_registry] registry_begin_scope stack id={id(_current_scope_stack)}\n")
        sys.stderr.write(f"[shared_registry] registry_begin_scope module={__name__} file={__file__}\n")
    if scope != "global":
        _ensure_page_bucket(scope)


def registry_end_scope() -> None:
    """End the current scope (pop stack)."""
    if os.environ.get("FISHBRO_UI_FORENSICS"):
        sys.stderr.write(f"[shared_registry] registry_end_scope before pop stack={_current_scope_stack}\n")
    if len(_current_scope_stack) > 1:
        _current_scope_stack.pop()
        if os.environ.get("FISHBRO_UI_FORENSICS"):
            sys.stderr.write(f"[shared_registry] registry_end_scope after pop stack={_current_scope_stack}\n")


def _get_current_scope() -> str:
    """Return the current active scope."""
    return _current_scope_stack[-1]


def _ensure_page_bucket(page_id: str) -> None:
    """Ensure a by_page entry exists for the given page."""
    if page_id not in _UI_REGISTRY_SCOPED["by_page"]:
        _UI_REGISTRY_SCOPED["by_page"][page_id] = {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0}


def increment_count(element_type: str) -> None:
    """Increment counts for current scope and totals."""
    scope = _get_current_scope()
    if os.environ.get("FISHBRO_UI_FORENSICS"):
        sys.stderr.write(f"[shared_registry] increment_count scope={scope} element_type={element_type} stack={_current_scope_stack}\n")
        sys.stderr.write(f"[shared_registry] increment_count stack id={id(_current_scope_stack)}\n")
        sys.stderr.write(f"[shared_registry] increment_count module={__name__} file={__file__}\n")
    if scope == "global":
        bucket = _UI_REGISTRY_SCOPED["global"]
    else:
        bucket = _UI_REGISTRY_SCOPED["by_page"].get(scope)
        if bucket is None:
            bucket = {"buttons": 0, "inputs": 0, "cards": 0, "selects": 0, "checkboxes": 0, "tables": 0, "logs": 0}
            _UI_REGISTRY_SCOPED["by_page"][scope] = bucket
    bucket[element_type] = bucket.get(element_type, 0) + 1
    if os.environ.get("FISHBRO_UI_FORENSICS"):
        sys.stderr.write(f"[shared_registry] after increment bucket[{element_type}] = {bucket[element_type]}\n")
        # Debug: print entire bucket for certain types
        if element_type in ["cards", "buttons", "tables", "logs"]:
            sys.stderr.write(f"[shared_registry] bucket state: {bucket}\n")
    _UI_REGISTRY_SCOPED["totals"][element_type] = _UI_REGISTRY_SCOPED["totals"].get(element_type, 0) + 1


def registry_snapshot() -> dict:
    """Return a copy of the scoped registry."""
    import copy
    return copy.deepcopy(_UI_REGISTRY_SCOPED)


def registry_counts_for_scope(scope: str) -> dict:
    """Return counts for a specific scope."""
    if scope == "global":
        return _UI_REGISTRY_SCOPED["global"].copy()
    return _UI_REGISTRY_SCOPED["by_page"].get(scope, {}).copy()


def snapshot_by_page() -> dict[str, dict[str, int]]:
    """Return a deep copy of the internal by_page dictionary."""
    import copy
    return copy.deepcopy(_UI_REGISTRY_SCOPED["by_page"])