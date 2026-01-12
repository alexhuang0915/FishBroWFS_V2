#!/usr/bin/env python3
"""Test artifact filename validation after X-5 fix."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

# Import the validation functions
from control.api import _validate_artifact_filename_or_403 as validate_api
from control.portfolio.api_v1 import _validate_artifact_filename_or_403 as validate_portfolio

def test_validation():
    """Test various filename patterns."""
    test_cases = [
        # (filename, should_pass, description)
        ("results.json", True, "Simple filename"),
        ("data/results.json", True, "Relative path with slash"),
        ("nested/path/to/file.csv", True, "Deep nested path"),
        ("../evil.txt", False, "Path traversal attempt"),
        ("../../etc/passwd", False, "Multiple path traversal"),
        ("./relative.txt", True, "Current directory relative"),
        ("/absolute/path", False, "Absolute path"),
        ("", False, "Empty filename"),
        ("valid_name_with_underscores.csv", True, "Valid with underscores"),
        ("spaces in name.txt", True, "Spaces allowed"),
        ("special!@#$%^&*().txt", True, "Special characters"),
        ("..hidden.txt", True, "Leading dots but not traversal"),
        (".../test.txt", False, "Three dots with slash is traversal"),
    ]
    
    print("Testing API validation function:")
    print("-" * 80)
    for filename, should_pass, description in test_cases:
        try:
            validate_api(filename)
            passed = True
        except Exception as e:
            passed = False
            error_msg = str(e)
        
        status = "✓ PASS" if passed == should_pass else "✗ FAIL"
        expected = "should pass" if should_pass else "should fail"
        actual = "passed" if passed else f"failed ({error_msg})"
        print(f"{status}: {filename!r:30} - {description}")
        print(f"      Expected: {expected}, Actual: {actual}")
    
    print("\nTesting Portfolio API validation function:")
    print("-" * 80)
    for filename, should_pass, description in test_cases:
        try:
            validate_portfolio(filename)
            passed = True
        except Exception as e:
            passed = False
            error_msg = str(e)
        
        status = "✓ PASS" if passed == should_pass else "✗ FAIL"
        expected = "should pass" if should_pass else "should fail"
        actual = "passed" if passed else f"failed ({error_msg})"
        print(f"{status}: {filename!r:30} - {description}")
        print(f"      Expected: {expected}, Actual: {actual}")
    
    # Test that both validators produce same results
    print("\nComparing API and Portfolio validators:")
    mismatches = []
    for filename, _, _ in test_cases:
        try:
            validate_api(filename)
            api_ok = True
        except:
            api_ok = False
        
        try:
            validate_portfolio(filename)
            portfolio_ok = True
        except:
            portfolio_ok = False
        
        if api_ok != portfolio_ok:
            mismatches.append((filename, api_ok, portfolio_ok))
    
    if mismatches:
        print("✗ MISMATCHES FOUND:")
        for filename, api_ok, portfolio_ok in mismatches:
            print(f"  {filename!r}: API={api_ok}, Portfolio={portfolio_ok}")
    else:
        print("✓ Both validators produce identical results")

if __name__ == "__main__":
    test_validation()