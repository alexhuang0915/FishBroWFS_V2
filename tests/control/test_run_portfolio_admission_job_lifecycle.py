"""
Test RUN_PORTFOLIO_ADMISSION job lifecycle.

Assertions:
- Submit job → DB state = QUEUED
- Handler is registered
- Parameter validation
- Handler smoke test with stub results
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime, timezone

from control.supervisor import submit, get_job
from control.supervisor.db import SupervisorDB, get_default_db_path
from control.supervisor.job_handler import get_handler


def test_submit_run_portfolio_admission_job():
    """Test submitting a RUN_PORTFOLIO_ADMISSION job."""
    # Clean up any existing test jobs
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        conn.execute("DELETE FROM jobs WHERE job_type = 'RUN_PORTFOLIO_ADMISSION'")
    
    # Create temporary result files
    with tempfile.TemporaryDirectory() as tmpdir:
        result_paths = []
        for i in range(2):
            result_path = Path(tmpdir) / f"result_{i}.json"
            
            # Create minimal valid result JSON
            result_data = {
                "version": "1.0",
                "meta": {
                    "job_id": f"test_job_{i}",
                    "run_at": datetime.now(timezone.utc).isoformat(),
                    "strategy_family": "S1",
                    "instrument": "MNQ",
                    "timeframe": "60m",
                    "start_season": "2023Q1",
                    "end_season": "2026Q1",
                    "window_rule": {"is_years": 3, "oos_quarters": 1, "rolling": "quarterly"},
                },
                "config": {
                    "instrument": {
                        "symbol": "MNQ",
                        "exchange": "CME",
                        "currency": "USD",
                        "multiplier": 2.0,
                    },
                    "costs": {
                        "commission": {"model": "per_trade", "value": 2.5, "unit": "USD"},
                        "slippage": {"model": "ticks", "value": 0.5, "unit": "ticks"},
                    },
                    "risk": {
                        "risk_unit_1R": 100.0,
                        "stop_model": "atr",
                    },
                    "data": {
                        "data1": "MNQ",
                        "data2": None,
                        "timeframe": "60m",
                        "actual_time_range": {
                            "start": "2023-01-01T00:00:00Z",
                            "end": "2026-01-01T00:00:00Z",
                        },
                    },
                },
                "estimate": {
                    "strategy_count": 5,
                    "param_count": 100,
                    "window_count": 12,
                    "workers": 4,
                    "estimated_runtime_sec": 3600,
                },
                "windows": [
                    {
                        "season": "2025Q4",
                        "is_range": {"start": "2022-10-01T00:00:00Z", "end": "2025-09-30T23:59:59Z"},
                        "oos_range": {"start": "2025-10-01T00:00:00Z", "end": "2025-12-31T23:59:59Z"},
                        "best_params": {"param1": 1.5},
                        "is_metrics": {"net": 1500.0, "mdd": -200.0, "trades": 45},
                        "oos_metrics": {"net": 300.0, "mdd": -50.0, "trades": 12},
                        "pass": True,
                        "fail_reasons": [],
                    }
                ],
                "series": {
                    "stitched_is_equity": [{"t": "2023-01-01T00:00:00Z", "v": 0.0}],
                    "stitched_oos_equity": [{"t": "2023-01-01T00:00:00Z", "v": 0.0}],
                    "stitched_bnh_equity": [{"t": "2023-01-01T00:00:00Z", "v": 0.0}],
                    "stitch_diagnostics": {
                        "per_season": [
                            {"season": "2025Q4", "jump_abs": 0.0, "jump_pct": 0.0}
                        ]
                    },
                    "drawdown_series": [],
                },
                "metrics": {
                    "raw": {
                        "rf": 2.5,
                        "wfe": 0.3,
                        "ecr": 2.0,
                        "trades": 57,
                        "pass_rate": 0.8,
                        "ulcer_index": 15.2,
                        "max_underwater_days": 10,
                    },
                    "scores": {
                        "profit": 62.5,
                        "stability": 58.0,
                        "robustness": 40.0,
                        "reliability": 28.5,
                        "armor": 76.0,
                        "total_weighted": 55.8,
                    },
                    "hard_gates_triggered": [],
                },
                "verdict": {
                    "grade": "B",
                    "is_tradable": True,
                    "summary": "Strategy passes all hard gates with moderate scores.",
                },
            }
            
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result_data, f)
            
            result_paths.append(str(result_path))
        
        # Submit job
        payload = {
            "portfolio_id": "test_portfolio_123",
            "result_paths": result_paths,
            "portfolio_config": {
                "name": "Test Portfolio",
                "description": "Test portfolio for admission analysis",
                "target_volatility": 0.15,
                "max_drawdown_limit_pct": 20.0,
                "correlation_threshold": 0.7,
            }
        }
        
        job_id = submit("RUN_PORTFOLIO_ADMISSION", payload)
        
        # Verify job was created
        job = get_job(job_id)
        assert job is not None
        assert job.job_id == job_id
        assert job.job_type == "RUN_PORTFOLIO_ADMISSION"
        assert job.state == "QUEUED"
        
        # Verify payload
        spec_dict = json.loads(job.spec_json)
        assert spec_dict["job_type"] == "RUN_PORTFOLIO_ADMISSION"
        assert spec_dict["params"]["portfolio_id"] == "test_portfolio_123"
        assert len(spec_dict["params"]["result_paths"]) == 2
        
        print(f"✓ Job submitted: {job_id}")


def test_run_portfolio_admission_handler_registered():
    """Test that RUN_PORTFOLIO_ADMISSION handler is registered."""
    handler = get_handler("RUN_PORTFOLIO_ADMISSION")
    assert handler is not None
    assert hasattr(handler, "validate_params")
    assert hasattr(handler, "execute")
    
    print("✓ RUN_PORTFOLIO_ADMISSION handler is registered")


def test_parameter_validation():
    """Test parameter validation for portfolio admission."""
    from control.supervisor.handlers.run_portfolio_admission import RunPortfolioAdmissionHandler
    
    handler = RunPortfolioAdmissionHandler()
    
    # Valid parameters
    valid_params = {
        "portfolio_id": "test_portfolio",
        "result_paths": ["/path/to/result1.json", "/path/to/result2.json"],
    }
    
    handler.validate_params(valid_params)
    
    # Missing required parameters
    with pytest.raises(ValueError, match="Missing required parameters"):
        handler.validate_params({})
    
    with pytest.raises(ValueError, match="Missing required parameters"):
        handler.validate_params({"portfolio_id": "test"})
    
    with pytest.raises(ValueError, match="Missing required parameters"):
        handler.validate_params({"result_paths": []})
    
    # Invalid result_paths type
    with pytest.raises(ValueError, match="result_paths must be a list"):
        handler.validate_params({
            "portfolio_id": "test",
            "result_paths": "not_a_list",
        })
    
    # Empty result_paths
    with pytest.raises(ValueError, match="At least one result.json file"):
        handler.validate_params({
            "portfolio_id": "test",
            "result_paths": [],
        })
    
    print("✓ Parameter validation passed")


@patch('control.supervisor.handlers.run_portfolio_admission.RunPortfolioAdmissionHandler._load_results')
@patch('control.supervisor.handlers.run_portfolio_admission.RunPortfolioAdmissionHandler._build_portfolio_config')
@patch('control.supervisor.handlers.run_portfolio_admission.RunPortfolioAdmissionHandler._run_correlation_analysis')
@patch('control.supervisor.handlers.run_portfolio_admission.RunPortfolioAdmissionHandler._determine_admission')
@patch('control.supervisor.handlers.run_portfolio_admission.RunPortfolioAdmissionHandler._write_artifacts')
def test_handler_smoke_stub_results(
    mock_write_artifacts,
    mock_determine_admission,
    mock_run_correlation_analysis,
    mock_build_portfolio_config,
    mock_load_results
):
    """Stub results returns deterministic admission decision."""
    from control.supervisor.handlers.run_portfolio_admission import RunPortfolioAdmissionHandler
    from contracts.portfolio.admission_schemas import AdmissionDecision, AdmissionVerdict
    
    # Mock the handler methods
    mock_load_results.return_value = {
        "job_1": MagicMock(),
        "job_2": MagicMock(),
    }
    
    mock_build_portfolio_config.return_value = {
        "portfolio_id": "test_portfolio",
        "name": "Test Portfolio",
        "currency": "USD",
        "correlation_threshold": 0.7,
    }
    
    mock_run_correlation_analysis.return_value = {
        "passed": True,
        "violations": [],
        "threshold": 0.7,
        "total_pairs": 1,
        "violating_pairs": 0,
    }
    
    mock_determine_admission.return_value = (
        ["job_1"],  # admitted_run_ids
        ["job_2"],  # rejected_run_ids
        {"job_2": "High correlation"}  # reasons
    )
    
    handler = RunPortfolioAdmissionHandler()
    
    # Test parameter validation
    params = {
        "portfolio_id": "test_portfolio",
        "result_paths": ["/path/to/result1.json", "/path/to/result2.json"],
        "portfolio_config": {
            "name": "Test Portfolio",
            "target_volatility": 0.15,
        }
    }
    
    handler.validate_params(params)
    
    # Mock job context
    mock_context = MagicMock()
    mock_context.job_id = "test_job_123"
    mock_context.artifacts_dir = "/tmp/test/artifacts"
    mock_context.is_abort_requested.return_value = False
    mock_context.heartbeat = MagicMock()
    
    # Test execution
    result = handler.execute(params, mock_context)
    
    assert result["ok"] is True
    assert result["job_type"] == "RUN_PORTFOLIO_ADMISSION"
    assert "payload" in result
    assert "result" in result
    
    # Verify result has expected structure
    result_data = result["result"]
    assert "portfolio_id" in result_data
    assert "admitted_runs" in result_data
    assert "rejected_runs" in result_data
    assert "verdict" in result_data
    assert "summary" in result_data
    
    assert result_data["portfolio_id"] == "test_portfolio"
    assert result_data["admitted_runs"] == 1
    assert result_data["rejected_runs"] == 1
    
    print("✓ Handler smoke test with stub results passed")


if __name__ == "__main__":
    # Run tests
    test_submit_run_portfolio_admission_job()
    test_run_portfolio_admission_handler_registered()
    test_parameter_validation()
    test_handler_smoke_stub_results()
    print("\n✅ All portfolio admission tests passed!")
