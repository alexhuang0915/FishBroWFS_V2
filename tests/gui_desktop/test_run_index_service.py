"""
Test run index service for listing and picking runs.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest

from src.gui.desktop.services.run_index_service import (
    is_artifact_dir_name,
    list_runs,
    pick_last_run,
    get_run_summary,
    RunRef,
)


def test_is_artifact_dir_name():
    """Test the artifact directory name validator."""
    # Valid names
    assert is_artifact_dir_name("run_ac8a71aa")
    assert is_artifact_dir_name("artifact_ac8a71aa")
    assert is_artifact_dir_name("run_123456")  # 6 hex chars
    assert is_artifact_dir_name("run_1234567890abcdef")  # 16 hex chars
    
    # Invalid names
    assert not is_artifact_dir_name("run_")  # no hex
    assert not is_artifact_dir_name("run_zzzz")  # non-hex
    assert not is_artifact_dir_name("test_ac8a71aa")  # wrong prefix
    assert not is_artifact_dir_name("ac8a71aa")  # no prefix
    assert not is_artifact_dir_name("")  # empty


def test_list_runs_empty(tmp_path):
    """Test listing runs when directory is empty."""
    season = "2026Q1"
    outputs_root = tmp_path
    
    runs = list_runs(season, outputs_root)
    assert runs == []  # No runs directory exists


def test_list_runs_with_meta_json(tmp_path):
    """Test listing runs with meta.json containing finished_at."""
    season = "2026Q1"
    outputs_root = tmp_path
    
    # Create runs directory structure
    runs_dir = outputs_root / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Create a run directory with meta.json
    run1_dir = runs_dir / "run_ac8a71aa"
    run1_dir.mkdir()
    
    # Create meta.json with finished_at
    meta_data = {
        "finished_at": "2026-01-03T12:34:56Z",
        "created_at": "2026-01-03T12:00:00Z"
    }
    (run1_dir / "meta.json").write_text(json.dumps(meta_data))
    
    # Create another run directory without meta.json
    run2_dir = runs_dir / "artifact_123456"
    run2_dir.mkdir()
    
    # List runs
    runs = list_runs(season, outputs_root)
    
    assert len(runs) == 2
    assert isinstance(runs[0], RunRef)
    assert isinstance(runs[1], RunRef)
    
    # Check names
    run_names = {r.name for r in runs}
    assert run_names == {"run_ac8a71aa", "artifact_123456"}
    
    # The run with meta.json should have finished_at
    run_with_meta = next(r for r in runs if r.name == "run_ac8a71aa")
    assert run_with_meta.finished_at is not None
    # Should be approx timestamp of 2026-01-03T12:34:56Z
    expected_timestamp = datetime(2026, 1, 3, 12, 34, 56, tzinfo=timezone.utc).timestamp()
    assert abs(run_with_meta.finished_at - expected_timestamp) < 1
    
    # Run without meta.json should have None finished_at
    run_without_meta = next(r for r in runs if r.name == "artifact_123456")
    assert run_without_meta.finished_at is None


def test_list_runs_skips_invalid_dirs(tmp_path):
    """Test that invalid directories are skipped."""
    season = "2026Q1"
    outputs_root = tmp_path
    
    runs_dir = outputs_root / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Create valid run directory
    valid_dir = runs_dir / "run_ac8a71aa"
    valid_dir.mkdir()
    
    # Create invalid directories (should be skipped)
    invalid_dir1 = runs_dir / "invalid_name"
    invalid_dir1.mkdir()
    
    invalid_dir2 = runs_dir / "test_123456"
    invalid_dir2.mkdir()
    
    # Create a file (not directory)
    (runs_dir / "some_file.txt").write_text("not a directory")
    
    runs = list_runs(season, outputs_root)
    assert len(runs) == 1
    assert runs[0].name == "run_ac8a71aa"


def test_list_runs_sorting(tmp_path):
    """Test that runs are sorted newest-first."""
    season = "2026Q1"
    outputs_root = tmp_path
    
    runs_dir = outputs_root / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Create 3 runs with different mtimes
    run1_dir = runs_dir / "run_111111"
    run1_dir.mkdir()
    
    run2_dir = runs_dir / "run_222222"
    run2_dir.mkdir()
    
    run3_dir = runs_dir / "run_333333"
    run3_dir.mkdir()
    
    # Manually set mtimes using os.utime (newest first: run3, run1, run2)
    import time
    import os
    now = time.time()
    os.utime(run1_dir, (now - 100, now - 100))  # oldest
    os.utime(run2_dir, (now - 50, now - 50))    # middle
    os.utime(run3_dir, (now, now))              # newest
    
    runs = list_runs(season, outputs_root)
    assert len(runs) == 3
    # Should be sorted by mtime descending (newest first)
    assert runs[0].name == "run_333333"  # newest
    assert runs[1].name == "run_222222"  # middle
    assert runs[2].name == "run_111111"  # oldest


def test_pick_last_run(tmp_path):
    """Test picking the last (most recent) run."""
    season = "2026Q1"
    outputs_root = tmp_path
    
    runs_dir = outputs_root / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Create runs
    run1_dir = runs_dir / "run_111111"
    run1_dir.mkdir()
    
    run2_dir = runs_dir / "run_222222"
    run2_dir.mkdir()
    
    # Set mtimes so run2 is newer
    import time
    import os
    now = time.time()
    os.utime(run1_dir, (now - 100, now - 100))
    os.utime(run2_dir, (now, now))
    
    last_run = pick_last_run(season, outputs_root)
    assert last_run is not None
    assert last_run.name == "run_222222"  # newest


def test_pick_last_run_empty(tmp_path):
    """Test picking last run when no runs exist."""
    season = "2026Q1"
    outputs_root = tmp_path
    
    last_run = pick_last_run(season, outputs_root)
    assert last_run is None


def test_get_run_summary(tmp_path):
    """Test getting run summary from directory."""
    run_dir = tmp_path / "run_test123"
    run_dir.mkdir()
    
    # Create a summary.json file
    summary_data = {
        "net_profit": 1000.0,
        "max_dd": -500.0,
        "trades": 42
    }
    (run_dir / "summary.json").write_text(json.dumps(summary_data))
    
    summary, reason = get_run_summary(run_dir)
    assert summary is not None
    assert "net_profit" in summary
    assert summary["net_profit"] == 1000.0
    assert "Loaded from summary.json" in reason


def test_get_run_summary_no_files(tmp_path):
    """Test getting run summary when no summary files exist."""
    run_dir = tmp_path / "run_test123"
    run_dir.mkdir()
    
    summary, reason = get_run_summary(run_dir)
    assert summary is None
    assert "No summary files found" in reason


def test_get_run_summary_metrics_json(tmp_path):
    """Test getting run summary from metrics.json."""
    run_dir = tmp_path / "run_test123"
    run_dir.mkdir()
    
    # Create metrics.json instead of summary.json
    metrics_data = {
        "sharpe": 1.5,
        "profit_factor": 2.0,
        "win_rate": 0.6
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_data))
    
    summary, reason = get_run_summary(run_dir)
    assert summary is not None
    assert "sharpe" in summary
    assert summary["sharpe"] == 1.5
    assert "Loaded from metrics.json" in reason


def test_get_run_summary_corrupted_json(tmp_path):
    """Test getting run summary with corrupted JSON file."""
    run_dir = tmp_path / "run_test123"
    run_dir.mkdir()
    
    # Create corrupted JSON file
    (run_dir / "summary.json").write_text("{invalid json")
    
    # Also create a valid metrics.json
    metrics_data = {"test": 1}
    (run_dir / "metrics.json").write_text(json.dumps(metrics_data))
    
    summary, reason = get_run_summary(run_dir)
    # Should fall back to metrics.json
    assert summary is not None
    assert "test" in summary
    assert summary["test"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])