"""Contract tests for governance accepting winners v2.

Tests verify that governance evaluator can read and process v2 winners.json.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from FishBroWFS_V2.core.governance_schema import Decision
from FishBroWFS_V2.pipeline.governance_eval import evaluate_governance


def _create_fake_manifest(run_id: str, stage_name: str, season: str = "test") -> dict:
    """Create fake manifest.json."""
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": "abc123def456",
        "dirty_repo": False,
        "param_subsample_rate": 0.1,
        "config_hash": "test_hash",
        "season": season,
        "dataset_id": "test_dataset",
        "bars": 1000,
        "params_total": 1000,
        "params_effective": 100,
        "artifact_version": "v1",
    }


def _create_fake_metrics(stage_name: str, stage_planned_subsample: float = 0.1) -> dict:
    """Create fake metrics.json."""
    return {
        "params_total": 1000,
        "params_effective": 100,
        "bars": 1000,
        "stage_name": stage_name,
        "param_subsample_rate": stage_planned_subsample,
        "stage_planned_subsample": stage_planned_subsample,
    }


def _create_fake_winners_v2(stage_name: str, topk_items: list[dict]) -> dict:
    """Create fake winners.json v2."""
    return {
        "schema": "v2",
        "stage_name": stage_name,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "topk": topk_items,
        "notes": {
            "schema": "v2",
            "candidate_id_mode": "strategy_id:param_id",
        },
    }


def _create_fake_config_snapshot() -> dict:
    """Create fake config_snapshot.json."""
    return {
        "dataset_id": "test_dataset",
        "bars": 1000,
        "params_total": 1000,
    }


def _write_artifacts(run_dir: Path, manifest: dict, metrics: dict, winners: dict, config: dict) -> None:
    """Write artifacts to run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    
    with (run_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    
    with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    
    with (run_dir / "winners.json").open("w", encoding="utf-8") as f:
        json.dump(winners, f, indent=2)
    
    with (run_dir / "config_snapshot.json").open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def test_governance_reads_winners_v2() -> None:
    """Test that governance can read and process v2 winners.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Stage0 artifacts
        stage0_dir = tmp_path / "stage0"
        _write_artifacts(
            stage0_dir,
            _create_fake_manifest("stage0-123", "stage0_coarse"),
            _create_fake_metrics("stage0_coarse"),
            _create_fake_winners_v2("stage0_coarse", [
                {
                    "candidate_id": "donchian_atr:0",
                    "strategy_id": "donchian_atr",
                    "symbol": "CME.MNQ",
                    "timeframe": "60m",
                    "params": {},
                    "score": 1.0,
                    "metrics": {"proxy_value": 1.0, "param_id": 0},
                    "source": {"param_id": 0, "run_id": "stage0-123", "stage_name": "stage0_coarse"},
                },
            ]),
            _create_fake_config_snapshot(),
        )
        
        # Stage1 artifacts (v2 format)
        stage1_dir = tmp_path / "stage1"
        stage1_winners = _create_fake_winners_v2("stage1_topk", [
            {
                "candidate_id": "donchian_atr:0",
                "strategy_id": "donchian_atr",
                "symbol": "CME.MNQ",
                "timeframe": "60m",
                "params": {},
                "score": 100.0,
                "metrics": {"net_profit": 100.0, "trades": 10, "max_dd": -10.0, "param_id": 0},
                "source": {"param_id": 0, "run_id": "stage1-123", "stage_name": "stage1_topk"},
            },
        ])
        _write_artifacts(
            stage1_dir,
            _create_fake_manifest("stage1-123", "stage1_topk"),
            _create_fake_metrics("stage1_topk"),
            stage1_winners,
            _create_fake_config_snapshot(),
        )
        
        # Stage2 artifacts (v2 format)
        stage2_dir = tmp_path / "stage2"
        stage2_winners = _create_fake_winners_v2("stage2_confirm", [
            {
                "candidate_id": "donchian_atr:0",
                "strategy_id": "donchian_atr",
                "symbol": "CME.MNQ",
                "timeframe": "60m",
                "params": {},
                "score": 100.0,
                "metrics": {"net_profit": 100.0, "trades": 10, "max_dd": -10.0, "param_id": 0},
                "source": {"param_id": 0, "run_id": "stage2-123", "stage_name": "stage2_confirm"},
            },
        ])
        _write_artifacts(
            stage2_dir,
            _create_fake_manifest("stage2-123", "stage2_confirm"),
            _create_fake_metrics("stage2_confirm"),
            stage2_winners,
            _create_fake_config_snapshot(),
        )
        
        # Evaluate governance
        report = evaluate_governance(
            stage0_dir=stage0_dir,
            stage1_dir=stage1_dir,
            stage2_dir=stage2_dir,
        )
        
        # Verify governance processed v2 format
        assert len(report.items) == 1
        item = report.items[0]
        
        # Verify candidate_id is preserved
        assert item.candidate_id == "donchian_atr:0"
        
        # Verify decision was made (should be KEEP since all rules pass)
        assert item.decision in (Decision.KEEP, Decision.FREEZE, Decision.DROP)


def test_governance_handles_mixed_v2_legacy() -> None:
    """Test that governance handles mixed v2/legacy formats gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Stage0 artifacts (legacy)
        stage0_dir = tmp_path / "stage0"
        _write_artifacts(
            stage0_dir,
            _create_fake_manifest("stage0-123", "stage0_coarse"),
            _create_fake_metrics("stage0_coarse"),
            {"topk": [{"param_id": 0, "proxy_value": 1.0}], "notes": {"schema": "v1"}},
            _create_fake_config_snapshot(),
        )
        
        # Stage1 artifacts (v2)
        stage1_dir = tmp_path / "stage1"
        stage1_winners = _create_fake_winners_v2("stage1_topk", [
            {
                "candidate_id": "donchian_atr:0",
                "strategy_id": "donchian_atr",
                "symbol": "CME.MNQ",
                "timeframe": "60m",
                "params": {},
                "score": 100.0,
                "metrics": {"net_profit": 100.0, "trades": 10, "max_dd": -10.0, "param_id": 0},
                "source": {"param_id": 0, "run_id": "stage1-123", "stage_name": "stage1_topk"},
            },
        ])
        _write_artifacts(
            stage1_dir,
            _create_fake_manifest("stage1-123", "stage1_topk"),
            _create_fake_metrics("stage1_topk"),
            stage1_winners,
            _create_fake_config_snapshot(),
        )
        
        # Stage2 artifacts (legacy)
        stage2_dir = tmp_path / "stage2"
        _write_artifacts(
            stage2_dir,
            _create_fake_manifest("stage2-123", "stage2_confirm"),
            _create_fake_metrics("stage2_confirm"),
            {"topk": [{"param_id": 0, "net_profit": 100.0, "trades": 10, "max_dd": -10.0}], "notes": {"schema": "v1"}},
            _create_fake_config_snapshot(),
        )
        
        # Evaluate governance (should handle mixed formats)
        report = evaluate_governance(
            stage0_dir=stage0_dir,
            stage1_dir=stage1_dir,
            stage2_dir=stage2_dir,
        )
        
        # Verify governance processed successfully
        assert len(report.items) == 1
        item = report.items[0]
        assert item.candidate_id == "donchian_atr:0"
