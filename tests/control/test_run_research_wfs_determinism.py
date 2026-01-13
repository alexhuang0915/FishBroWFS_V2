import pytest
import json
from unittest.mock import Mock

from control.supervisor.handlers.run_research_wfs import RunResearchWFSHandler
from control.supervisor.job_handler import JobContext

@pytest.fixture
def mock_context():
    ctx = Mock(spec=JobContext)
    ctx.job_id = "test_job"
    ctx.artifacts_dir = "/tmp/test"
    ctx.heartbeat = Mock()
    ctx.is_abort_requested.return_value = False
    return ctx

@pytest.fixture
def wfs_params():
    return {
        "strategy_id": "S1",
        "instrument": "CME.MNQ",
        "timeframe": "60m",
        "start_season": "2020Q1",
        "end_season": "2021Q1",
        "dataset": "default",
        "run_mode": "wfs",
        "workers": 1
    }

def test_run_research_wfs_determinism(mock_context, wfs_params):
    """
    Same params + context -> identical results (determinism).
    """
    handler = RunResearchWFSHandler()
    
    # Run 1
    result1 = handler.execute(wfs_params, mock_context)
    assert result1["ok"]
    
    # Run 2 (new context to reset state)
    mock_context2 = Mock(spec=JobContext)
    mock_context2.job_id = "test_job2"
    mock_context2.artifacts_dir = "/tmp/test2"
    mock_context2.heartbeat = Mock()
    mock_context2.is_abort_requested.return_value = False
    
    result2 = handler.execute(wfs_params, mock_context2)
    assert result2["ok"]
    
    # Normalize: strip mutable fields (timestamps, job_id)
    def normalize_result(result_dict):
        normalized = result_dict.copy()
        d = normalized["result"]
        # Remove run_at timestamps
        if "meta" in d:
            if "run_at" in d["meta"]:
                del d["meta"]["run_at"]
            if "job_id" in d["meta"]:
                del d["meta"]["job_id"]
        # Recurse for nested
        for key, val in d.items():
            if isinstance(val, dict):
                if "run_at" in val:
                    del val["run_at"]
        return normalized
    
    norm1 = normalize_result(result1)
    norm2 = normalize_result(result2)
    
    # Exact equality (deterministic seed ensures same random sequence)
    assert norm1 == norm2