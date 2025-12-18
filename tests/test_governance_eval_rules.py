"""Contract tests for governance evaluation rules.

Tests that governance rules (R1/R2/R3) are correctly applied using fixture artifacts.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

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


def _create_fake_winners(stage_name: str, topk_items: list[dict]) -> dict:
    """Create fake winners.json."""
    return {
        "topk": topk_items,
        "notes": {
            "schema": "v1",
            "stage": stage_name,
            "topk_count": len(topk_items),
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


def test_r1_drop_when_stage2_missing() -> None:
    """
    Test R1: DROP when candidate in Stage1 but missing in Stage2.
    
    Scenario:
    - Stage1 has candidate with param_id=0
    - Stage2 does not have candidate with param_id=0
    - Expected: DROP with reason "unverified"
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Stage0 artifacts
        stage0_dir = tmp_path / "stage0"
        _write_artifacts(
            stage0_dir,
            _create_fake_manifest("stage0-123", "stage0_coarse"),
            _create_fake_metrics("stage0_coarse"),
            _create_fake_winners("stage0_coarse", [{"param_id": 0, "proxy_value": 1.0}]),
            _create_fake_config_snapshot(),
        )
        
        # Stage1 artifacts (has candidate)
        stage1_dir = tmp_path / "stage1"
        stage1_winners = _create_fake_winners(
            "stage1_topk",
            [{"param_id": 0, "net_profit": 100.0, "trades": 10, "max_dd": -10.0}],
        )
        _write_artifacts(
            stage1_dir,
            _create_fake_manifest("stage1-123", "stage1_topk"),
            _create_fake_metrics("stage1_topk"),
            stage1_winners,
            _create_fake_config_snapshot(),
        )
        
        # Stage2 artifacts (missing candidate)
        stage2_dir = tmp_path / "stage2"
        stage2_winners = _create_fake_winners(
            "stage2_confirm",
            [{"param_id": 1, "net_profit": 200.0, "trades": 20, "max_dd": -20.0}],  # Different param_id
        )
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
        
        # Verify: candidate should be DROP
        assert len(report.items) == 1
        item = report.items[0]
        assert item.decision == Decision.DROP
        assert any("R1" in reason for reason in item.reasons)
        assert any("unverified" in reason.lower() for reason in item.reasons)


def test_r2_drop_when_metric_degrades_over_threshold() -> None:
    """
    Test R2: DROP when metrics degrade > 20% from Stage1 to Stage2.
    
    Scenario:
    - Stage1: net_profit=100, max_dd=-10 -> net_over_mdd = 10.0
    - Stage2: net_profit=70, max_dd=-10 -> net_over_mdd = 7.0
    - Degradation: (10.0 - 7.0) / 10.0 = 0.30 (30% > 20% threshold)
    - Expected: DROP with reason "degraded"
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Stage0 artifacts
        stage0_dir = tmp_path / "stage0"
        _write_artifacts(
            stage0_dir,
            _create_fake_manifest("stage0-123", "stage0_coarse"),
            _create_fake_metrics("stage0_coarse"),
            _create_fake_winners("stage0_coarse", [{"param_id": 0, "proxy_value": 1.0}]),
            _create_fake_config_snapshot(),
        )
        
        # Stage1 artifacts
        stage1_dir = tmp_path / "stage1"
        stage1_winners = _create_fake_winners(
            "stage1_topk",
            [{"param_id": 0, "net_profit": 100.0, "trades": 10, "max_dd": -10.0}],
        )
        _write_artifacts(
            stage1_dir,
            _create_fake_manifest("stage1-123", "stage1_topk"),
            _create_fake_metrics("stage1_topk"),
            stage1_winners,
            _create_fake_config_snapshot(),
        )
        
        # Stage2 artifacts (degraded metrics)
        stage2_dir = tmp_path / "stage2"
        stage2_winners = _create_fake_winners(
            "stage2_confirm",
            [{"param_id": 0, "net_profit": 70.0, "trades": 10, "max_dd": -10.0}],  # 30% degradation
        )
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
        
        # Verify: candidate should be DROP
        assert len(report.items) == 1
        item = report.items[0]
        assert item.decision == Decision.DROP
        assert any("R2" in reason for reason in item.reasons)
        assert any("degraded" in reason.lower() for reason in item.reasons)


def test_r3_freeze_when_density_over_threshold() -> None:
    """
    Test R3: FREEZE when same strategy_id appears >= 3 times in Stage1 topk.
    
    Scenario:
    - Stage1 has 5 candidates with same strategy_id (donchian_atr)
    - Expected: FREEZE with reason "density"
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Stage0 artifacts
        stage0_dir = tmp_path / "stage0"
        _write_artifacts(
            stage0_dir,
            _create_fake_manifest("stage0-123", "stage0_coarse"),
            _create_fake_metrics("stage0_coarse"),
            _create_fake_winners("stage0_coarse", [{"param_id": i, "proxy_value": 1.0} for i in range(5)]),
            _create_fake_config_snapshot(),
        )
        
        # Stage1 artifacts (5 candidates)
        stage1_dir = tmp_path / "stage1"
        stage1_winners = _create_fake_winners(
            "stage1_topk",
            [
                {"param_id": i, "net_profit": 100.0 + i, "trades": 10, "max_dd": -10.0}
                for i in range(5)
            ],
        )
        _write_artifacts(
            stage1_dir,
            _create_fake_manifest("stage1-123", "stage1_topk"),
            _create_fake_metrics("stage1_topk"),
            stage1_winners,
            _create_fake_config_snapshot(),
        )
        
        # Stage2 artifacts (all candidates present)
        stage2_dir = tmp_path / "stage2"
        stage2_winners = _create_fake_winners(
            "stage2_confirm",
            [
                {"param_id": i, "net_profit": 100.0 + i, "trades": 10, "max_dd": -10.0}
                for i in range(5)
            ],
        )
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
        
        # Verify: all candidates should be FREEZE (density >= 3)
        assert len(report.items) == 5
        for item in report.items:
            assert item.decision == Decision.FREEZE
            assert any("R3" in reason for reason in item.reasons)
            assert any("density" in reason.lower() for reason in item.reasons)


def test_keep_when_all_rules_pass() -> None:
    """
    Test KEEP when all rules pass.
    
    Scenario:
    - R1: Stage2 has candidate (pass)
    - R2: Metrics do not degrade (pass)
    - R3: Density < threshold (pass)
    - Expected: KEEP
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Stage0 artifacts
        stage0_dir = tmp_path / "stage0"
        _write_artifacts(
            stage0_dir,
            _create_fake_manifest("stage0-123", "stage0_coarse"),
            _create_fake_metrics("stage0_coarse"),
            _create_fake_winners("stage0_coarse", [{"param_id": 0, "proxy_value": 1.0}]),
            _create_fake_config_snapshot(),
        )
        
        # Stage1 artifacts (single candidate, low density)
        stage1_dir = tmp_path / "stage1"
        stage1_winners = _create_fake_winners(
            "stage1_topk",
            [{"param_id": 0, "net_profit": 100.0, "trades": 10, "max_dd": -10.0}],
        )
        _write_artifacts(
            stage1_dir,
            _create_fake_manifest("stage1-123", "stage1_topk"),
            _create_fake_metrics("stage1_topk"),
            stage1_winners,
            _create_fake_config_snapshot(),
        )
        
        # Stage2 artifacts (same metrics, no degradation)
        stage2_dir = tmp_path / "stage2"
        stage2_winners = _create_fake_winners(
            "stage2_confirm",
            [{"param_id": 0, "net_profit": 100.0, "trades": 10, "max_dd": -10.0}],
        )
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
        
        # Verify: candidate should be KEEP
        assert len(report.items) == 1
        item = report.items[0]
        assert item.decision == Decision.KEEP
