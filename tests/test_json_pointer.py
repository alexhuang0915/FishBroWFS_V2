"""Tests for JSON Pointer resolver.

Tests normal pointer, list index, missing keys, and never-raise contract.
"""

from __future__ import annotations

import pytest

from FishBroWFS_V2.gui.viewer.json_pointer import resolve_json_pointer


def test_normal_pointer() -> None:
    """Test normal object key pointer."""
    data = {
        "a": {
            "b": {
                "c": "value"
            }
        }
    }
    
    found, value = resolve_json_pointer(data, "/a/b/c")
    assert found is True
    assert value == "value"
    
    found, value = resolve_json_pointer(data, "/a/b")
    assert found is True
    assert value == {"c": "value"}


def test_list_index() -> None:
    """Test list index in pointer."""
    data = {
        "items": [
            {"name": "first"},
            {"name": "second"},
        ]
    }
    
    found, value = resolve_json_pointer(data, "/items/0/name")
    assert found is True
    assert value == "first"
    
    found, value = resolve_json_pointer(data, "/items/1/name")
    assert found is True
    assert value == "second"
    
    found, value = resolve_json_pointer(data, "/items/0")
    assert found is True
    assert value == {"name": "first"}


def test_list_index_out_of_bounds() -> None:
    """Test list index out of bounds."""
    data = {
        "items": [1, 2, 3]
    }
    
    found, value = resolve_json_pointer(data, "/items/10")
    assert found is False
    assert value is None
    
    found, value = resolve_json_pointer(data, "/items/-1")
    assert found is False
    assert value is None


def test_missing_key() -> None:
    """Test missing key in pointer."""
    data = {
        "a": {
            "b": "value"
        }
    }
    
    found, value = resolve_json_pointer(data, "/a/c")
    assert found is False
    assert value is None
    
    found, value = resolve_json_pointer(data, "/x/y")
    assert found is False
    assert value is None


def test_root_pointer_disabled() -> None:
    """Test root pointer is disabled (by design for Viewer UX)."""
    data = {"a": 1, "b": 2}
    
    # Root pointer "/" is intentionally disabled
    found, value = resolve_json_pointer(data, "/")
    assert found is False
    assert value is None
    
    # Empty string is also disabled
    found, value = resolve_json_pointer(data, "")
    assert found is False
    assert value is None


def test_invalid_pointer_format() -> None:
    """Test invalid pointer format."""
    data = {"a": 1}
    
    # Missing leading slash
    found, value = resolve_json_pointer(data, "a/b")
    assert found is False
    assert value is None


def test_nested_list_and_dict() -> None:
    """Test nested list and dict combination."""
    data = {
        "results": [
            {
                "metrics": {
                    "score": 100
                }
            },
            {
                "metrics": {
                    "score": 200
                }
            }
        ]
    }
    
    found, value = resolve_json_pointer(data, "/results/0/metrics/score")
    assert found is True
    assert value == 100
    
    found, value = resolve_json_pointer(data, "/results/1/metrics/score")
    assert found is True
    assert value == 200


def test_never_raises() -> None:
    """Test that resolve_json_pointer never raises exceptions."""
    # Test with None data
    found, value = resolve_json_pointer(None, "/a")  # type: ignore
    assert found is False
    assert value is None
    
    # Test with invalid data types
    found, value = resolve_json_pointer("string", "/a")  # type: ignore
    assert found is False
    assert value is None
    
    # Test with empty dict (valid, but key missing)
    found, value = resolve_json_pointer({}, "/a")
    assert found is False
    assert value is None
    
    # Test with invalid pointer type
    found, value = resolve_json_pointer({"a": 1}, None)  # type: ignore
    assert found is False
    assert value is None
    
    # Test with empty string pointer
    found, value = resolve_json_pointer({"a": 1}, "")
    assert found is False
    assert value is None
    
    # Test with root pointer (disabled)
    found, value = resolve_json_pointer({"a": 1}, "/")
    assert found is False
    assert value is None
    
    # Test with valid pointer
    found, value = resolve_json_pointer({"a": 1}, "/a")
    assert found is True
    assert value == 1


def test_critical_scenarios() -> None:
    """Test critical scenarios that must pass."""
    data = {"a": 1}
    
    # Scenario 1: None pointer
    found, value = resolve_json_pointer(data, None)  # type: ignore
    assert found is False
    assert value is None
    
    # Scenario 2: Empty string pointer
    found, value = resolve_json_pointer(data, "")
    assert found is False
    assert value is None
    
    # Scenario 3: Root pointer (disabled by design)
    found, value = resolve_json_pointer(data, "/")
    assert found is False
    assert value is None
    
    # Scenario 4: Valid pointer
    found, value = resolve_json_pointer(data, "/a")
    assert found is True
    assert value == 1


def test_intermediate_type_mismatch() -> None:
    """Test intermediate type mismatch."""
    data = {
        "items": "not_a_list"
    }
    
    # Try to access list index on string
    found, value = resolve_json_pointer(data, "/items/0")
    assert found is False
    assert value is None
    
    data = {
        "items": [1, 2, 3]
    }
    
    # Try to access dict key on list
    found, value = resolve_json_pointer(data, "/items/key")
    assert found is False
    assert value is None
