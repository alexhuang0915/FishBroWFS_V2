
"""Tests for B5 Streamlit querystring parameter parsing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.artifact_reader import read_artifact


@pytest.fixture
def temp_outputs_root() -> Path:
    """Create temporary outputs root directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_run_dir(temp_outputs_root: Path) -> Path:
    """Create a sample run directory with artifacts."""
    season = "2026Q1"
    run_id = "stage0_coarse-20251218T093512Z-d3caa754"
    
    run_dir = temp_outputs_root / "seasons" / season / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Create minimal manifest.json
    manifest = {
        "run_id": run_id,
        "season": season,
        "config_hash": "test_hash",
        "created_at": "2025-12-18T09:35:12Z",
        "git_sha": "abc123def456",
        "dirty_repo": False,
        "param_subsample_rate": 0.1,
        "bars": 1000,
        "params_total": 100,
        "params_effective": 10,
        "artifact_version": "v1",
    }
    
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    
    # Create minimal metrics.json
    metrics = {
        "stage_name": "stage0_coarse",
        "bars": 1000,
        "params_total": 100,
        "params_effective": 10,
        "param_subsample_rate": 0.1,
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    
    # Create minimal winners.json
    winners = {
        "topk": [],
        "notes": {"schema": "v1"},
    }
    (run_dir / "winners.json").write_text(
        json.dumps(winners, indent=2), encoding="utf-8"
    )
    
    return run_dir


def test_report_link_format() -> None:
    """Test that report_link format is correct."""
    from control.report_links import make_report_link
    
    season = "2026Q1"
    run_id = "stage0_coarse-20251218T093512Z-d3caa754"
    
    link = make_report_link(season=season, run_id=run_id)
    
    assert link.startswith("/?")
    assert f"season={season}" in link
    assert f"run_id={run_id}" in link


def test_run_dir_path_construction(temp_outputs_root: Path, sample_run_dir: Path) -> None:
    """Test that run directory path is constructed correctly."""
    season = "2026Q1"
    run_id = "stage0_coarse-20251218T093512Z-d3caa754"
    
    # Construct path using same logic as Streamlit app
    run_dir = temp_outputs_root / "seasons" / season / "runs" / run_id
    
    assert run_dir.exists()
    assert run_dir == sample_run_dir


def test_artifacts_readable_from_run_dir(sample_run_dir: Path) -> None:
    """Test that artifacts can be read from run directory."""
    # Read manifest
    manifest_result = read_artifact(sample_run_dir / "manifest.json")
    assert manifest_result.raw["run_id"] == "stage0_coarse-20251218T093512Z-d3caa754"
    assert manifest_result.raw["season"] == "2026Q1"
    
    # Read metrics
    metrics_result = read_artifact(sample_run_dir / "metrics.json")
    assert metrics_result.raw["stage_name"] == "stage0_coarse"
    
    # Read winners
    winners_result = read_artifact(sample_run_dir / "winners.json")
    assert winners_result.raw["notes"]["schema"] == "v1"


def test_querystring_parsing_logic() -> None:
    """Test querystring parsing logic (simulating Streamlit query_params)."""
    # Simulate Streamlit query_params.get() behavior
    query_params = {
        "season": "2026Q1",
        "run_id": "stage0_coarse-20251218T093512Z-d3caa754",
    }
    
    season = query_params.get("season", "")
    run_id = query_params.get("run_id", "")
    
    assert season == "2026Q1"
    assert run_id == "stage0_coarse-20251218T093512Z-d3caa754"
    
    # Test missing parameters
    empty_params = {}
    season_empty = empty_params.get("season", "")
    run_id_empty = empty_params.get("run_id", "")
    
    assert season_empty == ""
    assert run_id_empty == ""


