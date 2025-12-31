"""Test that history lists runs.

Tests that list_runs reads created runs with base_dir parameter.
"""
import json
import pytest
from pathlib import Path
from datetime import datetime

from gui.nicegui.services.run_index_service import list_runs


def test_history_lists_runs(tmp_path):
    """Test that list_runs reads created runs (section 6.2 of spec)."""
    # Create fake outputs structure in tmp_path
    base_dir = tmp_path / "outputs"
    season = "2026Q1"
    
    # Create runs directory structure
    runs_dir = base_dir / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Create two run directories with run_record.json
    run1_id = "run_abc123"
    run1_dir = runs_dir / run1_id
    run1_dir.mkdir()
    
    run1_record = {
        "version": "1.0",
        "run_id": run1_id,
        "season": season,
        "status": "CREATED",
        "created_at": datetime.now().isoformat(),
        "artifacts": {
            "intent": "intent.json",
            "derived": "derived.json",
            "run_record": "run_record.json",
        },
        "notes": "Test run 1",
    }
    
    run1_record_path = run1_dir / "run_record.json"
    with open(run1_record_path, "w", encoding="utf-8") as f:
        json.dump(run1_record, f)
    
    # Create intent.json and derived.json to simulate a complete run
    (run1_dir / "intent.json").write_text("{}")
    (run1_dir / "derived.json").write_text("{}")
    
    # Create second run without run_record.json (legacy)
    run2_id = "run_def456"
    run2_dir = runs_dir / run2_id
    run2_dir.mkdir()
    
    # Only create intent.json (legacy scanning will detect)
    (run2_dir / "intent.json").write_text("{}")
    # No derived.json or manifest.json -> status UNKNOWN
    
    # Call list_runs with base_dir parameter
    runs = list_runs(season=season, base_dir=str(base_dir))
    
    # Should return both runs
    assert len(runs) == 2
    
    # Find run1 by ID
    run1 = next(r for r in runs if r["run_id"] == run1_id)
    assert run1 is not None
    assert run1["season"] == season
    assert run1["status"] == "CREATED"
    assert run1["run_record_exists"] is True
    assert run1["intent_exists"] is True
    assert run1["derived_exists"] is True
    
    # Find run2 by ID
    run2 = next(r for r in runs if r["run_id"] == run2_id)
    assert run2 is not None
    assert run2["season"] == season
    assert run2["run_record_exists"] is False
    assert run2["intent_exists"] is True
    assert run2["derived_exists"] is False
    # Status should be UNKNOWN (no derived.json, no manifest.json)
    assert run2["status"] == "UNKNOWN"
    
    # Verify runs are sorted by created_at/started descending (most recent first)
    # Since we don't have timestamps, just ensure we got both runs


def test_list_runs_with_limit(tmp_path):
    """Test list_runs limit parameter."""
    base_dir = tmp_path / "outputs"
    season = "2026Q1"
    runs_dir = base_dir / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Create 5 runs
    for i in range(5):
        run_id = f"run_{i}"
        run_dir = runs_dir / run_id
        run_dir.mkdir()
        
        record = {
            "version": "1.0",
            "run_id": run_id,
            "season": season,
            "status": "CREATED",
            "created_at": datetime.now().isoformat(),
        }
        
        record_path = run_dir / "run_record.json"
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(record, f)
    
    # Test limit=3
    runs = list_runs(season=season, limit=3, base_dir=str(base_dir))
    assert len(runs) == 3
    
    # Test limit=None (default is 50)
    runs = list_runs(season=season, limit=None, base_dir=str(base_dir))
    assert len(runs) == 5
    
    # Test default limit (50)
    runs = list_runs(season=season, base_dir=str(base_dir))
    assert len(runs) == 5  # less than limit


def test_list_runs_empty_directory(tmp_path):
    """Test list_runs with empty or non-existent directory."""
    base_dir = tmp_path / "outputs"
    season = "2026Q1"
    
    # Directory doesn't exist
    runs = list_runs(season=season, base_dir=str(base_dir))
    assert runs == []
    
    # Directory exists but empty
    runs_dir = base_dir / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    runs = list_runs(season=season, base_dir=str(base_dir))
    assert runs == []


def test_list_runs_mixed_legacy_and_new(tmp_path):
    """Test list_runs with mix of legacy and new runs."""
    base_dir = tmp_path / "outputs"
    season = "2026Q1"
    runs_dir = base_dir / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Run with run_record.json (new)
    run1_dir = runs_dir / "run_new"
    run1_dir.mkdir()
    with open(run1_dir / "run_record.json", "w") as f:
        json.dump({"run_id": "run_new", "status": "COMPLETED", "created_at": "2025-01-01T00:00:00"}, f)
    (run1_dir / "manifest.json").write_text("{}")  # COMPLETED status
    
    # Run with derived.json but no run_record.json (legacy RUNNING)
    run2_dir = runs_dir / "run_legacy_running"
    run2_dir.mkdir()
    (run2_dir / "intent.json").write_text("{}")
    (run2_dir / "derived.json").write_text("{}")
    
    # Run with only intent.json (legacy UNKNOWN)
    run3_dir = runs_dir / "run_legacy_unknown"
    run3_dir.mkdir()
    (run3_dir / "intent.json").write_text("{}")
    
    runs = list_runs(season=season, base_dir=str(base_dir))
    
    # Should have 3 runs
    assert len(runs) == 3
    
    # Check statuses
    statuses = {r["run_id"]: r["status"] for r in runs}
    assert statuses["run_new"] == "COMPLETED"
    assert statuses["run_legacy_running"] == "RUNNING"
    assert statuses["run_legacy_unknown"] == "UNKNOWN"


def test_list_runs_base_dir_parameter_works():
    """Test that base_dir parameter is actually used (not hardcoded)."""
    # This test ensures the function respects base_dir parameter
    # by checking it doesn't rely on hardcoded "outputs" path
    import tempfile
    base_dir = tempfile.mkdtemp()
    base_path = Path(base_dir)
    
    season = "2026Q1"
    runs_dir = base_path / "seasons" / season / "runs"
    runs_dir.mkdir(parents=True)
    
    # Create a run
    run_dir = runs_dir / "test_run"
    run_dir.mkdir()
    with open(run_dir / "run_record.json", "w") as f:
        json.dump({"run_id": "test_run", "status": "CREATED", "created_at": "2025-01-01T00:00:00"}, f)
    
    # Call with custom base_dir
    runs = list_runs(season=season, base_dir=base_dir)
    
    assert len(runs) == 1
    assert runs[0]["run_id"] == "test_run"
    
    # Cleanup
    import shutil
    shutil.rmtree(base_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])