#!/usr/bin/env python3
"""Test atomic write functions."""

import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, 'src')

from control.artifacts import write_json_atomic, write_text_atomic

def test_json_atomic():
    """Test atomic JSON write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir) / "test.json"
        data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        
        # Write atomically
        write_json_atomic(test_path, data)
        
        # Verify file exists
        assert test_path.exists()
        
        # Verify content
        import json
        with open(test_path, 'r') as f:
            loaded = json.load(f)
        assert loaded == data
        
        # Verify atomicity by checking temp file is gone
        temp_files = list(Path(tmpdir).glob("*.tmp*"))
        assert len(temp_files) == 0, f"Temporary files remain: {temp_files}"
        
        print("✓ JSON atomic write test passed")

def test_text_atomic():
    """Test atomic text write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir) / "test.txt"
        text = "Hello, world!\nLine 2\nLine 3"
        
        # Write atomically
        write_text_atomic(test_path, text)
        
        # Verify file exists
        assert test_path.exists()
        
        # Verify content
        with open(test_path, 'r') as f:
            loaded = f.read()
        assert loaded == text
        
        # Verify atomicity by checking temp file is gone
        temp_files = list(Path(tmpdir).glob("*.tmp*"))
        assert len(temp_files) == 0, f"Temporary files remain: {temp_files}"
        
        print("✓ Text atomic write test passed")

def test_error_handling():
    """Test error handling in atomic writes."""
    from control.artifacts import write_json_atomic, write_text_atomic
    import tempfile
    
    # Test with invalid path (directory)
    with tempfile.TemporaryDirectory() as tmpdir:
        dir_path = Path(tmpdir)
        
        # Should raise OSError when trying to write to a directory
        try:
            write_json_atomic(dir_path, {"test": "data"})
            assert False, "Should have raised OSError"
        except (OSError, IsADirectoryError):
            print("✓ Directory error handling works")
        
        # Test with non-serializable data
        import threading
        non_serializable = {"thread": threading.Lock()}  # Lock is not JSON serializable
        file_path = Path(tmpdir) / "bad.json"
        try:
            write_json_atomic(file_path, non_serializable)
            assert False, "Should have raised TypeError"
        except (TypeError, ValueError):
            print("✓ Non-serializable error handling works")

if __name__ == "__main__":
    print("Testing atomic write functions...")
    test_json_atomic()
    test_text_atomic()
    test_error_handling()
    print("\nAll tests passed!")