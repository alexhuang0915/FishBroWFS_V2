#!/usr/bin/env python3
"""Simple test for artifact filename validation after X-5 fix."""

import sys
sys.path.insert(0, 'src')

# Import the validation functions
from control.api import _validate_artifact_filename_or_403 as validate_api
from control.portfolio.api_v1 import _validate_artifact_filename_or_403 as validate_portfolio

def test_basic():
    """Test basic validation cases."""
    print("Testing API validation function:")
    
    # Test cases that should pass
    valid_cases = [
        "results.json",
        "data/results.json",
        "nested/path/to/file.csv",
        "./relative.txt",
        "valid_name_with_underscores.csv",
        "spaces in name.txt",
        "special!@#$%^&*().txt",
        "..hidden.txt",  # Leading dots but not traversal
    ]
    
    for filename in valid_cases:
        try:
            validate_api(filename)
            print(f"  ✓ {filename!r} passed (expected)")
        except Exception as e:
            print(f"  ✗ {filename!r} failed unexpectedly: {e}")
    
    # Test cases that should fail
    invalid_cases = [
        ("", "empty filename"),
        (".", "current directory"),
        ("..", "parent directory"),
        ("../evil.txt", "path traversal"),
        ("../../etc/passwd", "multiple path traversal"),
        ("/absolute/path", "absolute path"),
        (".../test.txt", "three dots with slash"),
    ]
    
    for filename, description in invalid_cases:
        try:
            validate_api(filename)
            print(f"  ✗ {filename!r} passed unexpectedly (should fail: {description})")
        except Exception as e:
            print(f"  ✓ {filename!r} failed as expected: {description}")
    
    print("\nTesting Portfolio API validation function:")
    
    # Test a few cases to ensure consistency
    test_cases = ["results.json", "data/file.csv", "../bad.txt"]
    for filename in test_cases:
        try:
            validate_api(filename)
            api_result = "passed"
        except Exception:
            api_result = "failed"
        
        try:
            validate_portfolio(filename)
            portfolio_result = "passed"
        except Exception:
            portfolio_result = "failed"
        
        if api_result == portfolio_result:
            print(f"  ✓ {filename!r}: both {api_result}")
        else:
            print(f"  ✗ {filename!r}: API {api_result}, Portfolio {portfolio_result}")

if __name__ == "__main__":
    test_basic()