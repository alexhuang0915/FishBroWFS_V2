
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.pipeline.funnel_runner import run_funnel
from src.pipeline.funnel_schema import FunnelPlan, StageSpec, StageName

@patch("src.pipeline.funnel_runner.run_stage_job")
@patch("src.pipeline.funnel_runner.write_run_artifacts")
@patch("src.pipeline.funnel_runner.AuditSchema")
def test_run_funnel_propagates_plateau_candidates(mock_audit_schema, mock_write_artifacts, mock_run_stage_job, tmp_path):
    """Verify run_funnel passes plateau_candidates from stage_out to write_run_artifacts."""
    
    # Mock FunnelPlan with one stage
    plan = FunnelPlan(stages=[
        StageSpec(name=StageName.STAGE1_TOPK, param_subsample_rate=0.1, topk=10)
    ])
    
    # Mock Stage Output
    mock_plateau_candidates = [{"param_id": 1, "score": 100.0}]
    mock_run_stage_job.return_value = {
        "metrics": {"total": 100.0},
        "winners": {"topk": [], "notes": {"schema": "v1"}},
        "plateau_candidates": mock_plateau_candidates
    }
    
    # Mock Audit
    mock_audit_schema.return_value.to_dict.return_value = {"run_id": "test_run"}
    
    # Run
    outputs_root = tmp_path / "outputs"
    cfg = {
        "param_subsample_rate": 0.1,
        "params_matrix": MagicMock(),
        "strategy_id": "S1",
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "season": "2025",
        "dataset_id": "CME.MNQ",
        "timeframe": "60m",
        "bars": 100,
        "params_total": 1000,
    }
    
    with patch("src.pipeline.funnel_runner.build_default_funnel_plan", return_value=plan):
        run_funnel(cfg, outputs_root)
    
    # Verify write_run_artifacts was called with plateau_candidates
    assert mock_write_artifacts.called
    args, kwargs = mock_write_artifacts.call_args
    assert "plateau_candidates" in kwargs
    assert kwargs["plateau_candidates"] == mock_plateau_candidates
