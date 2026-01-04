"""
Test that desktop runs generate Phase 18 artifact bundle (trades.parquet, equity.parquet, report.json).
"""

import tempfile
import json
from pathlib import Path
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from research.run_writer import complete_run, create_canonical_run


def test_complete_run_generates_phase18_artifacts(tmp_path):
    """Test that complete_run generates Phase 18 artifacts when requested."""
    # Create a mock run directory
    outputs_root = tmp_path / "outputs"
    season = "2026Q1"
    run_id = "run_test_phase18"
    
    # Create manifest and metrics
    manifest = {
        "season": season,
        "run_id": run_id,
        "dataset_id": "MNQ.2026Q1",
        "strategy_id": "S2",
        "timeframe": "60m",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": "test",
        "bars": 1000,
        "params_total": 10,
        "params_effective": 5,
    }
    
    metrics = {
        "stage_name": "research",
        "net_profit": 1234.56,
        "max_dd": -567.89,
        "trades": 42,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fills_count": 42,
        "param_subsample_rate": 1.0,
        "params_effective": 5,
        "params_total": 10,
        "bars": 1000,
    }
    
    # Create canonical run
    run_dir = create_canonical_run(
        outputs_root=outputs_root,
        season=season,
        run_id=run_id,
        manifest=manifest,
        metrics=metrics,
        initial_status="RUNNING"
    )
    
    # Verify initial files exist
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "metrics.json").exists()
    assert (run_dir / "run_record.json").exists()
    
    # Complete the run with Phase 18 artifact generation
    complete_run(
        run_dir=run_dir,
        manifest=manifest,
        metrics=metrics,
        generate_phase18_artifacts=True
    )
    
    # Verify Phase 18 artifacts were created
    required_files = [
        "trades.parquet",
        "equity.parquet", 
        "report.json"
    ]
    
    for filename in required_files:
        file_path = run_dir / filename
        assert file_path.exists(), f"Phase 18 artifact {filename} should exist"
    
    # Verify trades.parquet has correct schema
    trades_df = pd.read_parquet(run_dir / "trades.parquet")
    expected_columns = ["entry_ts", "exit_ts", "side", "entry_px", "exit_px", "pnl", "bars_held"]
    for col in expected_columns:
        assert col in trades_df.columns, f"trades.parquet missing column {col}"
    
    # Verify equity.parquet has correct schema  
    equity_df = pd.read_parquet(run_dir / "equity.parquet")
    assert "ts" in equity_df.columns
    assert "equity" in equity_df.columns
    
    # Verify report.json has correct structure
    with open(run_dir / "report.json", "r", encoding="utf-8") as f:
        report = json.load(f)
    
    # The actual report structure from write_full_artifact may vary
    # Check for essential fields that should be present
    assert "metrics" in report
    assert "net_profit" in report["metrics"]
    assert report["metrics"]["net_profit"] == 1234.56
    assert "max_dd" in report["metrics"]
    assert report["metrics"]["max_dd"] == -567.89
    assert "trades" in report["metrics"]
    assert report["metrics"]["trades"] == 42
    
    # Verify run_record.json status is COMPLETED
    with open(run_dir / "run_record.json", "r", encoding="utf-8") as f:
        run_record = json.load(f)
    
    assert run_record["status"] == "COMPLETED"
    assert "completed_at" in run_record


def test_complete_run_without_phase18_artifacts(tmp_path):
    """Test that complete_run can skip Phase 18 artifact generation."""
    outputs_root = tmp_path / "outputs"
    season = "2026Q1"
    run_id = "run_test_no_phase18"
    
    manifest = {
        "season": season,
        "run_id": run_id,
        "dataset_id": "MNQ.2026Q1",
        "strategy_id": "S2",
        "timeframe": "60m",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": "test",
        "bars": 1000,
        "params_total": 10,
        "params_effective": 5,
    }
    
    metrics = {
        "stage_name": "research",
        "net_profit": 1234.56,
        "max_dd": -567.89,
        "trades": 42,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fills_count": 42,
        "param_subsample_rate": 1.0,
        "params_effective": 5,
        "params_total": 10,
        "bars": 1000,
    }
    
    # Create canonical run
    run_dir = create_canonical_run(
        outputs_root=outputs_root,
        season=season,
        run_id=run_id,
        manifest=manifest,
        metrics=metrics,
        initial_status="RUNNING"
    )
    
    # Complete the run WITHOUT Phase 18 artifact generation
    complete_run(
        run_dir=run_dir,
        manifest=manifest,
        metrics=metrics,
        generate_phase18_artifacts=False  # Explicitly disabled
    )
    
    # Verify Phase 18 artifacts were NOT created
    phase18_files = ["trades.parquet", "equity.parquet", "report.json"]
    for filename in phase18_files:
        file_path = run_dir / filename
        assert not file_path.exists(), f"Phase 18 artifact {filename} should not exist when generate_phase18_artifacts=False"
    
    # But core files should exist
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "metrics.json").exists()
    assert (run_dir / "run_record.json").exists()


def test_minimal_phase18_artifacts_for_zero_trades(tmp_path):
    """Test that minimal Phase 18 artifacts are generated for zero-trade runs."""
    outputs_root = tmp_path / "outputs"
    season = "2026Q1"
    run_id = "run_test_zero_trades"
    
    manifest = {
        "season": season,
        "run_id": run_id,
        "dataset_id": "MNQ.2026Q1",
        "strategy_id": "S2",
        "timeframe": "60m",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": "test",
        "bars": 1000,
        "params_total": 10,
        "params_effective": 5,
    }
    
    # Metrics with zero trades
    metrics = {
        "stage_name": "research",
        "net_profit": 0.0,
        "max_dd": 0.0,
        "trades": 0,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fills_count": 0,
        "param_subsample_rate": 1.0,
        "params_effective": 5,
        "params_total": 10,
        "bars": 1000,
    }
    
    # Create canonical run
    run_dir = create_canonical_run(
        outputs_root=outputs_root,
        season=season,
        run_id=run_id,
        manifest=manifest,
        metrics=metrics,
        initial_status="RUNNING"
    )
    
    # Complete with Phase 18 artifacts
    complete_run(
        run_dir=run_dir,
        manifest=manifest,
        metrics=metrics,
        generate_phase18_artifacts=True
    )
    
    # Verify all Phase 18 artifacts exist
    assert (run_dir / "trades.parquet").exists()
    assert (run_dir / "equity.parquet").exists()
    assert (run_dir / "report.json").exists()
    
    # Verify trades.parquet is empty (0 rows) for zero trades
    trades_df = pd.read_parquet(run_dir / "trades.parquet")
    assert len(trades_df) == 0, "trades.parquet should be empty for zero-trade run"
    
    # Verify report.json exists and has metrics
    with open(run_dir / "report.json", "r", encoding="utf-8") as f:
        report = json.load(f)
    
    # Check that report has metrics with zero trades
    assert "metrics" in report
    assert report["metrics"]["trades"] == 0
    # Note: The actual report may not have a "status" field
    # That's OK as long as the file exists with correct metrics


def test_artifact_bundle_integration_with_active_run_state(tmp_path):
    """Test that artifact bundle works with active run state classification."""
    outputs_root = tmp_path / "outputs"
    season = "2026Q1"
    run_id = "run_test_active_state"
    
    manifest = {
        "season": season,
        "run_id": run_id,
        "dataset_id": "MNQ.2026Q1",
        "strategy_id": "S2",
        "timeframe": "60m",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": "test",
        "bars": 1000,
        "params_total": 10,
        "params_effective": 5,
    }
    
    metrics = {
        "stage_name": "research",
        "net_profit": 1234.56,
        "max_dd": -567.89,
        "trades": 42,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fills_count": 42,
        "param_subsample_rate": 1.0,
        "params_effective": 5,
        "params_total": 10,
        "bars": 1000,
    }
    
    # Create canonical run
    run_dir = create_canonical_run(
        outputs_root=outputs_root,
        season=season,
        run_id=run_id,
        manifest=manifest,
        metrics=metrics,
        initial_status="RUNNING"
    )
    
    # Complete with Phase 18 artifacts
    complete_run(
        run_dir=run_dir,
        manifest=manifest,
        metrics=metrics,
        generate_phase18_artifacts=True
    )
    
    # Now test active run state classification
    # Import here to avoid circular imports in test
    from gui.desktop.state.active_run_state import active_run_state, RunStatus
    
    # Set this run as active
    active_run_state.set_active_run(run_dir, season, run_id)
    
    # Verify active run state classifies it correctly
    # With all Phase 18 artifacts, it should be READY or VERIFIED
    assert active_run_state.status != RunStatus.NONE
    assert active_run_state.status != RunStatus.PARTIAL
    
    # Verify diagnostics show all files as READY
    diag = active_run_state.diagnostics
    assert diag.get("metrics_json") == "READY"
    assert diag.get("manifest_json") == "READY"
    assert diag.get("run_record_json") == "READY"
    assert diag.get("trades_parquet") == "READY"
    assert diag.get("equity_parquet") == "READY"
    assert diag.get("report_json") == "READY"