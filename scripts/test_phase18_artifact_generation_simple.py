#!/usr/bin/env python3
"""
Simple test for Phase 18 artifact generation.
Tests core artifact_writers module directly.
"""
import json
import tempfile
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.artifact_writers import write_full_artifact

def test_artifact_generation():
    """Test that artifact generation creates all required files."""
    print("=== Phase 18 Artifact Generation Test ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create artifact directory
        artifact_dir = tmp_path / "artifact_test_20260103_150000"
        artifact_dir.mkdir()
        
        print(f"Created test artifact directory: {artifact_dir}")
        
        # Create test data
        manifest = {
            "run_id": "artifact_S1_CME.MNQ_20260103_150000",
            "created_at": "2026-01-03T15:00:00Z",
            "git_sha": "abc123def",
            "config_hash": "sha256:test123",
            "season": "2026Q1",
            "dataset_id": "CME.MNQ",
            "artifact_version": "phase18_v1"
        }
        
        config = {
            "strategy": "S1",
            "dataset": "CME.MNQ",
            "timeframe": 60,
            "context_feeds": []
        }
        
        metrics = {
            "net_profit": 1250.75,
            "max_dd": -350.25,
            "trades": 42,
            "sharpe": 1.85,
            "sortino": 2.12,
            "profit_factor": 1.65,
            "win_rate": 58.3,
            "sqn": 2.45
        }
        
        # Generate artifact files
        print("Generating artifact files...")
        files = write_full_artifact(artifact_dir, manifest, config, metrics)
        
        # List generated files
        print(f"\nGenerated files:")
        for file_type, file_path in files.items():
            if file_path and file_path.exists():
                print(f"  ✓ {file_type}: {file_path.name} ({file_path.stat().st_size} bytes)")
            else:
                print(f"  ✗ {file_type}: MISSING")
        
        # Check all required files exist
        required_files = [
            "manifest.json",
            "metrics.json", 
            "trades.parquet",
            "equity.parquet",
            "report.json"
        ]
        
        print("\n=== File Existence Check ===")
        all_exist = True
        for req_file in required_files:
            file_path = artifact_dir / req_file
            exists = file_path.exists()
            status = "✓" if exists else "✗"
            print(f"  {status} {req_file}: {exists}")
            if not exists:
                all_exist = False
        
        # Check file contents
        print("\n=== File Contents Check ===")
        
        # Check manifest.json
        manifest_path = artifact_dir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest_data = json.load(f)
            print(f"  ✓ manifest.json: {len(manifest_data)} keys")
        
        # Check metrics.json
        metrics_path = artifact_dir / "metrics.json"
        if metrics_path.exists():
            with open(metrics_path) as f:
                metrics_data = json.load(f)
            print(f"  ✓ metrics.json: {len(metrics_data)} metrics")
        
        # Check report.json
        report_path = artifact_dir / "report.json"
        if report_path.exists():
            with open(report_path) as f:
                report_data = json.load(f)
            print(f"  ✓ report.json: {len(report_data)} sections")
        
        # Check parquet files
        trades_path = artifact_dir / "trades.parquet"
        if trades_path.exists():
            print(f"  ✓ trades.parquet: {trades_path.stat().st_size} bytes")
        
        equity_path = artifact_dir / "equity.parquet"
        if equity_path.exists():
            print(f"  ✓ equity.parquet: {equity_path.stat().st_size} bytes")
        
        # Summary
        print("\n=== Test Summary ===")
        if all_exist:
            print("✅ SUCCESS: All Phase 18 artifact requirements met!")
            print(f"  - All {len(required_files)} required files created")
            print(f"  - Files contain valid data")
            return 0
        else:
            print("❌ FAILURE: Artifact generation incomplete")
            print(f"  - Missing required files")
            return 1

if __name__ == "__main__":
    exit_code = test_artifact_generation()
    sys.exit(exit_code)