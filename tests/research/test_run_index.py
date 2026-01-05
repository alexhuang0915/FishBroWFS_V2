"""
Tests for the robust run index resolver.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from research.run_index import (
    RunSummary,
    list_runs,
    find_best_run,
    find_run_by_id,
    get_run_diagnostics,
)


def test_run_index_list_runs_handles_mixed_dirs():
    """Test that list_runs() ignores artifact_* directories (run_* only)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        runs_dir = outputs_root / "seasons" / season / "runs"
        runs_dir.mkdir(parents=True)
        
        # Create a canonical run_* directory
        run_dir1 = runs_dir / "run_abc123"
        run_dir1.mkdir()
        (run_dir1 / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_abc123",
            "season": season,
            "status": "COMPLETED",
            "created_at": "2026-01-03T10:00:00Z",
            "intent": {
                "strategy_id": "S1",
                "dataset_id": "CME.MNQ",
                "timeframe": "60m",
            }
        }))
        (run_dir1 / "manifest.json").write_text(json.dumps({
            "run_id": "run_abc123",
            "season": season,
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": 60,
            "created_at": "2026-01-03T10:00:00Z",
            "git_sha": "test",
        }))
        (run_dir1 / "metrics.json").write_text(json.dumps({
            "net_profit": 1000.0,
            "max_dd": -500.0,
            "trades": 50,
            "created_at": "2026-01-03T10:00:00Z",
            "stage_name": "research",
        }))
        
        # Create a legacy artifact_* directory (should be ignored)
        artifact_dir = runs_dir / "artifact_S1-20260103T101142Z-3ed66323"
        artifact_dir.mkdir()
        (artifact_dir / "manifest.json").write_text(json.dumps({
            "run_id": "artifact_S1-20260103T101142Z-3ed66323",
            "season": season,
            "dataset_id": "CBOT.ZN",
            "strategy_id": "S1",
            "timeframe": 60,
            "created_at": "2026-01-03T10:11:42Z",
            "git_sha": "test",
        }))
        (artifact_dir / "metrics.json").write_text(json.dumps({
            "net_profit": 500.0,
            "max_dd": -200.0,
            "trades": 30,
            "created_at": "2026-01-03T10:11:42Z",
            "stage_name": "research",
        }))
        
        # Create a RUNNING run
        run_dir2 = runs_dir / "run_def456"
        run_dir2.mkdir()
        (run_dir2 / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_def456",
            "season": season,
            "status": "RUNNING",
            "created_at": "2026-01-03T11:00:00Z",
        }))
        
        # List runs
        runs = list_runs(outputs_root, season)
        
        # Should find only the two run_* directories (artifact ignored)
        assert len(runs) == 2
        
        # Should be sorted newest first (run_dir2 is newest)
        assert runs[0].run_id == "run_def456"
        assert runs[0].status == "RUNNING"
        
        # Check canonical run
        run_abc = next(r for r in runs if r.run_id == "run_abc123")
        assert run_abc.status == "COMPLETED"
        assert run_abc.dataset_id == "CME.MNQ"
        assert run_abc.strategy_id == "S1"
        assert run_abc.timeframe == "60"
        
        # Ensure no artifact appears in results
        artifact_runs = [r for r in runs if "artifact_" in r.run_id]
        assert len(artifact_runs) == 0


def test_find_best_run_prefers_completed_and_matches_intent():
    """Test that find_best_run prefers completed runs and matches intent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        runs_dir = outputs_root / "seasons" / season / "runs"
        runs_dir.mkdir(parents=True)
        
        # Create a completed run with wrong dataset
        wrong_run = runs_dir / "run_wrong"
        wrong_run.mkdir()
        (wrong_run / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_wrong",
            "season": season,
            "status": "COMPLETED",
            "created_at": "2026-01-03T09:00:00Z",
        }))
        (wrong_run / "manifest.json").write_text(json.dumps({
            "run_id": "run_wrong",
            "season": season,
            "dataset_id": "CBOT.ZN",  # Wrong dataset
            "strategy_id": "S1",
            "timeframe": 60,
            "created_at": "2026-01-03T09:00:00Z",
            "git_sha": "test",
        }))
        (wrong_run / "metrics.json").write_text(json.dumps({
            "net_profit": 100.0,
            "max_dd": -50.0,
            "trades": 10,
            "created_at": "2026-01-03T09:00:00Z",
            "stage_name": "research",
        }))
        
        # Create a completed run with correct dataset/tf/strategy (older)
        correct_run_old = runs_dir / "run_correct_old"
        correct_run_old.mkdir()
        (correct_run_old / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_correct_old",
            "season": season,
            "status": "COMPLETED",
            "created_at": "2026-01-03T10:00:00Z",
        }))
        (correct_run_old / "manifest.json").write_text(json.dumps({
            "run_id": "run_correct_old",
            "season": season,
            "dataset_id": "CME.MNQ",  # Correct dataset
            "strategy_id": "S1",      # Correct strategy
            "timeframe": 60,          # Correct timeframe
            "created_at": "2026-01-03T10:00:00Z",
            "git_sha": "test",
        }))
        (correct_run_old / "metrics.json").write_text(json.dumps({
            "net_profit": 200.0,
            "max_dd": -100.0,
            "trades": 20,
            "created_at": "2026-01-03T10:00:00Z",
            "stage_name": "research",
        }))
        
        # Create a completed run with correct dataset/tf/strategy (newer)
        correct_run_new = runs_dir / "run_correct_new"
        correct_run_new.mkdir()
        (correct_run_new / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_correct_new",
            "season": season,
            "status": "COMPLETED",
            "created_at": "2026-01-03T11:00:00Z",  # Newer
        }))
        (correct_run_new / "manifest.json").write_text(json.dumps({
            "run_id": "run_correct_new",
            "season": season,
            "dataset_id": "CME.MNQ",  # Correct dataset
            "strategy_id": "S1",      # Correct strategy
            "timeframe": 60,          # Correct timeframe
            "created_at": "2026-01-03T11:00:00Z",
            "git_sha": "test",
        }))
        (correct_run_new / "metrics.json").write_text(json.dumps({
            "net_profit": 300.0,
            "max_dd": -150.0,
            "trades": 30,
            "created_at": "2026-01-03T11:00:00Z",
            "stage_name": "research",
        }))
        
        # Create a RUNNING run with correct dataset/tf/strategy
        running_run = runs_dir / "run_running"
        running_run.mkdir()
        (running_run / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_running",
            "season": season,
            "status": "RUNNING",
            "created_at": "2026-01-03T12:00:00Z",  # Newest
        }))
        (running_run / "manifest.json").write_text(json.dumps({
            "run_id": "run_running",
            "season": season,
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": 60,
            "created_at": "2026-01-03T12:00:00Z",
            "git_sha": "test",
        }))
        
        # Find best run for S1/CME.MNQ/60m
        best_run = find_best_run(
            outputs_root=outputs_root,
            season=season,
            strategy_id="S1",
            dataset_id="CME.MNQ",
            timeframe="60m",
        )
        
        # Should pick the newest COMPLETED run (run_correct_new), not RUNNING
        assert best_run is not None
        assert best_run.run_id == "run_correct_new"
        assert best_run.status == "COMPLETED"
        
        # Test with created_after filter
        best_run_filtered = find_best_run(
            outputs_root=outputs_root,
            season=season,
            strategy_id="S1",
            dataset_id="CME.MNQ",
            timeframe="60m",
            created_after_iso="2026-01-03T10:30:00Z",  # After old, before new
        )
        
        # Should pick run_correct_new (created at 11:00, after filter)
        assert best_run_filtered is not None
        assert best_run_filtered.run_id == "run_correct_new"
        
        # Test with created_after that excludes both completed runs
        best_run_none = find_best_run(
            outputs_root=outputs_root,
            season=season,
            strategy_id="S1",
            dataset_id="CME.MNQ",
            timeframe="60m",
            created_after_iso="2026-01-03T11:30:00Z",  # After both completed
        )
        
        # Should return the RUNNING run (for live view)
        assert best_run_none is not None
        assert best_run_none.run_id == "run_running"
        assert best_run_none.status == "RUNNING"


def test_find_best_run_created_after_filters_out_old():
    """Test that created_after_iso filters out old runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        runs_dir = outputs_root / "seasons" / season / "runs"
        runs_dir.mkdir(parents=True)
        
        # Create old completed run
        old_run = runs_dir / "run_old"
        old_run.mkdir()
        (old_run / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_old",
            "season": season,
            "status": "COMPLETED",
            "created_at": "2026-01-03T09:00:00Z",
        }))
        (old_run / "manifest.json").write_text(json.dumps({
            "run_id": "run_old",
            "season": season,
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": 60,
            "created_at": "2026-01-03T09:00:00Z",
            "git_sha": "test",
        }))
        (old_run / "metrics.json").write_text(json.dumps({
            "net_profit": 100.0,
            "max_dd": -50.0,
            "trades": 10,
            "created_at": "2026-01-03T09:00:00Z",
            "stage_name": "research",
        }))
        
        # Create new completed run
        new_run = runs_dir / "run_new"
        new_run.mkdir()
        (new_run / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_new",
            "season": season,
            "status": "COMPLETED",
            "created_at": "2026-01-03T11:00:00Z",
        }))
        (new_run / "manifest.json").write_text(json.dumps({
            "run_id": "run_new",
            "season": season,
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": 60,
            "created_at": "2026-01-03T11:00:00Z",
            "git_sha": "test",
        }))
        (new_run / "metrics.json").write_text(json.dumps({
            "net_profit": 200.0,
            "max_dd": -100.0,
            "trades": 20,
            "created_at": "2026-01-03T11:00:00Z",
            "stage_name": "research",
        }))
        
        # Find with created_after set to between old and new
        best_run = find_best_run(
            outputs_root=outputs_root,
            season=season,
            strategy_id="S1",
            dataset_id="CME.MNQ",
            timeframe="60m",
            created_after_iso="2026-01-03T10:00:00Z",
        )
        
        # Should pick new run only
        assert best_run is not None
        assert best_run.run_id == "run_new"
        
        # Find without filter should pick newest (which is new_run)
        best_run_no_filter = find_best_run(
            outputs_root=outputs_root,
            season=season,
            strategy_id="S1",
            dataset_id="CME.MNQ",
            timeframe="60m",
        )
        
        assert best_run_no_filter is not None
        assert best_run_no_filter.run_id == "run_new"


def test_find_run_by_id():
    """Test finding a specific run by ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        runs_dir = outputs_root / "seasons" / season / "runs"
        runs_dir.mkdir(parents=True)
        
        # Create a run
        run_dir = runs_dir / "run_test123"
        run_dir.mkdir()
        (run_dir / "run_record.json").write_text(json.dumps({
            "version": "1.0",
            "run_id": "run_test123",
            "season": season,
            "status": "COMPLETED",
            "created_at": "2026-01-03T10:00:00Z",
        }))
        (run_dir / "manifest.json").write_text(json.dumps({
            "run_id": "run_test123",
            "season": season,
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": 60,
            "created_at": "2026-01-03T10:00:00Z",
            "git_sha": "test",
        }))
        
        # Find by ID
        run = find_run_by_id(outputs_root, season, "run_test123")
        
        assert run is not None
        assert run.run_id == "run_test123"
        assert run.status == "COMPLETED"
        assert run.dataset_id == "CME.MNQ"
        
        # Non-existent run
        run_none = find_run_by_id(outputs_root, season, "nonexistent")
        assert run_none is None


def test_get_run_diagnostics():
    """Test diagnostic information for debugging."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        runs_dir = outputs_root / "seasons" / season / "runs"
        runs_dir.mkdir(parents=True)
        
        # Create a few runs with different statuses
        for i, (run_id, status, dataset) in enumerate([
            ("run_1", "COMPLETED", "CME.MNQ"),
            ("run_2", "RUNNING", "CME.MNQ"),
            ("run_3", "COMPLETED", "CBOT.ZN"),
        ]):
            run_dir = runs_dir / run_id
            run_dir.mkdir()
            (run_dir / "run_record.json").write_text(json.dumps({
                "version": "1.0",
                "run_id": run_id,
                "season": season,
                "status": status,
                "created_at": f"2026-01-03T10:00:0{i}Z",
            }))
            (run_dir / "manifest.json").write_text(json.dumps({
                "run_id": run_id,
                "season": season,
                "dataset_id": dataset,
                "strategy_id": "S1",
                "timeframe": 60,
                "created_at": f"2026-01-03T10:00:0{i}Z",
                "git_sha": "test",
            }))
            if status == "COMPLETED":
                (run_dir / "metrics.json").write_text(json.dumps({
                    "net_profit": 100.0 * (i + 1),
                    "max_dd": -50.0,
                    "trades": 10,
                    "created_at": f"2026-01-03T10:00:0{i}Z",
                    "stage_name": "research",
                }))
        
        # Get diagnostics for S1/CME.MNQ/60m
        diag = get_run_diagnostics(
            outputs_root=outputs_root,
            season=season,
            strategy_id="S1",
            dataset_id="CME.MNQ",
            timeframe="60m",
        )
        
        assert diag["total_runs"] == 3
        assert diag["status_counts"] == {"COMPLETED": 2, "RUNNING": 1}
        assert diag["matching_runs"] == 2  # run_1 and run_2 match CME.MNQ
        assert len(diag["newest_runs"]) == 3  # All runs
        assert diag["search_params"]["strategy_id"] == "S1"
        assert diag["search_params"]["dataset_id"] == "CME.MNQ"