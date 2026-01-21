
import json
import pytest
from pathlib import Path
from src.core.artifacts import write_run_artifacts

def test_write_run_artifacts_exports_plateau_candidates(tmp_path):
    """Verify write_run_artifacts creates plateau_candidates.json."""
    run_dir = tmp_path / "run1"
    manifest = {"run_id": "run1"}
    config_snapshot = {"param_subsample_rate": 1.0}
    metrics = {"stage_name": "stage1_topk", "net_profit": 1000.0}
    winners = {
        "schema": "v2",
        "stage_name": "stage1_topk",
        "generated_at": "2025-01-01T00:00:00Z",
        "topk": [],
        "notes": {"schema": "v2"}
    }
    plateau_candidates = [
        {"param_id": 0, "params": {"p1": 1}, "score": 10.0}
    ]
    
    # Run
    write_run_artifacts(
        run_dir=run_dir,
        manifest=manifest,
        config_snapshot=config_snapshot,
        metrics=metrics,
        winners=winners,
        plateau_candidates=plateau_candidates
    )
    
    # Assertions
    candidates_file = run_dir / "plateau_candidates.json"
    assert candidates_file.exists()
    
    with open(candidates_file, "r") as f:
        data = json.load(f)
        
    assert "plateau_candidates" in data
    assert len(data["plateau_candidates"]) == 1
    assert data["plateau_candidates"][0]["param_id"] == 0
    assert data["metadata"]["source_stage"] == "stage1_topk"
    assert data["metadata"]["count"] == 1

def test_write_run_artifacts_skips_plateau_candidates_if_none(tmp_path):
    """Verify plateau_candidates.json is NOT created if None passed."""
    run_dir = tmp_path / "run2"
    manifest = {"run_id": "run2"}
    config_snapshot = {}
    metrics = {}
    winners = {
        "schema": "v2",
        "stage_name": "stage1_topk",
        "generated_at": "2025-01-01T00:00:00Z",
        "topk": [],
        "notes": {"schema": "v2"}
    }
    
    # Run
    write_run_artifacts(
        run_dir=run_dir,
        manifest=manifest,
        config_snapshot=config_snapshot,
        metrics=metrics,
        winners=winners,
        plateau_candidates=None
    )
    
    # Assertions
    candidates_file = run_dir / "plateau_candidates.json"
    assert not candidates_file.exists()
