"""
Unit tests for artifact contract lock (Phase 15.1).

Tests verify:
1. Only artifact_* directories are considered promotable artifacts
2. Both manifest.json AND metrics.json are required (strict AND)
3. run_* and stage0_coarse-* directories are never considered artifacts
4. Artifact scanning selects latest valid artifact_*
"""

import json
import os
import tempfile
from pathlib import Path
import shutil
import time

import pytest

from src.gui.desktop.artifact_validation import (
    is_artifact_dir_name,
    validate_artifact_dir,
    find_latest_valid_artifact,
    validate_artifact_backward_compatible,
)


def test_is_artifact_dir_name():
    """Test canonical predicate for artifact directory names."""
    assert is_artifact_dir_name("artifact_12345") is True
    assert is_artifact_dir_name("artifact_20250101_120000") is True
    assert is_artifact_dir_name("artifact_S1_CME.MNQ") is True
    
    # Non-artifact prefixes must return False
    assert is_artifact_dir_name("run_12345") is False
    assert is_artifact_dir_name("stage0_coarse-12345") is False
    assert is_artifact_dir_name("debug_12345") is False
    assert is_artifact_dir_name("artifact") is False  # missing underscore
    assert is_artifact_dir_name("") is False
    assert is_artifact_dir_name("some_other_dir") is False


def test_validate_artifact_dir_strict():
    """Test strict validation requiring both manifest.json AND metrics.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create artifact directory
        artifact_dir = tmp_path / "artifact_test123"
        artifact_dir.mkdir()
        
        # Test 1: Empty directory (missing both files)
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is False
        assert result["reason"] == "missing_required_files"
        assert "manifest.json" in result.get("missing", [])
        assert "metrics.json" in result.get("missing", [])
        
        # Test 2: Only manifest.json
        (artifact_dir / "manifest.json").write_text(json.dumps({"run_id": "test"}))
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is False
        assert result["reason"] == "missing_required_files"
        assert "metrics.json" in result.get("missing", [])
        
        # Test 3: Only metrics.json
        (artifact_dir / "manifest.json").unlink()
        (artifact_dir / "metrics.json").write_text(json.dumps({"net_profit": 100}))
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is False
        assert result["reason"] == "missing_required_files"
        assert "manifest.json" in result.get("missing", [])
        
        # Test 4: Both files present (valid)
        (artifact_dir / "manifest.json").write_text(json.dumps({"run_id": "test"}))
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is True
        assert result["reason"] == "ok"
        
        # Test 5: Non-artifact prefix directory (should fail)
        run_dir = tmp_path / "run_12345"
        run_dir.mkdir()
        (run_dir / "manifest.json").write_text(json.dumps({}))
        (run_dir / "metrics.json").write_text(json.dumps({}))
        result = validate_artifact_dir(run_dir)
        assert result["ok"] is False
        assert result["reason"] == "not_artifact_prefix"


def test_find_latest_valid_artifact():
    """Test artifact scanning selects latest valid artifact_* directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create runs directory structure
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        
        # Create non-artifact directories (should be ignored)
        run_dir = runs_dir / "run_11111"
        run_dir.mkdir()
        (run_dir / "intent.json").write_text("{}")
        (run_dir / "derived.json").write_text("{}")
        
        stage0_dir = runs_dir / "stage0_coarse-22222"
        stage0_dir.mkdir()
        (stage0_dir / "debug.log").write_text("debug")
        
        # Create invalid artifact directory (missing metrics)
        artifact_invalid = runs_dir / "artifact_33333"
        artifact_invalid.mkdir()
        (artifact_invalid / "manifest.json").write_text(json.dumps({"run_id": "33333"}))
        # No metrics.json
        
        # Create valid artifact directory (older)
        artifact_old = runs_dir / "artifact_44444"
        artifact_old.mkdir()
        (artifact_old / "manifest.json").write_text(json.dumps({"run_id": "44444"}))
        (artifact_old / "metrics.json").write_text(json.dumps({"net_profit": 100}))
        # Make it older by modifying mtime
        old_time = time.time() - 3600  # 1 hour ago
        os.utime(artifact_old, (old_time, old_time))
        
        # Create valid artifact directory (newer)
        artifact_new = runs_dir / "artifact_55555"
        artifact_new.mkdir()
        (artifact_new / "manifest.json").write_text(json.dumps({"run_id": "55555"}))
        (artifact_new / "metrics.json").write_text(json.dumps({"net_profit": 200}))
        # This is newest (default current time)
        
        # Test scanning
        result = find_latest_valid_artifact(runs_dir)
        assert result["ok"] is True
        assert result["artifact_dir"] == str(artifact_new)
        
        # Verify validation result
        validation = result["validation"]
        assert validation["ok"] is True
        assert validation["reason"] == "ok"


def test_find_latest_valid_artifact_no_valid():
    """Test scanning when no valid artifact exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        
        # Only non-artifact directories
        run_dir = runs_dir / "run_11111"
        run_dir.mkdir()
        (run_dir / "intent.json").write_text("{}")
        
        # Invalid artifact (missing files)
        artifact_invalid = runs_dir / "artifact_22222"
        artifact_invalid.mkdir()
        # No files
        
        result = find_latest_valid_artifact(runs_dir)
        assert result["ok"] is False
        assert result["reason"] == "no_valid_artifact_found"
        
        # Non-existent directory
        result = find_latest_valid_artifact(Path("/nonexistent"))
        assert result["ok"] is False
        assert result["reason"] == "runs_dir_missing"


def test_artifact_selection_ignores_non_artifact():
    """Ensure run_* and stage0_coarse-* are never selected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        
        # Create run_* with both manifest and metrics (should still be ignored)
        run_dir = runs_dir / "run_99999"
        run_dir.mkdir()
        (run_dir / "manifest.json").write_text(json.dumps({"run_id": "run"}))
        (run_dir / "metrics.json").write_text(json.dumps({"net_profit": 999}))
        
        # Create stage0_coarse-* with both files
        stage0_dir = runs_dir / "stage0_coarse-88888"
        stage0_dir.mkdir()
        (stage0_dir / "manifest.json").write_text(json.dumps({"run_id": "stage0"}))
        (stage0_dir / "metrics.json").write_text(json.dumps({"net_profit": 888}))
        
        # No artifact_* directories
        result = find_latest_valid_artifact(runs_dir)
        assert result["ok"] is False
        assert result["reason"] == "no_valid_artifact_found"
        
        # Add a valid artifact_* (should be selected)
        artifact_dir = runs_dir / "artifact_77777"
        artifact_dir.mkdir()
        (artifact_dir / "manifest.json").write_text(json.dumps({"run_id": "artifact"}))
        (artifact_dir / "metrics.json").write_text(json.dumps({"net_profit": 777}))
        
        result = find_latest_valid_artifact(runs_dir)
        assert result["ok"] is True
        assert result["artifact_dir"] == str(artifact_dir)


def test_validate_artifact_backward_compatible():
    """Test backward-compatible validate_artifact method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Valid artifact directory
        artifact_dir = tmp_path / "artifact_test"
        artifact_dir.mkdir()
        (artifact_dir / "manifest.json").write_text(json.dumps({}))
        (artifact_dir / "metrics.json").write_text(json.dumps({}))
        
        result = validate_artifact_backward_compatible(str(artifact_dir))
        assert result["valid"] is True
        assert result["run_dir"] == str(artifact_dir)
        assert "manifest.json" in result["found_files"]
        assert "metrics.json" in result["found_files"]
        
        # Non-artifact directory (should be invalid)
        run_dir = tmp_path / "run_test"
        run_dir.mkdir()
        (run_dir / "manifest.json").write_text(json.dumps({}))
        (run_dir / "metrics.json").write_text(json.dumps({}))
        
        result = validate_artifact_backward_compatible(str(run_dir))
        assert result["valid"] is False
        assert result["found_files"] == []  # No files counted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])