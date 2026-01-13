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

from gui.desktop.artifact_validation import (
    is_artifact_dir_name,
    validate_artifact_dir,
    find_latest_valid_artifact,
    validate_artifact_backward_compatible,
)


def test_is_artifact_dir_name():
    """Test canonical predicate for artifact directory names."""
    # Valid hex patterns (6-64 hex chars)
    assert is_artifact_dir_name("artifact_123456") is True  # 6 hex chars
    assert is_artifact_dir_name("artifact_abcdef") is True  # 6 hex chars
    assert is_artifact_dir_name("artifact_1234567890abcdef") is True  # 16 hex chars
    assert is_artifact_dir_name("run_123456") is True  # run_ with 6 hex chars
    
    # Invalid patterns
    assert is_artifact_dir_name("artifact_12345") is False  # only 5 hex chars
    assert is_artifact_dir_name("artifact_20250101_120000") is False  # timestamp with underscore
    assert is_artifact_dir_name("artifact_S1_CME.MNQ") is False  # strategy and market
    assert is_artifact_dir_name("stage0_coarse-12345") is False
    assert is_artifact_dir_name("debug_12345") is False
    assert is_artifact_dir_name("artifact") is False  # missing underscore
    assert is_artifact_dir_name("") is False
    assert is_artifact_dir_name("some_other_dir") is False


def test_validate_artifact_dir_strict():
    """Test strict validation requiring all Phase 18 files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create artifact directory (6+ hex chars) - use valid hex only
        artifact_dir = tmp_path / "artifact_123456"
        artifact_dir.mkdir()
        
        # Test 1: Empty directory (missing all files)
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is False
        assert result["reason"] == "missing_required_files"
        missing = result.get("missing", [])
        assert "manifest.json" in missing
        assert "metrics.json" in missing
        assert "trades.parquet" in missing
        assert "equity.parquet" in missing
        assert "report.json" in missing
        
        # Test 2: Only some files
        (artifact_dir / "manifest.json").write_text(json.dumps({"run_id": "test"}))
        (artifact_dir / "metrics.json").write_text(json.dumps({"net_profit": 100}))
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is False
        assert result["reason"] == "missing_required_files"
        missing = result.get("missing", [])
        assert "trades.parquet" in missing
        assert "equity.parquet" in missing
        assert "report.json" in missing
        
        # Test 3: Add trades and equity but missing report
        (artifact_dir / "trades.parquet").write_bytes(b"parquet dummy")
        (artifact_dir / "equity.parquet").write_bytes(b"parquet dummy")
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is False
        assert result["reason"] == "missing_required_files"
        missing = result.get("missing", [])
        assert "report.json" in missing
        
        # Test 4: All files present (valid)
        (artifact_dir / "report.json").write_text(json.dumps({"metrics": {}}))
        result = validate_artifact_dir(artifact_dir)
        assert result["ok"] is True
        assert result["reason"] == "ok"
        
        # Test 5: Non-artifact prefix directory (should fail even with all files)
        debug_dir = tmp_path / "debug_123456"
        debug_dir.mkdir()
        (debug_dir / "manifest.json").write_text(json.dumps({}))
        (debug_dir / "metrics.json").write_text(json.dumps({}))
        (debug_dir / "trades.parquet").write_bytes(b"dummy")
        (debug_dir / "equity.parquet").write_bytes(b"dummy")
        (debug_dir / "report.json").write_text(json.dumps({}))
        result = validate_artifact_dir(debug_dir)
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
        run_dir = runs_dir / "run_111111"
        run_dir.mkdir()
        (run_dir / "intent.json").write_text("{}")
        (run_dir / "derived.json").write_text("{}")
        
        stage0_dir = runs_dir / "stage0_coarse-222222"
        stage0_dir.mkdir()
        (stage0_dir / "debug.log").write_text("debug")
        
        # Create invalid artifact directory (missing metrics)
        artifact_invalid = runs_dir / "artifact_333333"
        artifact_invalid.mkdir()
        (artifact_invalid / "manifest.json").write_text(json.dumps({"run_id": "333333"}))
        # No metrics.json
        
        # Create valid artifact directory (older)
        artifact_old = runs_dir / "artifact_444444"
        artifact_old.mkdir()
        (artifact_old / "manifest.json").write_text(json.dumps({"run_id": "444444"}))
        (artifact_old / "metrics.json").write_text(json.dumps({"net_profit": 100}))
        (artifact_old / "trades.parquet").write_bytes(b"parquet dummy")
        (artifact_old / "equity.parquet").write_bytes(b"parquet dummy")
        (artifact_old / "report.json").write_text(json.dumps({"metrics": {}}))
        # Make it older by modifying mtime
        old_time = time.time() - 3600  # 1 hour ago
        os.utime(artifact_old, (old_time, old_time))
        
        # Create valid artifact directory (newer)
        artifact_new = runs_dir / "artifact_555555"
        artifact_new.mkdir()
        (artifact_new / "manifest.json").write_text(json.dumps({"run_id": "555555"}))
        (artifact_new / "metrics.json").write_text(json.dumps({"net_profit": 200}))
        (artifact_new / "trades.parquet").write_bytes(b"parquet dummy")
        (artifact_new / "equity.parquet").write_bytes(b"parquet dummy")
        (artifact_new / "report.json").write_text(json.dumps({"metrics": {}}))
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
        run_dir = runs_dir / "run_111111"
        run_dir.mkdir()
        (run_dir / "intent.json").write_text("{}")
        
        # Invalid artifact (missing files)
        artifact_invalid = runs_dir / "artifact_222222"
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
    """Ensure stage0_coarse-* is never selected; run_* is considered but may be invalid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        
        # Create run_* with both manifest and metrics but missing required Phase 18 files (invalid)
        run_dir = runs_dir / "run_999999"
        run_dir.mkdir()
        (run_dir / "manifest.json").write_text(json.dumps({"run_id": "run"}))
        (run_dir / "metrics.json").write_text(json.dumps({"net_profit": 999}))
        # Missing trades.parquet, equity.parquet, report.json
        
        # Create stage0_coarse-* with both files (should be ignored entirely)
        stage0_dir = runs_dir / "stage0_coarse-888888"
        stage0_dir.mkdir()
        (stage0_dir / "manifest.json").write_text(json.dumps({"run_id": "stage0"}))
        (stage0_dir / "metrics.json").write_text(json.dumps({"net_profit": 888}))
        
        # No valid artifact_* directories
        result = find_latest_valid_artifact(runs_dir)
        assert result["ok"] is False
        assert result["reason"] == "no_valid_artifact_found"
        
        # Add a valid artifact_* (should be selected)
        artifact_dir = runs_dir / "artifact_777777"
        artifact_dir.mkdir()
        (artifact_dir / "manifest.json").write_text(json.dumps({"run_id": "artifact"}))
        (artifact_dir / "metrics.json").write_text(json.dumps({"net_profit": 777}))
        (artifact_dir / "trades.parquet").write_bytes(b"parquet dummy")
        (artifact_dir / "equity.parquet").write_bytes(b"parquet dummy")
        (artifact_dir / "report.json").write_text(json.dumps({"metrics": {}}))
        
        result = find_latest_valid_artifact(runs_dir)
        assert result["ok"] is True
        assert result["artifact_dir"] == str(artifact_dir)


def test_validate_artifact_backward_compatible():
    """Test backward-compatible validate_artifact method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Valid artifact directory (6+ hex chars) - use valid hex only
        artifact_dir = tmp_path / "artifact_123456"
        artifact_dir.mkdir()
        (artifact_dir / "manifest.json").write_text(json.dumps({}))
        (artifact_dir / "metrics.json").write_text(json.dumps({}))
        
        result = validate_artifact_backward_compatible(str(artifact_dir))
        assert result["valid"] is True
        assert result["run_dir"] == str(artifact_dir)
        assert "manifest.json" in result["found_files"]
        assert "metrics.json" in result["found_files"]
        
        # Non-artifact directory (should be invalid)
        debug_dir = tmp_path / "debug_123456"
        debug_dir.mkdir()
        (debug_dir / "manifest.json").write_text(json.dumps({}))
        (debug_dir / "metrics.json").write_text(json.dumps({}))
        
        result = validate_artifact_backward_compatible(str(debug_dir))
        assert result["valid"] is False
        assert result["found_files"] == []  # No files counted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])