
"""Tests for research extract module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from FishBroWFS_V2.research.extract import extract_canonical_metrics, ExtractionError
from FishBroWFS_V2.research.metrics import CanonicalMetrics


def test_extract_canonical_metrics_success(tmp_path: Path) -> None:
    """Test successful extraction of canonical metrics."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    
    # Create manifest.json
    manifest = {
        "run_id": "test-run-123",
        "bars": 1000,
        "created_at": "2025-01-01T00:00:00Z",
    }
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    
    # Create metrics.json
    metrics_data = {
        "stage_name": "stage2_confirm",
    }
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f)
    
    # Create winners.json with topk
    winners = {
        "schema": "v2",
        "stage_name": "stage2_confirm",
        "topk": [
            {
                "candidate_id": "test:1",
                "strategy_id": "donchian_atr",
                "symbol": "CME.MNQ",
                "timeframe": "60m",
                "metrics": {
                    "net_profit": 100.0,
                    "max_dd": -50.0,
                    "trades": 10,
                },
                "score": 100.0,
            },
            {
                "candidate_id": "test:2",
                "strategy_id": "donchian_atr",
                "symbol": "CME.MNQ",
                "timeframe": "60m",
                "metrics": {
                    "net_profit": 50.0,
                    "max_dd": -20.0,
                    "trades": 5,
                },
                "score": 50.0,
            },
        ],
    }
    with open(run_dir / "winners.json", "w", encoding="utf-8") as f:
        json.dump(winners, f)
    
    # Extract metrics
    metrics = extract_canonical_metrics(run_dir)
    
    # Verify
    assert metrics.run_id == "test-run-123"
    assert metrics.bars == 1000
    assert metrics.trades == 15  # 10 + 5
    assert metrics.net_profit == 150.0  # 100 + 50
    assert metrics.max_drawdown == 50.0  # abs(-50)
    assert metrics.start_date == "2025-01-01T00:00:00Z"
    assert metrics.strategy_id == "donchian_atr"
    assert metrics.symbol == "CME.MNQ"
    assert metrics.timeframe_min == 60
    assert metrics.score_net_mdd == 150.0 / 50.0  # net_profit / max_drawdown
    assert metrics.score_final > 0  # score_net_mdd * (trades ** 0.25)


def test_extract_canonical_metrics_missing_artifacts(tmp_path: Path) -> None:
    """Test extraction fails when no artifacts exist."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    
    # No artifacts
    with pytest.raises(ExtractionError, match="No artifacts found"):
        extract_canonical_metrics(run_dir)


def test_extract_canonical_metrics_missing_run_id(tmp_path: Path) -> None:
    """Test extraction fails when run_id is missing."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    
    # Create manifest without run_id
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"bars": 100}, f)
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    
    # Should raise ExtractionError
    with pytest.raises(ExtractionError, match="Missing 'run_id'"):
        extract_canonical_metrics(run_dir)


def test_extract_canonical_metrics_missing_bars(tmp_path: Path) -> None:
    """Test extraction fails when bars is missing."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    
    # Create manifest without bars
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"run_id": "test"}, f)
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    
    # Should raise ExtractionError
    with pytest.raises(ExtractionError, match="Missing 'bars'"):
        extract_canonical_metrics(run_dir)


def test_extract_canonical_metrics_zero_drawdown_with_profit(tmp_path: Path) -> None:
    """Test extraction raises when max_drawdown is 0 but net_profit is non-zero."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    
    manifest = {
        "run_id": "test-run",
        "bars": 1000,
        "created_at": "2025-01-01T00:00:00Z",
    }
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    
    winners = {
        "schema": "v2",
        "topk": [
            {
                "candidate_id": "test:1",
                "metrics": {
                    "net_profit": 100.0,
                    "max_dd": 0.0,  # Zero drawdown
                    "trades": 10,
                },
            },
        ],
    }
    with open(run_dir / "winners.json", "w", encoding="utf-8") as f:
        json.dump(winners, f)
    
    # Should raise ExtractionError
    with pytest.raises(ExtractionError, match="cannot calculate score_net_mdd"):
        extract_canonical_metrics(run_dir)


def test_extract_canonical_metrics_no_trades(tmp_path: Path) -> None:
    """Test extraction with no trades."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    
    manifest = {
        "run_id": "test-run-no-trades",
        "bars": 1000,
        "created_at": "2025-01-01T00:00:00Z",
    }
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    
    winners = {
        "schema": "v2",
        "topk": [
            {
                "candidate_id": "test:1",
                "metrics": {
                    "net_profit": 0.0,
                    "max_dd": 0.0,
                    "trades": 0,
                },
            },
        ],
    }
    with open(run_dir / "winners.json", "w", encoding="utf-8") as f:
        json.dump(winners, f)
    
    # Extract metrics
    metrics = extract_canonical_metrics(run_dir)
    
    # Verify zero metrics
    assert metrics.trades == 0
    assert metrics.net_profit == 0.0
    assert metrics.max_drawdown == 0.0
    assert metrics.score_net_mdd == 0.0
    assert metrics.score_final == 0.0


