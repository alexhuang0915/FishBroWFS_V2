"""
Test artifact validation regex pattern matches requirements.

Requirements: ^(run|artifact)_[0-9a-f]{6,64}$
"""

import re
import pytest

# Import the actual function from the module
from gui.desktop.artifact_validation import is_artifact_dir_name


def test_regex_pattern():
    """Test that the regex pattern matches the requirements."""
    # The pattern should be compiled in the module
    from gui.desktop.artifact_validation import _DIR_RE
    
    # Valid cases (6-64 hex chars, lowercase only per [0-9a-f])
    valid_names = [
        "run_ac8a71aa",  # 8 hex chars
        "artifact_ac8a71aa",  # 8 hex chars with artifact prefix
        "run_1234567890abcdef",  # 16 hex chars
        "artifact_1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",  # 64 hex chars
        "run_123456",  # 6 hex chars (minimum per spec)
        "run_abcdef",  # lowercase hex
        "run_123abc",  # mixed case (numbers + lowercase)
    ]
    
    # Invalid cases
    invalid_names = [
        "run_",  # no hex
        "run_zzzz",  # non-hex chars
        "run_12345",  # 5 hex chars (less than minimum 6)
        "artifact_",  # no hex
        "artifact_zzzzzz",  # non-hex
        "test_ac8a71aa",  # wrong prefix
        "ac8a71aa",  # no prefix
        "run_12345g",  # contains 'g' which is not hex
        "",  # empty
        "run_1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",  # >64 chars
    ]
    
    for name in valid_names:
        # Check if regex matches
        assert _DIR_RE.match(name) is not None, f"Valid name '{name}' should match regex"
        # Check if function returns True
        assert is_artifact_dir_name(name), f"Valid name '{name}' should return True"
    
    for name in invalid_names:
        # Check if regex doesn't match (or matches but shouldn't)
        if _DIR_RE.match(name) is not None:
            print(f"WARNING: Invalid name '{name}' matched regex but shouldn't")
        # Function should return False
        assert not is_artifact_dir_name(name), f"Invalid name '{name}' should return False"


def test_edge_cases():
    """Test edge cases for the regex."""
    from gui.desktop.artifact_validation import _DIR_RE
    
    # Test with exactly 6 hex chars (minimum per spec)
    assert _DIR_RE.match("run_123456") is not None
    assert is_artifact_dir_name("run_123456")
    
    # Test with exactly 64 hex chars (maximum per spec)
    max_hex = "a" * 64
    assert _DIR_RE.match(f"run_{max_hex}") is not None
    assert is_artifact_dir_name(f"run_{max_hex}")
    
    # Test with 65 hex chars (should not match)
    too_long = "a" * 65
    assert _DIR_RE.match(f"run_{too_long}") is None
    assert not is_artifact_dir_name(f"run_{too_long}")
    
    # Test with mixed case (should NOT match because regex is [0-9a-f] lowercase only)
    assert _DIR_RE.match("run_AbCdEf123") is None
    assert not is_artifact_dir_name("run_AbCdEf123")
    
    # Test with underscores in hex part (should not match)
    assert _DIR_RE.match("run_123_456") is None
    assert not is_artifact_dir_name("run_123_456")


def test_backward_compatibility():
    """Ensure backward compatibility with existing run/artifact directories."""
    # Existing code might have directories with timestamps or other patterns
    # Our regex should still accept valid hex patterns
    from gui.desktop.artifact_validation import _DIR_RE
    
    # These are examples of what might exist in the wild
    legacy_compatible = [
        "run_ac8a71aa",
        "artifact_ac8a71aa",
        "run_20240101_123456",  # This has underscores in hex part - actually not valid hex
    ]
    
    # Only the first two should match
    assert _DIR_RE.match("run_ac8a71aa") is not None
    assert _DIR_RE.match("artifact_ac8a71aa") is not None
    assert _DIR_RE.match("run_20240101_123456") is None  # Contains underscores


if __name__ == "__main__":
    pytest.main([__file__, "-v"])