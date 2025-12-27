
"""Contract tests for artifacts winners v2 writing.

Tests verify that write_run_artifacts automatically upgrades legacy winners to v2.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.artifacts import write_run_artifacts
from core.audit_schema import AuditSchema, compute_params_effective
from core.config_hash import stable_config_hash
from core.run_id import make_run_id
from core.winners_schema import is_winners_v2


def test_artifacts_upgrades_legacy_winners_to_v2() -> None:
    """Test that write_run_artifacts upgrades legacy winners to v2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run_test"
        
        # Create audit schema
        config = {"n_bars": 1000, "n_params": 100}
        param_subsample_rate = 0.1
        params_total = 100
        params_effective = compute_params_effective(params_total, param_subsample_rate)
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="abc123def456",
            dirty_repo=False,
            param_subsample_rate=param_subsample_rate,
            config_hash=stable_config_hash(config),
            season="test_season",
            dataset_id="test_dataset",
            bars=1000,
            params_total=params_total,
            params_effective=params_effective,
        )
        
        # Legacy winners format
        legacy_winners = {
            "topk": [
                {"param_id": 0, "net_profit": 100.0, "trades": 10, "max_dd": -10.0},
                {"param_id": 1, "net_profit": 200.0, "trades": 20, "max_dd": -20.0},
            ],
            "notes": {"schema": "v1"},
        }
        
        # Write artifacts
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot=config,
            metrics={
                "param_subsample_rate": param_subsample_rate,
                "stage_name": "stage1_topk",
            },
            winners=legacy_winners,
        )
        
        # Read winners.json
        winners_path = run_dir / "winners.json"
        assert winners_path.exists()
        
        with winners_path.open("r", encoding="utf-8") as f:
            winners = json.load(f)
        
        # Verify it's v2 schema
        assert is_winners_v2(winners) is True
        assert winners["schema"] == "v2"
        assert winners["stage_name"] == "stage1_topk"
        
        # Verify topk items are v2 format
        topk = winners["topk"]
        assert len(topk) == 2
        
        for item in topk:
            assert "candidate_id" in item
            assert "strategy_id" in item
            assert "symbol" in item
            assert "timeframe" in item
            assert "params" in item
            assert "score" in item
            assert "metrics" in item
            assert "source" in item
            
            # Verify legacy fields are in metrics
            metrics = item["metrics"]
            assert "net_profit" in metrics
            assert "max_dd" in metrics
            assert "trades" in metrics
            assert "param_id" in metrics


def test_artifacts_writes_v2_when_winners_is_none() -> None:
    """Test that write_run_artifacts creates v2 format when winners is None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run_test"
        
        # Create audit schema
        config = {"n_bars": 1000, "n_params": 100}
        param_subsample_rate = 0.1
        params_total = 100
        params_effective = compute_params_effective(params_total, param_subsample_rate)
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="abc123def456",
            dirty_repo=False,
            param_subsample_rate=param_subsample_rate,
            config_hash=stable_config_hash(config),
            season="test_season",
            dataset_id="test_dataset",
            bars=1000,
            params_total=params_total,
            params_effective=params_effective,
        )
        
        # Write artifacts with winners=None
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot=config,
            metrics={
                "param_subsample_rate": param_subsample_rate,
                "stage_name": "stage0_coarse",
            },
            winners=None,
        )
        
        # Read winners.json
        winners_path = run_dir / "winners.json"
        assert winners_path.exists()
        
        with winners_path.open("r", encoding="utf-8") as f:
            winners = json.load(f)
        
        # Verify it's v2 schema (even when empty)
        assert is_winners_v2(winners) is True
        assert winners["schema"] == "v2"
        assert winners["topk"] == []


def test_artifacts_preserves_legacy_metrics_fields() -> None:
    """Test that legacy metrics fields are preserved in v2 format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run_test"
        
        # Create audit schema
        config = {"n_bars": 1000, "n_params": 100}
        param_subsample_rate = 0.1
        params_total = 100
        params_effective = compute_params_effective(params_total, param_subsample_rate)
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="abc123def456",
            dirty_repo=False,
            param_subsample_rate=param_subsample_rate,
            config_hash=stable_config_hash(config),
            season="test_season",
            dataset_id="test_dataset",
            bars=1000,
            params_total=params_total,
            params_effective=params_effective,
        )
        
        # Legacy winners with proxy_value (Stage0)
        legacy_winners = {
            "topk": [
                {"param_id": 0, "proxy_value": 1.234},
            ],
            "notes": {"schema": "v1"},
        }
        
        # Write artifacts
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot=config,
            metrics={
                "param_subsample_rate": param_subsample_rate,
                "stage_name": "stage0_coarse",
            },
            winners=legacy_winners,
        )
        
        # Read winners.json
        winners_path = run_dir / "winners.json"
        with winners_path.open("r", encoding="utf-8") as f:
            winners = json.load(f)
        
        # Verify legacy fields are preserved
        item = winners["topk"][0]
        metrics = item["metrics"]
        
        # proxy_value should be in metrics
        assert "proxy_value" in metrics
        assert metrics["proxy_value"] == 1.234
        
        # param_id should be in metrics (for backward compatibility)
        assert "param_id" in metrics
        assert metrics["param_id"] == 0


