"""
Tests for the canonical run writer.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from research.run_writer import (
    ensure_run_dir,
    write_run_manifest,
    write_run_metrics,
    update_run_record_status,
    create_canonical_run,
    complete_run,
)


def test_ensure_run_dir():
    """Test that run directory is created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        run_id = "run_test123"
        
        run_dir = ensure_run_dir(outputs_root, season, run_id)
        
        assert run_dir.exists()
        assert run_dir == outputs_root / "seasons" / season / "runs" / run_id
        
        # Calling again should not fail
        run_dir2 = ensure_run_dir(outputs_root, season, run_id)
        assert run_dir2 == run_dir


def test_write_run_manifest():
    """Test writing manifest with atomic write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        run_dir.mkdir()
        
        manifest = {
            "season": "2026Q1",
            "run_id": "run_test123",
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": "60m",
            "created_at": "2026-01-03T10:00:00Z",
            "git_sha": "abc123",
            "bars": 1000,
            "params_total": 50,
            "params_effective": 25,
        }
        
        manifest_path = write_run_manifest(run_dir, manifest)
        
        assert manifest_path.exists()
        assert manifest_path == run_dir / "manifest.json"
        
        # Verify content
        loaded = json.loads(manifest_path.read_text())
        assert loaded["run_id"] == "run_test123"
        assert loaded["dataset_id"] == "CME.MNQ"
        assert loaded["strategy_id"] == "S1"
        
        # Test missing required field
        invalid_manifest = manifest.copy()
        del invalid_manifest["dataset_id"]
        with pytest.raises(ValueError, match="missing required fields"):
            write_run_manifest(run_dir, invalid_manifest)


def test_write_run_metrics():
    """Test writing metrics with atomic write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        run_dir.mkdir()
        
        metrics = {
            "stage_name": "research",
            "net_profit": 1000.0,
            "max_dd": -500.0,
            "trades": 50,
            "created_at": "2026-01-03T10:00:00Z",
            "fills_count": 45,
            "param_subsample_rate": 1.0,
            "params_effective": 25,
            "params_total": 50,
            "bars": 1000,
        }
        
        metrics_path = write_run_metrics(run_dir, metrics)
        
        assert metrics_path.exists()
        assert metrics_path == run_dir / "metrics.json"
        
        # Verify content
        loaded = json.loads(metrics_path.read_text())
        assert loaded["net_profit"] == 1000.0
        assert loaded["trades"] == 50
        assert loaded["stage_name"] == "research"
        
        # Test missing required field
        invalid_metrics = metrics.copy()
        del invalid_metrics["net_profit"]
        with pytest.raises(ValueError, match="missing required fields"):
            write_run_metrics(run_dir, invalid_metrics)


def test_update_run_record_status():
    """Test updating run record status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        run_dir.mkdir()
        
        # Create initial run_record
        run_record_path = run_dir / "run_record.json"
        initial_record = {
            "version": "1.0",
            "run_id": "run_test123",
            "season": "2026Q1",
            "status": "CREATED",
            "created_at": "2026-01-03T09:00:00Z",
            "artifacts": {},
        }
        run_record_path.write_text(json.dumps(initial_record))
        
        # Update to RUNNING
        update_run_record_status(run_dir, "RUNNING", {"progress": 50})
        
        # Verify update
        loaded = json.loads(run_record_path.read_text())
        assert loaded["status"] == "RUNNING"
        assert "updated_at" in loaded
        assert loaded["progress"] == 50
        assert loaded["run_id"] == "run_test123"  # Original preserved
        
        # Update to COMPLETED
        update_run_record_status(run_dir, "COMPLETED")
        
        loaded = json.loads(run_record_path.read_text())
        assert loaded["status"] == "COMPLETED"
        
        # Test creating new run_record if doesn't exist
        run_dir2 = Path(tmpdir) / "run2"
        run_dir2.mkdir()
        
        update_run_record_status(run_dir2, "CREATED")
        
        run_record_path2 = run_dir2 / "run_record.json"
        assert run_record_path2.exists()
        loaded2 = json.loads(run_record_path2.read_text())
        assert loaded2["status"] == "CREATED"
        assert loaded2["run_id"] == run_dir2.name
        
        # Test invalid status
        with pytest.raises(ValueError, match="Invalid status"):
            update_run_record_status(run_dir, "INVALID_STATUS")


def test_create_canonical_run():
    """Test creating a complete canonical run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        run_id = "run_test123"
        
        manifest = {
            "season": season,
            "run_id": run_id,
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": "60m",
            "created_at": "2026-01-03T10:00:00Z",
            "git_sha": "abc123",
            "bars": 1000,
            "params_total": 50,
            "params_effective": 25,
        }
        
        metrics = {
            "stage_name": "research",
            "net_profit": 1000.0,
            "max_dd": -500.0,
            "trades": 50,
            "created_at": "2026-01-03T10:00:00Z",
        }
        
        run_dir = create_canonical_run(
            outputs_root=outputs_root,
            season=season,
            run_id=run_id,
            manifest=manifest,
            metrics=metrics,
            initial_status="CREATED"
        )
        
        assert run_dir.exists()
        assert (run_dir / "run_record.json").exists()
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "metrics.json").exists()
        
        # Verify run_record
        run_record = json.loads((run_dir / "run_record.json").read_text())
        assert run_record["status"] == "CREATED"
        assert run_record["run_id"] == run_id
        assert "intent" in run_record
        assert run_record["intent"]["strategy_id"] == "S1"
        
        # Verify manifest
        loaded_manifest = json.loads((run_dir / "manifest.json").read_text())
        assert loaded_manifest["run_id"] == run_id
        assert loaded_manifest["dataset_id"] == "CME.MNQ"
        
        # Verify metrics
        loaded_metrics = json.loads((run_dir / "metrics.json").read_text())
        assert loaded_metrics["net_profit"] == 1000.0
        assert loaded_metrics["trades"] == 50


def test_complete_run():
    """Test marking a run as COMPLETED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2026Q1"
        run_id = "run_test123"
        
        # First create a run
        manifest = {
            "season": season,
            "run_id": run_id,
            "dataset_id": "CME.MNQ",
            "strategy_id": "S1",
            "timeframe": "60m",
            "created_at": "2026-01-03T10:00:00Z",
            "git_sha": "abc123",
        }
        
        metrics = {
            "stage_name": "research",
            "net_profit": 1000.0,
            "max_dd": -500.0,
            "trades": 50,
            "created_at": "2026-01-03T10:00:00Z",
        }
        
        run_dir = create_canonical_run(
            outputs_root=outputs_root,
            season=season,
            run_id=run_id,
            manifest=manifest,
            metrics=metrics,
            initial_status="RUNNING"
        )
        
        # Update metrics
        updated_metrics = metrics.copy()
        updated_metrics["net_profit"] = 1500.0
        updated_metrics["sharpe"] = 1.5
        
        # Complete the run
        completed_dir = complete_run(run_dir, metrics=updated_metrics)
        
        assert completed_dir == run_dir
        
        # Verify status is COMPLETED
        run_record = json.loads((run_dir / "run_record.json").read_text())
        assert run_record["status"] == "COMPLETED"
        assert "completed_at" in run_record
        
        # Verify metrics were updated
        loaded_metrics = json.loads((run_dir / "metrics.json").read_text())
        assert loaded_metrics["net_profit"] == 1500.0
        assert loaded_metrics["sharpe"] == 1.5