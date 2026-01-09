"""
Test RUN_RESEARCH_WFS job lifecycle.

Assertions:
- Submit job → DB state = QUEUED
- Handler is registered
- Result schema shape validation
- Hard gates evaluation
- Scoring formulas exact
- Stitching offsets
- B&H baseline required present
- Handler smoke test with stub engine
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime, timezone

from src.control.supervisor import submit, get_job
from src.control.supervisor.db import SupervisorDB, get_default_db_path
from src.control.supervisor.job_handler import get_handler

# Import WFS modules
from src.contracts.research_wfs.result_schema import (
    ResearchWFSResult,
    MetaSection as Meta,
    ConfigSection as Config,
    EstimateSection as Estimate,
    WindowResult as Window,
    SeriesSection as Series,
    MetricsSection as Metrics,
    VerdictSection as Verdict,
)
from src.wfs.evaluation import (
    compute_hard_gates,
    compute_scores,
    compute_total,
    grade_from_total,
    evaluate,
    EvaluationResult,
)
from src.wfs.stitching import stitch_equity_series
from src.wfs.bnh_baseline import compute_bnh_equity_for_range


def test_submit_run_research_wfs_job():
    """Test submitting a RUN_RESEARCH_WFS job."""
    # Clean up any existing test jobs
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        conn.execute("DELETE FROM jobs WHERE job_type = 'RUN_RESEARCH_WFS'")
    
    # Submit job
    payload = {
        "strategy_id": "S1",
        "instrument": "MNQ",
        "timeframe": "60m",
        "run_mode": "wfs",
        "season": "2026Q1",
        "start_season": "2023Q1",
        "end_season": "2026Q1",
    }
    
    job_id = submit("RUN_RESEARCH_WFS", payload)
    
    # Verify job was created
    job = get_job(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.job_type == "RUN_RESEARCH_WFS"
    assert job.state == "QUEUED"
    
    # Verify payload
    spec_dict = json.loads(job.spec_json)
    assert spec_dict["job_type"] == "RUN_RESEARCH_WFS"
    assert spec_dict["params"] == payload
    
    print(f"✓ Job submitted: {job_id}")


def test_run_research_wfs_handler_registered():
    """Test that RUN_RESEARCH_WFS handler is registered."""
    handler = get_handler("RUN_RESEARCH_WFS")
    assert handler is not None
    assert hasattr(handler, "validate_params")
    assert hasattr(handler, "execute")
    
    print("✓ RUN_RESEARCH_WFS handler is registered")


def test_result_schema_shape():
    """Validate required keys exist and types are correct."""
    # Create a minimal valid result
    result = ResearchWFSResult(
        version="1.0",
        meta=Meta(
            job_id="test_job_123",
            run_at=datetime.now(timezone.utc).isoformat(),
            strategy_family="S1",
            instrument="MNQ",
            timeframe="60m",
            start_season="2023Q1",
            end_season="2026Q1",
            window_rule={"is_years": 3, "oos_quarters": 1, "rolling": "quarterly"},
        ),
        config=Config(
            instrument={
                "symbol": "MNQ",
                "exchange": "CME",
                "currency": "USD",
                "multiplier": 2.0,
            },
            costs={
                "commission": {"model": "per_trade", "value": 2.5, "unit": "USD"},
                "slippage": {"model": "ticks", "value": 0.5, "unit": "ticks"},
            },
            risk={
                "risk_unit_1R": 100.0,
                "stop_model": "atr",
            },
            data={
                "data1": "MNQ",
                "data2": None,
                "timeframe": "60m",
                "actual_time_range": {
                    "start": "2023-01-01T00:00:00Z",
                    "end": "2026-01-01T00:00:00Z",
                },
            },
        ),
        estimate=Estimate(
            strategy_count=5,
            param_count=100,
            window_count=12,
            workers=4,
            estimated_runtime_sec=3600,
        ),
        windows=[
            Window(
                season="2025Q4",
                is_range={"start": "2022-10-01T00:00:00Z", "end": "2025-09-30T23:59:59Z"},
                oos_range={"start": "2025-10-01T00:00:00Z", "end": "2025-12-31T23:59:59Z"},
                best_params={"param1": 1.5},
                is_metrics={"net": 1500.0, "mdd": -200.0, "trades": 45},
                oos_metrics={"net": 300.0, "mdd": -50.0, "trades": 12},
                pass_=True,  # Note: using pass_ with alias "pass"
                fail_reasons=[],
            )
        ],
        series=Series(
            stitched_is_equity=[{"t": "2023-01-01T00:00:00Z", "v": 0.0}],
            stitched_oos_equity=[{"t": "2023-01-01T00:00:00Z", "v": 0.0}],
            stitched_bnh_equity=[{"t": "2023-01-01T00:00:00Z", "v": 0.0}],
            stitch_diagnostics={
                "per_season": [
                    {"season": "2025Q4", "jump_abs": 0.0, "jump_pct": 0.0}
                ]
            },
            drawdown_series=[],
        ),
        metrics=Metrics(
            raw={
                "rf": 2.5,
                "wfe": 0.3,
                "ecr": 2.0,
                "trades": 57,
                "pass_rate": 0.8,
                "ulcer_index": 15.2,
                "max_underwater_days": 10,
            },
            scores={
                "profit": 62.5,
                "stability": 58.0,
                "robustness": 40.0,
                "reliability": 28.5,
                "armor": 76.0,
                "total_weighted": 55.8,
            },
            hard_gates_triggered=[],
        ),
        verdict=Verdict(
            grade="B",
            is_tradable=True,
            summary="Strategy passes all hard gates with moderate scores.",
        ),
    )
    
    # Convert to dict and validate JSON serialization
    result_dict = result.model_dump()
    
    # Check required top-level keys
    required_keys = ["version", "meta", "config", "estimate", "windows", "series", "metrics", "verdict"]
    for key in required_keys:
        assert key in result_dict, f"Missing required key: {key}"
    
    # Check types
    assert isinstance(result_dict["version"], str)
    assert isinstance(result_dict["meta"], dict)
    assert isinstance(result_dict["config"], dict)
    assert isinstance(result_dict["estimate"], dict)
    assert isinstance(result_dict["windows"], list)
    assert isinstance(result_dict["series"], dict)
    assert isinstance(result_dict["metrics"], dict)
    assert isinstance(result_dict["verdict"], dict)
    
    # Check meta fields
    meta = result_dict["meta"]
    assert "job_id" in meta
    assert "run_at" in meta
    assert "strategy_family" in meta
    assert "instrument" in meta
    assert "timeframe" in meta
    assert "start_season" in meta
    assert "end_season" in meta
    assert "window_rule" in meta
    
    # Check series has B&H baseline
    series = result_dict["series"]
    assert "stitched_bnh_equity" in series
    assert isinstance(series["stitched_bnh_equity"], list)
    
    print("✓ Result schema shape validation passed")


def test_hard_gates():
    """Each gate forces grade='D' and is_tradable=false."""
    # Test ECR < 1.5 gate
    raw1 = {
        "rf": 3.0,
        "wfe": 0.4,
        "ecr": 1.2,  # Triggers ECR < 1.5 gate
        "trades": 100,
        "pass_rate": 0.8,
        "ulcer_index": 10.0,
        "max_underwater_days": 5,
    }
    
    gates1 = compute_hard_gates(raw1)
    assert "ECR < 1.5" in gates1
    
    eval1 = evaluate(raw1)
    assert eval1.grade == "D"
    assert not eval1.is_tradable
    assert "HardGate:" in eval1.summary
    
    # Test WFE < 0.5 gate
    raw2 = {
        "rf": 3.0,
        "wfe": 0.3,  # Triggers WFE < 0.5 gate
        "ecr": 2.0,
        "trades": 100,
        "pass_rate": 0.8,
        "ulcer_index": 10.0,
        "max_underwater_days": 5,
    }
    
    gates2 = compute_hard_gates(raw2)
    assert "WFE < 0.5" in gates2
    
    # Test PassRate < 0.6 gate
    raw3 = {
        "rf": 3.0,
        "wfe": 0.6,
        "ecr": 2.0,
        "trades": 100,
        "pass_rate": 0.5,  # Triggers PassRate < 0.6 gate
        "ulcer_index": 10.0,
        "max_underwater_days": 5,
    }
    
    gates3 = compute_hard_gates(raw3)
    assert "PassRate < 0.6" in gates3
    
    # Test TotalTrades < 30 gate
    raw4 = {
        "rf": 3.0,
        "wfe": 0.6,
        "ecr": 2.0,
        "trades": 25,  # Triggers TotalTrades < 30 gate
        "pass_rate": 0.8,
        "ulcer_index": 10.0,
        "max_underwater_days": 5,
    }
    
    gates4 = compute_hard_gates(raw4)
    assert "TotalTrades < 30" in gates4
    
    # Test no gates triggered but low total score (should still be D)
    raw5 = {
        "rf": 3.0,
        "wfe": 0.6,
        "ecr": 2.0,
        "trades": 100,
        "pass_rate": 0.8,
        "ulcer_index": 10.0,
        "max_underwater_days": 5,
    }
    
    gates5 = compute_hard_gates(raw5)
    assert len(gates5) == 0
    
    eval5 = evaluate(raw5)
    # Total score is 58.75 < 60, so grade should be D even without hard gates
    assert eval5.grade == "D"
    assert not eval5.is_tradable  # Grade D means not tradable
    
    # Test no gates triggered with high total score (should be better grade)
    raw6 = {
        "rf": 4.0,  # Higher RF for better profit score
        "wfe": 0.8,  # Higher WFE but still > 0.5 (no hard gate)
        "ecr": 4.0,  # Higher ECR
        "trades": 200,  # More trades
        "pass_rate": 0.9,  # Higher pass rate
        "ulcer_index": 5.0,  # Lower ulcer
        "max_underwater_days": 10,
    }
    
    gates6 = compute_hard_gates(raw6)
    assert len(gates6) == 0
    
    eval6 = evaluate(raw6)
    # Should have grade better than D (likely B or A depending on scores)
    assert eval6.grade != "D"
    assert eval6.is_tradable
    
    print("✓ Hard gates evaluation passed")


def test_scoring_formulas_exact():
    """Verify normalization math exact, weights exact."""
    raw = {
        "rf": 3.0,  # RF = 3.0
        "wfe": 0.6,  # WFE = 0.6
        "ecr": 2.5,  # ECR = 2.5
        "trades": 150,  # Trades = 150
        "pass_rate": 0.8,  # PassRate = 0.8
        "ulcer_index": 12.0,  # Ulcer = 12.0
        "max_underwater_days": 15,  # Underwater days = 15
    }
    
    scores = compute_scores(raw)
    
    # Expected calculations:
    # profit = min(100, (RF / 4.0) * 100) = min(100, (3.0 / 4.0) * 100) = min(100, 75.0) = 75.0
    assert abs(scores["profit"] - 75.0) < 0.001
    
    # stability = clamp(60*WFE + 40*PassRate, 0, 100) = clamp(60*0.6 + 40*0.8, 0, 100) = clamp(36 + 32, 0, 100) = 68.0
    assert abs(scores["stability"] - 68.0) < 0.001
    
    # robustness = min(100, (ECR / 5.0) * 100) = min(100, (2.5 / 5.0) * 100) = min(100, 50.0) = 50.0
    assert abs(scores["robustness"] - 50.0) < 0.001
    
    # reliability = min(100, (Trades / 200) * 100) = min(100, (150 / 200) * 100) = min(100, 75.0) = 75.0
    assert abs(scores["reliability"] - 75.0) < 0.001
    
    # armor = clamp(100 - 5*ulcer_index - 2*max(0, underwater_days-20), 0, 100)
    # = clamp(100 - 5*12.0 - 2*max(0, 15-20), 0, 100) = clamp(100 - 60 - 2*0, 0, 100) = 40.0
    assert abs(scores["armor"] - 40.0) < 0.001
    
    # Check weights
    total = compute_total(scores)
    # Expected: 0.25*75 + 0.20*40 + 0.25*68 + 0.20*50 + 0.10*75 = 18.75 + 8.0 + 17.0 + 10.0 + 7.5 = 61.25
    assert abs(total - 61.25) < 0.001
    
    print("✓ Scoring formulas exact verification passed")


def test_stitching_offsets():
    """Two-season synthetic series: verify stitched values exact."""
    # Create synthetic equity series for two seasons
    season1 = [
        {"t": "2023-01-01T00:00:00Z", "v": 0.0},
        {"t": "2023-01-02T00:00:00Z", "v": 100.0},
        {"t": "2023-01-03T00:00:00Z", "v": 150.0},  # season ends at 150
    ]
    
    season2 = [
        {"t": "2024-01-01T00:00:00Z", "v": 0.0},
        {"t": "2024-01-02T00:00:00Z", "v": 50.0},
        {"t": "2024-01-03T00:00:00Z", "v": 75.0},  # season ends at 75
    ]
    
    by_season = [season1, season2]
    
    stitched, diags = stitch_equity_series(by_season)
    
    # Expected stitching:
    # Season 1: starts at 0, ends at 150
    # Season 2: should start at 150 (last_end), so values become:
    #   point1: 150 + 0 = 150
    #   point2: 150 + 50 = 200
    #   point3: 150 + 75 = 225
    
    assert len(stitched) == 6  # 3 points per season
    
    # Check season 1 points (unchanged)
    assert stitched[0]["t"] == "2023-01-01T00:00:00Z"
    assert stitched[0]["v"] == 0.0
    
    assert stitched[1]["t"] == "2023-01-02T00:00:00Z"
    assert stitched[1]["v"] == 100.0
    
    assert stitched[2]["t"] == "2023-01-03T00:00:00Z"
    assert stitched[2]["v"] == 150.0
    
    # Check season 2 points (offset by 150)
    assert stitched[3]["t"] == "2024-01-01T00:00:00Z"
    assert stitched[3]["v"] == 150.0  # 150 + 0
    assert stitched[4]["t"] == "2024-01-02T00:00:00Z"
    assert stitched[4]["v"] == 200.0  # 150 + 50
    
    assert stitched[5]["t"] == "2024-01-03T00:00:00Z"
    assert stitched[5]["v"] == 225.0  # 150 + 75
    
    # Check diagnostics
    assert len(diags) == 2
    assert diags[0]["season"] == "season_0"
    assert diags[0]["jump_abs"] == 0.0  # First season starts at 0
    assert diags[0]["jump_pct"] == 0.0
    
    assert diags[1]["season"] == "season_1"
    assert diags[1]["jump_abs"] == 0.0  # Season 2 starts at 0 relative to itself
    assert diags[1]["jump_pct"] == 0.0  # last_end_before = 150, jump_abs = 0, so 0/150 = 0
    
    print("✓ Stitching offsets verification passed")


def test_bnh_required_present():
    """result.json includes stitched_bnh_equity and is non-empty for stub case."""
    from src.wfs.bnh_baseline import PriceSeries, CostModel
    
    # Create a simple price series
    timestamps = [
        "2023-01-01T00:00:00Z",
        "2023-01-02T00:00:00Z",
        "2023-01-03T00:00:00Z",
    ]
    close_prices = [100.0, 102.0, 101.0]
    open_prices = [99.5, 101.5, 100.5]
    
    price_series = PriceSeries(
        timestamps=timestamps,
        close_prices=close_prices,
        open_prices=open_prices
    )
    
    # Create cost model
    cost_model = CostModel(
        commission_per_trade=2.5,
        slippage_ticks=0.5,
        tick_value=0.25,
        multiplier=2.0
    )
    
    # Test compute_bnh_equity_for_range
    bnh_series = compute_bnh_equity_for_range(
        price_series=price_series,
        cost_model=cost_model,
        initial_capital=10000.0,
        position_size=1.0
    )
    
    assert isinstance(bnh_series, list)
    assert len(bnh_series) == 3
    for point in bnh_series:
        assert "t" in point
        assert "v" in point
        assert isinstance(point["t"], str)
        assert isinstance(point["v"], float)
    
    # First point should be near 0 (linear interpolation starts at 0)
    assert abs(bnh_series[0]["v"]) < 0.01
    
    print("✓ B&H baseline required present verification passed")


@patch('src.control.supervisor.handlers.run_research_wfs.RunResearchWFSHandler._execute_wfs_windows')
def test_handler_smoke_stub_engine(mock_execute_windows):
    """Stub engine returns deterministic metrics/equity for 2 seasons."""
    from src.control.supervisor.handlers.run_research_wfs import RunResearchWFSHandler
    from src.contracts.research_wfs.result_schema import WindowResult, TimeRange
    
    # Create mock window results
    mock_window = WindowResult(
        season="2025Q4",
        is_range=TimeRange(start="2022-10-01T00:00:00Z", end="2025-09-30T23:59:59Z"),
        oos_range=TimeRange(start="2025-10-01T00:00:00Z", end="2025-12-31T23:59:59Z"),
        best_params={"param1": 1.5},
        is_metrics={"net": 1500.0, "mdd": -200.0, "trades": 45},
        oos_metrics={"net": 300.0, "mdd": -50.0, "trades": 12},
        pass_=True,
        fail_reasons=[],
    )
    
    # Create mock equity series
    mock_is_equity = [{"t": "2023-01-01T00:00:00Z", "v": 0.0}]
    mock_oos_equity = [{"t": "2023-01-01T00:00:00Z", "v": 0.0}]
    mock_bnh_equity = [{"t": "2023-01-01T00:00:00Z", "v": 0.0}]
    
    # Mock the _execute_wfs_windows method to return deterministic data
    mock_execute_windows.return_value = (
        [mock_window],  # windows
        [mock_is_equity],  # is_equity_by_season
        [mock_oos_equity],  # oos_equity_by_season
        [mock_bnh_equity],  # bnh_equity_by_season
    )
    
    # Also mock _aggregate_metrics to return deterministic metrics
    with patch.object(RunResearchWFSHandler, '_aggregate_metrics') as mock_aggregate:
        mock_aggregate.return_value = {
            "rf": 2.5,
            "wfe": 0.3,
            "ecr": 2.0,
            "trades": 57,
            "pass_rate": 0.8,
            "ulcer_index": 15.2,
            "max_underwater_days": 10,
        }
    
    handler = RunResearchWFSHandler()
    
    # Test parameter validation
    params = {
        "strategy_id": "S1",
        "instrument": "MNQ",
        "timeframe": "60m",
        "run_mode": "wfs",
        "season": "2026Q1",
        "start_season": "2023Q1",
        "end_season": "2026Q1",
    }
    
    handler.validate_params(params)
    
    # Mock job context
    mock_context = MagicMock()
    mock_context.job_id = "test_job_123"
    mock_context.artifacts_dir = "/tmp/test/artifacts"
    mock_context.is_abort_requested.return_value = False
    mock_context.heartbeat = MagicMock()
    mock_context.artifact_writer = MagicMock()
    
    # Test execution
    result = handler.execute(params, mock_context)
    
    assert result["ok"] is True
    assert result["job_type"] == "RUN_RESEARCH_WFS"
    assert "payload" in result
    assert "result" in result
    
    # Verify result has expected structure
    result_data = result["result"]
    assert "version" in result_data
    assert result_data["version"] == "1.0"
    assert "meta" in result_data
    assert "config" in result_data
    assert "estimate" in result_data
    assert "windows" in result_data
    assert "series" in result_data
    assert "metrics" in result_data
    assert "verdict" in result_data
    
    # Verify series has B&H baseline
    assert "stitched_bnh_equity" in result_data["series"]
    
    print("✓ Handler smoke test with stub engine passed")


if __name__ == "__main__":
    # Run tests
    test_submit_run_research_wfs_job()
    test_run_research_wfs_handler_registered()
    test_result_schema_shape()
    test_hard_gates()
    test_scoring_formulas_exact()
    test_stitching_offsets()
    test_bnh_required_present()
    test_handler_smoke_stub_engine()
    print("\n✅ All WFS tests passed!")
    
