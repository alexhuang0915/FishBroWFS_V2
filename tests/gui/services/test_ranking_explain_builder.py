"""
Test ranking explain builder.

Ensure:
1. Basic report generation from winners data
2. Context-aware wording
3. Plateau artifact gating
4. File loading functions
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from datetime import datetime

from contracts.ranking_explain import (
    RankingExplainContext,
    RankingExplainReasonCode,
    RankingExplainReport,
)
from gui.services.ranking_explain_builder import (
    build_ranking_explain_report,
    build_and_write_ranking_explain_report,
    load_winners_from_file,
    load_plateau_report_from_file,
)
from wfs.scoring_guards import ScoringGuardConfig


def test_load_winners_from_file(tmp_path):
    """Test loading winners from file."""
    # Create test winners data
    winners_data = {
        "topk": [
            {
                "strategy_id": "strategy_001",
                "params_fingerprint": "fp1",
                "final_score": 1.2345,
                "metrics": {
                    "net_profit": 123456.0,
                    "max_dd": -34567.0,
                    "trades": 420,
                    "avg_profit_per_trade": 294.0
                }
            },
            {
                "strategy_id": "strategy_002",
                "params_fingerprint": "fp2",
                "final_score": 1.1234,
                "metrics": {
                    "net_profit": 98765.0,
                    "max_dd": -23456.0,
                    "trades": 350,
                    "avg_profit_per_trade": 282.0
                }
            }
        ],
        "metadata": {
            "stage_name": "wfs_candidate",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    # Write to file
    winners_file = tmp_path / "winners.json"
    winners_file.write_text(json.dumps(winners_data, indent=2), encoding="utf-8")
    
    # Load from file
    loaded = load_winners_from_file(tmp_path)
    
    assert loaded is not None
    assert "topk" in loaded
    assert len(loaded["topk"]) == 2
    assert loaded["topk"][0]["strategy_id"] == "strategy_001"
    assert loaded["topk"][1]["strategy_id"] == "strategy_002"
    
    # Test with non-existent file
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    loaded = load_winners_from_file(empty_dir)
    assert loaded is None


def test_load_plateau_report_from_file(tmp_path):
    """Test loading plateau report from file."""
    # Create test plateau data
    plateau_data = {
        "stability_score": 0.85,
        "parameter_neighborhood": {
            "radius": 0.1,
            "samples": 50
        },
        "performance_consistency": 0.92
    }
    
    # Write to file
    plateau_file = tmp_path / "plateau_report.json"
    plateau_file.write_text(json.dumps(plateau_data, indent=2), encoding="utf-8")
    
    # Load from file
    loaded = load_plateau_report_from_file(tmp_path)
    
    assert loaded is not None
    assert "stability_score" in loaded
    assert loaded["stability_score"] == 0.85
    assert "parameter_neighborhood" in loaded
    
    # Test with non-existent file
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    loaded = load_plateau_report_from_file(empty_dir)
    assert loaded is None


def test_build_ranking_explain_report_basic():
    """Test basic report generation."""
    # Create mock winners data
    winners_data = {
        "topk": [
            {
                "strategy_id": "strategy_001",
                "params_fingerprint": "fp1",
                "final_score": 1.2345,
                "metrics": {
                    "net_profit": 123456.0,
                    "max_dd": -34567.0,
                    "trades": 420,
                    "avg_profit_per_trade": 294.0
                }
            },
            {
                "strategy_id": "strategy_002",
                "params_fingerprint": "fp2",
                "final_score": 1.1234,
                "metrics": {
                    "net_profit": 98765.0,
                    "max_dd": -23456.0,
                    "trades": 350,
                    "avg_profit_per_trade": 282.0
                }
            }
        ],
        "metadata": {
            "stage_name": "wfs_candidate",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    # Build report with CANDIDATE context
    report = build_ranking_explain_report(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        winners=winners_data,
        plateau_report=None,
        scoring_guard_cfg=ScoringGuardConfig(),
    )
    
    assert isinstance(report, RankingExplainReport)
    assert report.schema_version == "1"
    assert report.context == RankingExplainContext.CANDIDATE
    assert report.job_id == "test_job_123"
    assert "formula" in report.scoring
    assert len(report.reasons) > 0
    
    # Check reason cards
    reason_codes = [card.code for card in report.reasons]
    # Should have at least SCORE_FORMULA and METRIC_SUMMARY
    assert RankingExplainReasonCode.SCORE_FORMULA in reason_codes
    assert RankingExplainReasonCode.METRIC_SUMMARY in reason_codes
    # Should have DATA_MISSING_PLATEAU_ARTIFACT since plateau_report is None
    assert RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT in reason_codes
    
    # Check that scoring details are included
    assert "t_max" in report.scoring
    assert "alpha" in report.scoring
    assert report.scoring["t_max"] == 100  # Default from ScoringGuardConfig
    assert report.scoring["alpha"] == 0.25  # Default from ScoringGuardConfig


def test_build_ranking_explain_report_with_plateau():
    """Test report generation with plateau artifact."""
    winners_data = {
        "topk": [
            {
                "strategy_id": "strategy_001",
                "params_fingerprint": "fp1",
                "final_score": 1.2345,
                "metrics": {
                    "net_profit": 123456.0,
                    "max_dd": -34567.0,
                    "trades": 420,
                    "avg_profit_per_trade": 294.0
                }
            }
        ],
        "metadata": {
            "stage_name": "wfs_final_selection",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    plateau_data = {
        "stability_score": 0.85,
        "parameter_neighborhood": {
            "radius": 0.1,
            "samples": 50
        }
    }
    
    # Build report with FINAL_SELECTION context and plateau artifact
    report = build_ranking_explain_report(
        context=RankingExplainContext.FINAL_SELECTION,
        job_id="test_job_123",
        winners=winners_data,
        plateau_report=plateau_data,
        scoring_guard_cfg=ScoringGuardConfig(),
    )
    
    assert report.context == RankingExplainContext.FINAL_SELECTION
    assert report.job_id == "test_job_123"
    
    # Check that plateau-related reason card is included
    reason_codes = [card.code for card in report.reasons]
    # Should have PLATEAU_CONFIRMED since plateau artifact exists
    assert RankingExplainReasonCode.PLATEAU_CONFIRMED in reason_codes
    # Should NOT have DATA_MISSING_PLATEAU_ARTIFACT
    assert RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT not in reason_codes
    
    # Check context-aware wording in title
    for card in report.reasons:
        if card.code == RankingExplainReasonCode.PLATEAU_CONFIRMED:
            # Title should mention plateau stability
            assert "plateau" in card.title.lower() or "stability" in card.title.lower()
            # Should have Chinese annotation for FINAL_SELECTION (勝出)
            assert "勝出" in card.title


def test_build_ranking_explain_report_threshold_reasons():
    """Test threshold reason cards generation."""
    # Create winners with trades > t_max (100)
    winners_data = {
        "topk": [
            {
                "strategy_id": "strategy_001",
                "params_fingerprint": "fp1",
                "final_score": 1.2345,
                "metrics": {
                    "net_profit": 123456.0,
                    "max_dd": -34567.0,  # Negative value for drawdown
                    "trades": 420,  # > t_max=100
                    "avg_profit_per_trade": 294.0  # > min_avg_profit=5.0
                }
            }
        ],
        "metadata": {
            "stage_name": "wfs_candidate",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    report = build_ranking_explain_report(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        winners=winners_data,
        plateau_report=None,
        scoring_guard_cfg=ScoringGuardConfig(),
    )
    
    reason_codes = [card.code for card in report.reasons]
    # Should have THRESHOLD_TMAX_APPLIED since trades > t_max
    assert RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED in reason_codes
    # Should have THRESHOLD_MIN_AVG_PROFIT_APPLIED since avg_profit > min_avg_profit
    assert RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED in reason_codes
    
    # Check details in threshold reason cards
    for card in report.reasons:
        if card.code == RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED:
            assert "trades" in card.details
            assert card.details["trades"] == 420
            assert card.details["t_max"] == 100
            assert card.details["capped_trades"] == 100
        elif card.code == RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED:
            assert "avg_profit" in card.details
            # avg_profit = net_profit / trades = 123456.0 / 420 = 293.9428571428571
            assert card.details["avg_profit"] == pytest.approx(123456.0 / 420)
            assert card.details["min_avg_profit"] == 5.0


def test_build_ranking_explain_report_no_topk():
    """Test report generation with no topk data."""
    # Empty winners data
    winners_data = {
        "topk": [],
        "metadata": {
            "stage_name": "wfs_candidate",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    report = build_ranking_explain_report(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        winners=winners_data,
        plateau_report=None,
        scoring_guard_cfg=ScoringGuardConfig(),
    )
    
    assert isinstance(report, RankingExplainReport)
    assert report.context == RankingExplainContext.CANDIDATE
    
    # Should still have SCORE_FORMULA reason
    reason_codes = [card.code for card in report.reasons]
    assert RankingExplainReasonCode.SCORE_FORMULA in reason_codes
    # Should NOT have METRIC_SUMMARY since no topk items
    assert RankingExplainReasonCode.METRIC_SUMMARY not in reason_codes
    # Should have DATA_MISSING_PLATEAU_ARTIFACT
    assert RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT in reason_codes


def test_build_ranking_explain_report_missing_metrics():
    """Test report generation with missing metrics."""
    winners_data = {
        "topk": [
            {
                "strategy_id": "strategy_001",
                "params_fingerprint": "fp1",
                "final_score": 1.2345,
                "metrics": {
                    # Missing net_profit, max_dd, trades
                }
            }
        ],
        "metadata": {
            "stage_name": "wfs_candidate",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    report = build_ranking_explain_report(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        winners=winners_data,
        plateau_report=None,
        scoring_guard_cfg=ScoringGuardConfig(),
    )
    
    assert isinstance(report, RankingExplainReport)
    
    # Should have METRIC_SUMMARY but with default values
    has_metric_summary = False
    for card in report.reasons:
        if card.code == RankingExplainReasonCode.METRIC_SUMMARY:
            has_metric_summary = True
            # Details should have default values
            assert "net_profit" in card.details
            assert card.details["net_profit"] == 0.0
            assert "max_dd" in card.details
            assert card.details["max_dd"] == 0.0
            assert "trades" in card.details
            assert card.details["trades"] == 0
            break
    
    assert has_metric_summary


def test_build_and_write_ranking_explain_report(tmp_path):
    """Test building and writing report to file."""
    job_dir = tmp_path / "job_123"
    job_dir.mkdir()
    
    # Create winners.json
    winners_data = {
        "topk": [
            {
                "strategy_id": "strategy_001",
                "params_fingerprint": "fp1",
                "final_score": 1.2345,
                "metrics": {
                    "net_profit": 123456.0,
                    "max_dd": -34567.0,
                    "trades": 420,
                    "avg_profit_per_trade": 294.0
                }
            }
        ],
        "metadata": {
            "stage_name": "wfs_candidate",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    winners_file = job_dir / "winners.json"
    winners_file.write_text(json.dumps(winners_data, indent=2), encoding="utf-8")
    
    # Build and write report
    success = build_and_write_ranking_explain_report(
        job_dir=job_dir,
        context=RankingExplainContext.CANDIDATE,
        scoring_guard_cfg=ScoringGuardConfig(),
    )
    
    assert success is True
    
    # Check that report was written with canonical filename ranking_explain_report.json
    report_file = job_dir / "ranking_explain_report.json"
    assert report_file.exists()
    
    # Load and validate report
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["schema_version"] == "1"
    assert report_data["context"] == "CANDIDATE"
    assert report_data["job_id"] == "job_123"
    assert len(report_data["reasons"]) > 0
    
    # Check that reasons are sorted by code
    reason_codes = [r["code"] for r in report_data["reasons"]]
    assert sorted(reason_codes) == reason_codes  # Should be sorted


def test_build_and_write_ranking_explain_report_with_plateau(tmp_path):
    """Test building and writing report with plateau artifact."""
    job_dir = tmp_path / "job_123"
    job_dir.mkdir()
    
    # Create winners.json
    winners_data = {
        "topk": [
            {
                "strategy_id": "strategy_001",
                "params_fingerprint": "fp1",
                "final_score": 1.2345,
                "metrics": {
                    "net_profit": 123456.0,
                    "max_dd": -34567.0,
                    "trades": 420,
                    "avg_profit_per_trade": 294.0
                }
            }
        ],
        "metadata": {
            "stage_name": "wfs_final_selection",
            "generated_at": "2026-01-16T00:00:00Z"
        }
    }
    
    winners_file = job_dir / "winners.json"
    winners_file.write_text(json.dumps(winners_data, indent=2), encoding="utf-8")
    
    # Create plateau_report.json
    plateau_data = {
        "stability_score": 0.85,
        "parameter_neighborhood": {
            "radius": 0.1,
            "samples": 50
        }
    }
    
    plateau_file = job_dir / "plateau_report.json"
    plateau_file.write_text(json.dumps(plateau_data, indent=2), encoding="utf-8")
    
    # Build and write report
    success = build_and_write_ranking_explain_report(
        job_dir=job_dir,
        context=RankingExplainContext.FINAL_SELECTION,
        scoring_guard_cfg=ScoringGuardConfig(),
    )
    
    assert success is True
    
    # Check that report was written with canonical filename ranking_explain_report.json
    report_file = job_dir / "ranking_explain_report.json"
    assert report_file.exists()
    
    # Load and validate report
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["context"] == "FINAL_SELECTION"
    
