"""
Tests for Portfolio Orchestrator (R6-2).
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from src.core.portfolio.portfolio_orchestrator import (
    PortfolioOrchestrator,
    PortfolioRunConfigV1,
    PortfolioRunRecordV1,
    CandidateSelector,
)
from src.core.portfolio.evidence_aggregator import (
    EvidenceIndexV1,
    JobEvidenceSummaryV1,
    GateStatus,
    JobLifecycle,
    DataStatus,
    GatekeeperMetricsV1,
    DataStateV1,
)


def create_mock_evidence_index(tmp_path: Path) -> Path:
    """Create a mock evidence index file for testing."""
    # Create sample job summaries
    jobs = {}
    
    for i in range(10):
        job_id = f"job_{i:03d}"
        
        # Vary gate status
        if i < 3:
            gate_status = GateStatus.PASS
        elif i < 6:
            gate_status = GateStatus.WARN
        else:
            gate_status = GateStatus.FAIL
        
        # Vary instrument and timeframe
        instrument = "MNQ" if i % 2 == 0 else "MES"
        timeframe = "5m" if i % 3 == 0 else "15m"
        
        job_summary = JobEvidenceSummaryV1(
            job_id=job_id,
            lifecycle=JobLifecycle.ACTIVE,
            strategy_id=f"strategy_{i}",
            instrument=instrument,
            timeframe=timeframe,
            run_mode="research",
            gate_status=gate_status,
            gatekeeper_metrics=GatekeeperMetricsV1(
                total_permutations=100 + i * 10,
                valid_candidates=20 + i * 2,
                plateau_check="Pass",
            ),
            data_state=DataStateV1(
                data1_status=DataStatus.READY,
                data2_status=DataStatus.READY,
                data1_dataset_id=f"dataset_{i}_1",
                data2_dataset_id=f"dataset_{i}_2",
            ),
            artifacts_present=["strategy_report_v1.json", "input_manifest.json"],
            created_at=datetime.now().isoformat(),
            job_type="RUN_RESEARCH_WFS",
            season="season_2024q1",
        )
        
        jobs[job_id] = job_summary
    
    # Create evidence index
    index = EvidenceIndexV1(
        schema_version="v1",
        source="outputs/jobs/",
        job_count=len(jobs),
        jobs=jobs,
    )
    
    # Write to file
    index_path = tmp_path / "evidence_index_v1.json"
    index_json = index.model_dump_json(indent=2)
    index_path.write_text(index_json)
    
    return index_path


def test_portfolio_run_config_model():
    """Test PortfolioRunConfigV1 Pydantic model."""
    config = PortfolioRunConfigV1(
        portfolio_run_id="run_123",
        portfolio_id="portfolio_456",
        name="Test Portfolio Run",
        description="Test description",
        strategy="top_performers",
        max_candidates=5,
        min_candidates=2,
        correlation_threshold=0.7,
        include_warn=False,
        include_archived=False,
        include_fail=False,
    )
    
    # Test serialization/deserialization
    config_json = config.model_dump_json(indent=2)
    config_dict = json.loads(config_json)
    
    assert config_dict["portfolio_run_id"] == "run_123"
    assert config_dict["portfolio_id"] == "portfolio_456"
    assert config_dict["strategy"] == "top_performers"
    assert config_dict["max_candidates"] == 5
    assert config_dict["min_candidates"] == 2
    
    # Test that we can load it back
    loaded_config = PortfolioRunConfigV1(**config_dict)
    assert loaded_config.portfolio_run_id == "run_123"


def test_portfolio_run_record_model():
    """Test PortfolioRunRecordV1 Pydantic model."""
    config = PortfolioRunConfigV1(
        portfolio_run_id="run_123",
        portfolio_id="portfolio_456",
    )
    
    record = PortfolioRunRecordV1(
        portfolio_run_id="run_123",
        portfolio_id="portfolio_456",
        config=config,
        evidence_index_path="/path/to/evidence_index_v1.json",
        selected_job_ids=["job_001", "job_002", "job_003"],
        submitted_job_id="admission_job_789",
        submitted_at=datetime.now().isoformat(),
        admission_result_path="/path/to/admission_decision.json",
        admission_verdict="ADMITTED",
        admission_summary="Admitted 3 of 10 runs",
    )
    
    # Test serialization/deserialization
    record_json = record.model_dump_json(indent=2)
    record_dict = json.loads(record_json)
    
    assert record_dict["portfolio_run_id"] == "run_123"
    assert record_dict["portfolio_id"] == "portfolio_456"
    assert len(record_dict["selected_job_ids"]) == 3
    assert record_dict["submitted_job_id"] == "admission_job_789"
    assert record_dict["admission_verdict"] == "ADMITTED"
    
    # Test that we can load it back
    loaded_record = PortfolioRunRecordV1(**record_dict)
    assert loaded_record.portfolio_run_id == "run_123"


def test_candidate_selector_top_performers():
    """Test CandidateSelector.top_performers method."""
    # Create a mock evidence index
    jobs = {}
    
    # Create jobs with different statuses
    for i, gate_status in enumerate([GateStatus.PASS, GateStatus.WARN, GateStatus.FAIL, GateStatus.PASS]):
        job_id = f"job_{i}"
        job_summary = JobEvidenceSummaryV1(
            job_id=job_id,
            lifecycle=JobLifecycle.ACTIVE,
            strategy_id=f"strategy_{i}",
            instrument="MNQ",
            timeframe="5m",
            run_mode="research",
            gate_status=gate_status,
            gatekeeper_metrics=GatekeeperMetricsV1(),
            data_state=DataStateV1(
                data1_status=DataStatus.READY,
                data2_status=DataStatus.READY,
            ),
            artifacts_present=["strategy_report_v1.json"],
        )
        jobs[job_id] = job_summary
    
    index = EvidenceIndexV1(
        schema_version="v1",
        source="outputs/jobs/",
        job_count=len(jobs),
        jobs=jobs,
    )
    
    # Test default (exclude WARN and FAIL)
    selected = CandidateSelector.select_top_performers(
        index=index,
        max_candidates=10,
        include_warn=False,
    )
    
    # Should only select PASS jobs
    assert len(selected) == 2  # job_0 and job_3
    assert "job_0" in selected
    assert "job_3" in selected
    assert "job_1" not in selected  # WARN
    assert "job_2" not in selected  # FAIL
    
    # Test include WARN
    selected_with_warn = CandidateSelector.select_top_performers(
        index=index,
        max_candidates=10,
        include_warn=True,
    )
    
    # Should select PASS and WARN jobs
    assert len(selected_with_warn) == 3  # job_0, job_1, job_3
    assert "job_1" in selected_with_warn  # WARN included


def test_candidate_selector_diversified():
    """Test CandidateSelector.diversified method."""
    # Create a mock evidence index with different instruments/timeframes
    jobs = {}
    
    instruments = ["MNQ", "MES", "MNQ", "MES", "MNQ"]
    timeframes = ["5m", "5m", "15m", "15m", "5m"]
    
    for i in range(5):
        job_id = f"job_{i}"
        job_summary = JobEvidenceSummaryV1(
            job_id=job_id,
            lifecycle=JobLifecycle.ACTIVE,
            strategy_id=f"strategy_{i}",
            instrument=instruments[i],
            timeframe=timeframes[i],
            run_mode="research",
            gate_status=GateStatus.PASS,
            gatekeeper_metrics=GatekeeperMetricsV1(),
            data_state=DataStateV1(
                data1_status=DataStatus.READY,
                data2_status=DataStatus.READY,
            ),
            artifacts_present=["strategy_report_v1.json"],
        )
        jobs[job_id] = job_summary
    
    index = EvidenceIndexV1(
        schema_version="v1",
        source="outputs/jobs/",
        job_count=len(jobs),
        jobs=jobs,
    )
    
    # Test diversified selection
    selected = CandidateSelector.select_diversified(
        index=index,
        max_candidates=10,
        include_warn=False,
    )
    
    # Should select at most 1 from each instrument/timeframe group
    # Groups: MNQ_5m, MES_5m, MNQ_15m, MES_15m
    assert len(selected) == 4  # 4 unique groups
    
    # Check that we have one from each group
    selected_instruments = set()
    selected_timeframes = set()
    
    for job_id in selected:
        job_summary = index.jobs[job_id]
        selected_instruments.add(job_summary.instrument)
        selected_timeframes.add(job_summary.timeframe)
    
    assert "MNQ" in selected_instruments
    assert "MES" in selected_instruments
    assert "5m" in selected_timeframes
    assert "15m" in selected_timeframes


def test_portfolio_orchestrator_initialization():
    """Test PortfolioOrchestrator initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create outputs directory structure
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()
        
        # Initialize orchestrator
        orchestrator = PortfolioOrchestrator(outputs_root=outputs_root)
        
        assert orchestrator.outputs_root == outputs_root
        assert orchestrator.portfolio_runs_dir.exists()
        
        # Check that portfolio runs directory was created
        assert (outputs_root / "portfolio" / "runs").exists()


def test_portfolio_orchestrator_select_candidates():
    """Test PortfolioOrchestrator.select_candidates method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a mock evidence index
        index_path = create_mock_evidence_index(tmp_path)
        
        # Initialize orchestrator
        orchestrator = PortfolioOrchestrator(outputs_root=tmp_path)
        
        # Load evidence index
        index = orchestrator.load_evidence_index(index_path)
        
        # Create portfolio run config
        config = PortfolioRunConfigV1(
            portfolio_run_id="test_run",
            portfolio_id="test_portfolio",
            strategy="top_performers",
            max_candidates=3,
            min_candidates=1,
            include_warn=False,
        )
        
        # Select candidates
        selected = orchestrator.select_candidates(
            index=index,
            config=config,
            manual_job_ids=None,
        )
        
        # Should select PASS jobs only (exclude WARN and FAIL)
        assert len(selected) <= 3  # max_candidates
        assert len(selected) >= 1  # at least one
        
        # Verify selected jobs are PASS
        for job_id in selected:
            job_summary = index.jobs[job_id]
            assert job_summary.gate_status == GateStatus.PASS
            assert job_summary.lifecycle == JobLifecycle.ACTIVE
            assert "strategy_report_v1.json" in job_summary.artifacts_present


def test_portfolio_orchestrator_manual_strategy():
    """Test PortfolioOrchestrator with manual strategy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a mock evidence index
        index_path = create_mock_evidence_index(tmp_path)
        
        # Initialize orchestrator
        orchestrator = PortfolioOrchestrator(outputs_root=tmp_path)
        
        # Load evidence index
        index = orchestrator.load_evidence_index(index_path)
        
        # Create portfolio run config with manual strategy
        config = PortfolioRunConfigV1(
            portfolio_run_id="test_run",
            portfolio_id="test_portfolio",
            strategy="manual",
            max_candidates=5,
            min_candidates=1,
            include_warn=True,
        )
        
        # Manual job IDs (mix of PASS, WARN, FAIL)
        manual_job_ids = ["job_001", "job_004", "job_007"]  # PASS, WARN, FAIL
        
        # Select candidates
        selected = orchestrator.select_candidates(
            index=index,
            config=config,
            manual_job_ids=manual_job_ids,
        )
        
        # Should select manual jobs that pass filters
        # job_007 is FAIL and include_fail=False by default, so it should be excluded
        assert len(selected) == 2  # job_001 (PASS) and job_004 (WARN with include_warn=True)
        assert "job_001" in selected
        assert "job_004" in selected
        assert "job_007" not in selected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])