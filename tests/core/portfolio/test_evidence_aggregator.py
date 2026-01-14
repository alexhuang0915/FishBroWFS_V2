"""
Tests for Evidence Aggregator (R6-1).
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from src.core.portfolio.evidence_aggregator import (
    EvidenceAggregator,
    EvidenceIndexV1,
    JobEvidenceSummaryV1,
    GateStatus,
    JobLifecycle,
    DataStatus,
    GateSummaryV1,
    DataStateV1,
)


def test_evidence_index_model():
    """Test EvidenceIndexV1 Pydantic model."""
    # Create a sample job summary
    job_summary = JobEvidenceSummaryV1(
        job_id="test_job_123",
        lifecycle=JobLifecycle.ACTIVE,
        strategy_id="strategy_ma_crossover",
        instrument="MNQ",
        timeframe="5m",
        run_mode="research",
        gate_status=GateStatus.PASS,
        gate_summary=GateSummaryV1(
            total_permutations=100,
            valid_candidates=25,
            plateau_check="Pass",
        ),
        data_state=DataStateV1(
            data1_status=DataStatus.READY,
            data2_status=DataStatus.READY,
            data1_dataset_id="dataset_1",
            data2_dataset_id="dataset_2",
        ),
        artifacts_present=["strategy_report_v1.json", "input_manifest.json"],
        created_at=datetime.now().isoformat(),
        job_type="RUN_RESEARCH_WFS",
        season="season_2024q1",
    )
    
    # Create evidence index
    index = EvidenceIndexV1(
        schema_version="v1",
        source="",
        job_count=1,
        jobs={"test_job_123": job_summary},
    )
    
    # Test serialization/deserialization
    index_json = index.model_dump_json(indent=2)
    index_dict = json.loads(index_json)
    
    assert index_dict["schema_version"] == "v1"
    assert index_dict["job_count"] == 1
    assert "test_job_123" in index_dict["jobs"]
    
    # Test that we can load it back
    loaded_index = EvidenceIndexV1(**index_dict)
    assert loaded_index.job_count == 1
    assert loaded_index.jobs["test_job_123"].job_id == "test_job_123"


def test_evidence_aggregator_initialization():
    """Test EvidenceAggregator initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a mock jobs directory structure
        jobs_root = tmp_path / "jobs"
        jobs_root.mkdir(parents=True, exist_ok=True)
        
        # Create a mock job directory
        job_dir = jobs_root / "job_123"
        job_dir.mkdir()
        
        # Create a mock strategy report
        strategy_report = {
            "gatekeeper": {
                "gate_status": "PASS",
                "total_permutations": 100,
                "valid_candidates": 25,
                "plateau_check": "Pass",
            }
        }
        (job_dir / "strategy_report_v1.json").write_text(json.dumps(strategy_report))
        
        # Create input manifest
        input_manifest = {
            "strategy_id": "strategy_ma_crossover",
            "instrument": "MNQ",
            "timeframe": "5m",
            "run_mode": "research",
            "season": "season_2024q1",
            "job_type": "RUN_RESEARCH_WFS",
        }
        (job_dir / "input_manifest.json").write_text(json.dumps(input_manifest))
        
        # Create derived datasets
        derived_datasets = {
            "data1_status": "READY",
            "data2_status": "READY",
            "data1_id": "dataset_1",
            "data2_id": "dataset_2",
        }
        (job_dir / "derived_datasets.json").write_text(json.dumps(derived_datasets))
        
        # Initialize aggregator
        aggregator = EvidenceAggregator(jobs_root=jobs_root)
        
        # Scan job directories
        job_dirs = aggregator.scan_job_directories()
        assert len(job_dirs) == 1
        assert job_dirs[0].name == "job_123"
        
        # Build job summary
        summary = aggregator.build_job_summary(job_dir)
        assert summary is not None
        assert summary.job_id == "job_123"
        assert summary.gate_status == GateStatus.PASS
        assert summary.strategy_id == "strategy_ma_crossover"
        assert summary.instrument == "MNQ"
        assert summary.timeframe == "5m"
        
        # Build index
        index = aggregator.build_index()
        assert index.job_count == 1
        assert "job_123" in index.jobs
        
        # Write index
        output_dir = tmp_path / "output"
        json_path = aggregator.write_index(index, output_dir)
        
        assert json_path.exists()
        assert (output_dir / "evidence_index_v1.sha256").exists()
        
        # Load index back
        loaded_index = aggregator.load_index(json_path)
        assert loaded_index.job_count == 1


def test_evidence_aggregator_filters():
    """Test EvidenceAggregator filtering options."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a mock jobs directory structure
        jobs_root = tmp_path / "jobs"
        jobs_root.mkdir(parents=True, exist_ok=True)
        
        # Create job directories with different statuses
        for i, (job_id, gate_status) in enumerate([
            ("job_pass", "PASS"),
            ("job_warn", "WARN"),
            ("job_fail", "FAIL"),
        ]):
            job_dir = jobs_root / job_id
            job_dir.mkdir()
            
            strategy_report = {
                "gatekeeper": {
                    "gate_status": gate_status,
                    "total_permutations": 100,
                    "valid_candidates": 25,
                    "plateau_check": "Pass",
                }
            }
            (job_dir / "strategy_report_v1.json").write_text(json.dumps(strategy_report))
            
            input_manifest = {
                "strategy_id": f"strategy_{i}",
                "instrument": "MNQ",
                "timeframe": "5m",
                "run_mode": "research",
            }
            (job_dir / "input_manifest.json").write_text(json.dumps(input_manifest))
            
            derived_datasets = {
                "data1_status": "READY",
                "data2_status": "READY",
            }
            (job_dir / "derived_datasets.json").write_text(json.dumps(derived_datasets))
        
        # Initialize aggregator
        aggregator = EvidenceAggregator(jobs_root=jobs_root)
        
        # Test default filters (exclude FAIL, exclude WARN)
        index_default = aggregator.build_index()
        assert index_default.job_count == 1  # Only PASS
        
        # Test include WARN
        index_with_warn = aggregator.build_index(include_warn=True)
        assert index_with_warn.job_count == 2  # PASS + WARN
        
        # Test include FAIL
        index_with_fail = aggregator.build_index(include_fail=True)
        assert index_with_fail.job_count == 2  # PASS + FAIL
        
        # Test include both
        index_all = aggregator.build_index(include_warn=True, include_fail=True)
        assert index_all.job_count == 3  # PASS + WARN + FAIL


def test_evidence_aggregator_skips_special_directories():
    """Test that EvidenceAggregator skips special directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a mock jobs directory structure
        jobs_root = tmp_path / "jobs"
        jobs_root.mkdir(parents=True, exist_ok=True)
        
        # Create special directories that should be skipped
        (jobs_root / "_trash").mkdir()
        (jobs_root / ".hidden").mkdir()
        (jobs_root / "__pycache__").mkdir()
        
        # Create a regular job directory
        job_dir = jobs_root / "regular_job"
        job_dir.mkdir()
        
        # Create minimal artifacts
        strategy_report = {
            "gatekeeper": {
                "gate_status": "PASS",
            }
        }
        (job_dir / "strategy_report_v1.json").write_text(json.dumps(strategy_report))
        
        input_manifest = {
            "strategy_id": "test_strategy",
        }
        (job_dir / "input_manifest.json").write_text(json.dumps(input_manifest))
        
        # Initialize aggregator
        aggregator = EvidenceAggregator(jobs_root=jobs_root)
        
        # Scan job directories
        job_dirs = aggregator.scan_job_directories()
        
        # Should only find the regular job
        assert len(job_dirs) == 1
        assert job_dirs[0].name == "regular_job"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])