
"""Contract tests for artifact system.

Tests verify:
1. Directory structure contract
2. File existence and format
3. JSON serialization correctness (sorted keys)
4. param_subsample_rate visibility (mandatory in manifest/metrics/README)
5. Winners schema stability
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from FishBroWFS_V2.core.artifacts import write_run_artifacts
from FishBroWFS_V2.core.audit_schema import AuditSchema, compute_params_effective
from FishBroWFS_V2.core.config_hash import stable_config_hash
from FishBroWFS_V2.core.paths import ensure_run_dir, get_run_dir
from FishBroWFS_V2.core.run_id import make_run_id


def test_artifact_tree_contract():
    """Test that artifact directory structure follows contract."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        run_id = make_run_id()
        
        run_dir = ensure_run_dir(outputs_root, season, run_id)
        
        # Verify directory structure
        expected_path = outputs_root / "seasons" / season / "runs" / run_id
        assert run_dir == expected_path
        assert expected_path.exists()
        assert expected_path.is_dir()
        
        # Verify get_run_dir returns same path
        assert get_run_dir(outputs_root, season, run_id) == expected_path


def test_manifest_must_include_param_subsample_rate():
    """Test that manifest.json must include param_subsample_rate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        config = {"n_bars": 1000, "n_params": 100}
        param_subsample_rate = 0.1
        params_total = 100
        params_effective = compute_params_effective(params_total, param_subsample_rate)
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=param_subsample_rate,
            config_hash=stable_config_hash(config),
            season=season,
            dataset_id="test_dataset",
            bars=1000,
            params_total=params_total,
            params_effective=params_effective,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot=config,
            metrics={"param_subsample_rate": param_subsample_rate},
        )
        
        # Read and verify manifest
        manifest_path = run_dir / "manifest.json"
        assert manifest_path.exists()
        
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        
        # Verify param_subsample_rate exists and is correct
        assert "param_subsample_rate" in manifest_data
        assert manifest_data["param_subsample_rate"] == 0.1
        
        # Verify all audit fields are present
        assert "run_id" in manifest_data
        assert "created_at" in manifest_data
        assert "git_sha" in manifest_data
        assert "dirty_repo" in manifest_data
        assert "config_hash" in manifest_data


def test_config_snapshot_is_json_serializable():
    """Test that config_snapshot.json is valid JSON with sorted keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        config = {
            "n_bars": 1000,
            "n_params": 100,
            "commission": 0.0,
            "slip": 0.0,
        }
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=1.0,
            config_hash=stable_config_hash(config),
            season=season,
            dataset_id="test_dataset",
            bars=1000,
            params_total=100,
            params_effective=100,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot=config,
            metrics={"param_subsample_rate": 1.0},
        )
        
        config_path = run_dir / "config_snapshot.json"
        assert config_path.exists()
        
        # Verify JSON is valid and has sorted keys
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        # Verify keys are sorted (JSON should be written with sort_keys=True)
        keys = list(config_data.keys())
        assert keys == sorted(keys), "Config keys should be sorted"
        
        # Verify content matches
        assert config_data == config


def test_metrics_must_include_param_subsample_rate():
    """Test that metrics.json must include param_subsample_rate visibility."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        param_subsample_rate = 0.25
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=param_subsample_rate,
            config_hash="test_hash",
            season=season,
            dataset_id="test_dataset",
            bars=20000,
            params_total=1000,
            params_effective=250,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        metrics = {
            "param_subsample_rate": param_subsample_rate,
            "runtime_s": 12.345,
            "throughput": 27777777.78,
        }
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot={"test": "config"},
            metrics=metrics,
        )
        
        metrics_path = run_dir / "metrics.json"
        assert metrics_path.exists()
        
        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)
        
        # Verify param_subsample_rate exists
        assert "param_subsample_rate" in metrics_data
        assert metrics_data["param_subsample_rate"] == 0.25


def test_winners_structure_contract():
    """Test that winners.json has fixed structure versioned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=1.0,
            config_hash="test_hash",
            season=season,
            dataset_id="test_dataset",
            bars=1000,
            params_total=100,
            params_effective=100,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot={"test": "config"},
            metrics={"param_subsample_rate": 1.0},
        )
        
        winners_path = run_dir / "winners.json"
        assert winners_path.exists()
        
        with open(winners_path, "r", encoding="utf-8") as f:
            winners_data = json.load(f)
        
        # Verify fixed structure
        assert "topk" in winners_data
        assert isinstance(winners_data["topk"], list)
        
        # Verify schema version (v1 or v2)
        notes = winners_data.get("notes", {})
        schema = notes.get("schema")
        assert schema in ("v1", "v2"), f"Schema must be v1 or v2, got {schema}"
        
        # If v2, must include 'schema' at top level too
        if schema == "v2":
            assert winners_data.get("schema") == "v2"
        
        assert winners_data["topk"] == []  # Initially empty


def test_readme_must_display_param_subsample_rate():
    """Test that README.md prominently displays param_subsample_rate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        param_subsample_rate = 0.33
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=param_subsample_rate,
            config_hash="test_hash_123",
            season=season,
            dataset_id="test_dataset",
            bars=20000,
            params_total=1000,
            params_effective=330,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot={"test": "config"},
            metrics={"param_subsample_rate": param_subsample_rate},
        )
        
        readme_path = run_dir / "README.md"
        assert readme_path.exists()
        
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_content = f.read()
        
        # Verify param_subsample_rate is prominently displayed
        assert "param_subsample_rate" in readme_content
        assert "0.33" in readme_content
        
        # Verify other required fields
        assert "run_id" in readme_content
        assert "git_sha" in readme_content
        assert "season" in readme_content
        assert "dataset_id" in readme_content
        assert "bars" in readme_content
        assert "params_total" in readme_content
        assert "params_effective" in readme_content
        assert "config_hash" in readme_content


def test_logs_file_exists():
    """Test that logs.txt file is created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=1.0,
            config_hash="test_hash",
            season=season,
            dataset_id="test_dataset",
            bars=1000,
            params_total=100,
            params_effective=100,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot={"test": "config"},
            metrics={"param_subsample_rate": 1.0},
        )
        
        logs_path = run_dir / "logs.txt"
        assert logs_path.exists()
        
        # Initially empty
        with open(logs_path, "r", encoding="utf-8") as f:
            assert f.read() == ""


def test_all_artifacts_exist():
    """Test that all required artifacts are created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=0.1,
            config_hash="test_hash",
            season=season,
            dataset_id="test_dataset",
            bars=20000,
            params_total=1000,
            params_effective=100,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot={"test": "config"},
            metrics={"param_subsample_rate": 0.1},
        )
        
        # Verify all artifacts exist
        artifacts = [
            "manifest.json",
            "config_snapshot.json",
            "metrics.json",
            "winners.json",
            "README.md",
            "logs.txt",
        ]
        
        for artifact_name in artifacts:
            artifact_path = run_dir / artifact_name
            assert artifact_path.exists(), f"Missing artifact: {artifact_name}"


def test_json_files_have_sorted_keys():
    """Test that all JSON files are written with sorted keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        season = "test_season"
        
        config = {
            "z_field": "last",
            "a_field": "first",
            "m_field": "middle",
        }
        
        audit = AuditSchema(
            run_id=make_run_id(),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="a1b2c3d4e5f6",
            dirty_repo=False,
            param_subsample_rate=1.0,
            config_hash=stable_config_hash(config),
            season=season,
            dataset_id="test_dataset",
            bars=1000,
            params_total=100,
            params_effective=100,
        )
        
        run_dir = ensure_run_dir(outputs_root, season, audit.run_id)
        
        write_run_artifacts(
            run_dir=run_dir,
            manifest=audit.to_dict(),
            config_snapshot=config,
            metrics={"param_subsample_rate": 1.0},
        )
        
        # Check config_snapshot.json has sorted keys
        config_path = run_dir / "config_snapshot.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        keys = list(config_data.keys())
        assert keys == sorted(keys), "Config keys should be sorted"
        
        # Check manifest.json has sorted keys
        manifest_path = run_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        
        manifest_keys = list(manifest_data.keys())
        assert manifest_keys == sorted(manifest_keys), "Manifest keys should be sorted"


