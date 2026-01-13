"""
Test that admission gate rejects runs with missing artifacts cleanly.
"""
import json
import tempfile
from pathlib import Path
import pytest

from control.portfolio.evidence_reader import RunEvidenceReader


def test_missing_policy_check_rejects(tmp_path):
    """Run with missing policy_check.json should raise FileNotFoundError."""
    # Create a dummy run directory without policy_check.json
    run_dir = tmp_path / "seasons" / "current" / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write a minimal report.json (so score can be read)
    report = {"metrics": {"score": 1.5, "max_dd": -0.1}}
    (run_dir / "report.json").write_text(json.dumps(report))
    
    # Write equity.parquet (requires pandas)
    try:
        import pandas as pd
        import numpy as np
        dates = pd.date_range("2026-01-01", periods=10, tz="UTC")
        equity = 10000 + np.cumsum(np.random.randn(10) * 100)
        df = pd.DataFrame({"ts": dates, "equity": equity})
        df.to_parquet(run_dir / "equity.parquet")
    except ImportError:
        pytest.skip("pandas not available")
    
    reader = RunEvidenceReader(outputs_root=tmp_path)
    
    # Should raise FileNotFoundError when reading policy_check
    with pytest.raises(FileNotFoundError, match="policy_check.json not found"):
        reader.read_policy_check("test_run")
    
    # validate_run_has_required_artifacts should list missing policy_check
    missing = reader.validate_run_has_required_artifacts("test_run")
    assert "policy_check.json" in missing


def test_missing_score_rejects(tmp_path):
    """Run with missing score/metrics should raise FileNotFoundError."""
    run_dir = tmp_path / "seasons" / "current" / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write policy_check.json
    policy = {
        "pre_flight_checks": [],
        "post_flight_checks": [],
        "downstream_admissible": True
    }
    (run_dir / "policy_check.json").write_text(json.dumps(policy))
    
    # Write equity.parquet
    try:
        import pandas as pd
        import numpy as np
        dates = pd.date_range("2026-01-01", periods=10, tz="UTC")
        equity = 10000 + np.cumsum(np.random.randn(10) * 100)
        df = pd.DataFrame({"ts": dates, "equity": equity})
        df.to_parquet(run_dir / "equity.parquet")
    except ImportError:
        pytest.skip("pandas not available")
    
    reader = RunEvidenceReader(outputs_root=tmp_path)
    
    # Should raise FileNotFoundError when reading score
    with pytest.raises(FileNotFoundError, match="Could not find score"):
        reader.read_score("test_run")
    
    missing = reader.validate_run_has_required_artifacts("test_run")
    assert "score/metrics" in missing


def test_missing_equity_rejects(tmp_path):
    """Run with missing equity.parquet should raise FileNotFoundError."""
    run_dir = tmp_path / "seasons" / "current" / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write policy_check.json
    policy = {
        "pre_flight_checks": [],
        "post_flight_checks": [],
        "downstream_admissible": True
    }
    (run_dir / "policy_check.json").write_text(json.dumps(policy))
    
    # Write report.json with score and max_dd
    report = {"metrics": {"score": 1.5, "max_dd": -0.1}}
    (run_dir / "report.json").write_text(json.dumps(report))
    
    reader = RunEvidenceReader(outputs_root=tmp_path)
    
    # Should raise FileNotFoundError when reading returns series
    with pytest.raises(FileNotFoundError, match="equity.parquet not found"):
        reader.read_returns_series("test_run")
    
    missing = reader.validate_run_has_required_artifacts("test_run")
    assert "equity.parquet" in missing


def test_read_returns_series_if_exists_returns_none_on_missing(tmp_path):
    """read_returns_series_if_exists returns None when equity missing."""
    run_dir = tmp_path / "seasons" / "current" / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    reader = RunEvidenceReader(outputs_root=tmp_path)
    result = reader.read_returns_series_if_exists("test_run")
    assert result is None


def test_downstream_admissible_false_causes_rejection(tmp_path):
    """If downstream_admissible is False, admission should reject."""
    run_dir = tmp_path / "seasons" / "current" / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write policy_check.json with downstream_admissible = False
    policy = {
        "pre_flight_checks": [{"policy_name": "test", "passed": False, "message": "failed", "checked_at": "2026-01-01T00:00:00Z"}],
        "post_flight_checks": [],
        "downstream_admissible": False
    }
    (run_dir / "policy_check.json").write_text(json.dumps(policy))
    
    reader = RunEvidenceReader(outputs_root=tmp_path)
    bundle = reader.read_policy_check("test_run")
    assert bundle.downstream_admissible is False


def test_artifact_validation_passes_when_all_present(tmp_path):
    """When all artifacts are present, validation returns empty list."""
    run_dir = tmp_path / "seasons" / "current" / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write policy_check.json
    policy = {
        "pre_flight_checks": [],
        "post_flight_checks": [],
        "downstream_admissible": True
    }
    (run_dir / "policy_check.json").write_text(json.dumps(policy))
    
    # Write report.json
    report = {"metrics": {"score": 1.5, "max_dd": -0.1}}
    (run_dir / "report.json").write_text(json.dumps(report))
    
    # Write equity.parquet
    try:
        import pandas as pd
        import numpy as np
        dates = pd.date_range("2026-01-01", periods=10, tz="UTC")
        equity = 10000 + np.cumsum(np.random.randn(10) * 100)
        df = pd.DataFrame({"ts": dates, "equity": equity})
        df.to_parquet(run_dir / "equity.parquet")
    except ImportError:
        pytest.skip("pandas not available")
    
    reader = RunEvidenceReader(outputs_root=tmp_path)
    missing = reader.validate_run_has_required_artifacts("test_run")
    assert missing == []