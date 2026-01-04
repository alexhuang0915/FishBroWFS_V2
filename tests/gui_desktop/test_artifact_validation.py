"""
Unit tests for artifact validation logic.
"""
import json
import tempfile
from pathlib import Path
import shutil

import pytest

# Import the validation function from control_station
# Since it's a method, we'll test the logic directly


def validate_artifact_dir(artifact_path: str) -> dict:
    """
    Reimplementation of validation logic from control_station.py
    for testing purposes.
    """
    if not artifact_path:
        return {"valid": False, "run_dir": "", "found_files": []}
    
    path = Path(artifact_path)
    if not path.exists():
        return {"valid": False, "run_dir": str(path), "found_files": []}
    
    # Check for at least ONE of these files
    required_patterns = ["metrics.json", "manifest.json", "trades.parquet"]
    found_files = []
    
    for pattern in required_patterns:
        # Check recursively
        for file_path in path.rglob(pattern):
            found_files.append(str(file_path.relative_to(path)))
    
    # Also check directly in the directory
    for pattern in required_patterns:
        if (path / pattern).exists():
            found_files.append(pattern)
    
    # Remove duplicates
    found_files = list(set(found_files))
    
    valid = len(found_files) > 0
    
    return {
        "valid": valid,
        "run_dir": str(path),
        "found_files": found_files
    }


def test_validate_artifact_dir_valid_with_metrics():
    """Test validation passes when metrics.json exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create metrics.json
        metrics = {"net_profit": 1000, "max_dd": 50}
        (tmp_path / "metrics.json").write_text(json.dumps(metrics))
        
        result = validate_artifact_dir(str(tmp_path))
        
        assert result["valid"] is True
        assert result["run_dir"] == str(tmp_path)
        assert "metrics.json" in result["found_files"]


def test_validate_artifact_dir_valid_with_manifest():
    """Test validation passes when manifest.json exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create manifest.json
        manifest = {"run_id": "test123", "created_at": "2026-01-01"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        
        result = validate_artifact_dir(str(tmp_path))
        
        assert result["valid"] is True
        assert "manifest.json" in result["found_files"]


def test_validate_artifact_dir_valid_with_trades():
    """Test validation passes when trades.parquet exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create empty trades.parquet file
        (tmp_path / "trades.parquet").write_bytes(b"parquet dummy data")
        
        result = validate_artifact_dir(str(tmp_path))
        
        assert result["valid"] is True
        assert "trades.parquet" in result["found_files"]


def test_validate_artifact_dir_valid_with_nested_files():
    """Test validation finds files in subdirectories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create nested structure
        nested_dir = tmp_path / "subdir" / "deep"
        nested_dir.mkdir(parents=True)
        
        # Create metrics.json in nested directory
        metrics = {"net_profit": 500}
        (nested_dir / "metrics.json").write_text(json.dumps(metrics))
        
        result = validate_artifact_dir(str(tmp_path))
        
        assert result["valid"] is True
        # Should find the nested file
        assert any("metrics.json" in f for f in result["found_files"])


def test_validate_artifact_dir_invalid_empty():
    """Test validation fails for empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = validate_artifact_dir(str(tmpdir))
        
        assert result["valid"] is False
        assert result["found_files"] == []


def test_validate_artifact_dir_invalid_wrong_files():
    """Test validation fails when only wrong files exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create wrong files
        (tmp_path / "config.yaml").write_text("config")
        (tmp_path / "log.txt").write_text("log")
        
        result = validate_artifact_dir(str(tmp_path))
        
        assert result["valid"] is False
        assert result["found_files"] == []


def test_validate_artifact_dir_nonexistent():
    """Test validation fails for non-existent path."""
    result = validate_artifact_dir("/nonexistent/path/12345")
    
    assert result["valid"] is False
    assert result["run_dir"] == "/nonexistent/path/12345"
    assert result["found_files"] == []


def test_validate_artifact_dir_empty_string():
    """Test validation fails for empty string."""
    result = validate_artifact_dir("")
    
    assert result["valid"] is False
    assert result["run_dir"] == ""
    assert result["found_files"] == []


def test_validate_artifact_dir_multiple_files():
    """Test validation passes and lists all found files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create multiple valid files
        (tmp_path / "metrics.json").write_text(json.dumps({"a": 1}))
        (tmp_path / "manifest.json").write_text(json.dumps({"b": 2}))
        
        result = validate_artifact_dir(str(tmp_path))
        
        assert result["valid"] is True
        assert len(result["found_files"]) == 2
        assert "metrics.json" in result["found_files"]
        assert "manifest.json" in result["found_files"]