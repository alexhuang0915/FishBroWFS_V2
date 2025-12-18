"""Contract tests for audit schema.

Tests verify:
1. JSON serialization correctness
2. Run ID format stability
3. Config hash consistency
4. params_effective calculation rule consistency
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from FishBroWFS_V2.core.audit_schema import (
    AuditSchema,
    compute_params_effective,
)
from FishBroWFS_V2.core.config_hash import stable_config_hash
from FishBroWFS_V2.core.run_id import make_run_id


def test_audit_schema_json_serializable():
    """Test that AuditSchema can be serialized to JSON."""
    audit = AuditSchema(
        run_id=make_run_id(),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        git_sha="a1b2c3d4e5f6",
        dirty_repo=False,
        param_subsample_rate=0.1,
        config_hash="f9e8d7c6b5a4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8",
        season="2025Q4",
        dataset_id="synthetic_20k",
        bars=20000,
        params_total=1000,
        params_effective=100,
    )
    
    # Test to_dict()
    audit_dict = audit.to_dict()
    assert isinstance(audit_dict, dict)
    assert "param_subsample_rate" in audit_dict
    
    # Test JSON serialization
    audit_json = json.dumps(audit_dict)
    assert isinstance(audit_json, str)
    
    # Test JSON deserialization
    loaded_dict = json.loads(audit_json)
    assert loaded_dict["param_subsample_rate"] == 0.1
    assert loaded_dict["run_id"] == audit.run_id


def test_run_id_is_stable_format():
    """Test that run_id has stable, parseable format."""
    run_id = make_run_id()
    
    # Verify format: YYYYMMDDTHHMMSSZ-token
    assert len(run_id) > 15  # At least timestamp + dash + token
    assert "T" in run_id  # ISO format separator
    assert "Z" in run_id  # UTC timezone indicator
    assert run_id.count("-") >= 1  # At least one dash before token
    
    # Verify timestamp part is sortable
    parts = run_id.split("-")
    timestamp_part = parts[0] if len(parts) > 1 else run_id.split("Z")[0] + "Z"
    assert len(timestamp_part) >= 15  # YYYYMMDDTHHMMSSZ
    
    # Test with prefix
    prefixed_run_id = make_run_id(prefix="test")
    assert prefixed_run_id.startswith("test-")
    assert "T" in prefixed_run_id
    assert "Z" in prefixed_run_id


def test_config_hash_is_stable():
    """Test that config hash is stable and consistent."""
    config1 = {
        "n_bars": 20000,
        "n_params": 1000,
        "commission": 0.0,
    }
    
    config2 = {
        "commission": 0.0,
        "n_bars": 20000,
        "n_params": 1000,
    }
    
    # Same config with different key order should produce same hash
    hash1 = stable_config_hash(config1)
    hash2 = stable_config_hash(config2)
    assert hash1 == hash2
    
    # Different config should produce different hash
    config3 = {"n_bars": 20001, "n_params": 1000}
    hash3 = stable_config_hash(config3)
    assert hash1 != hash3
    
    # Verify hash format (64 hex chars for SHA256)
    assert len(hash1) == 64
    assert all(c in "0123456789abcdef" for c in hash1)


def test_params_effective_rounding_rule_is_stable():
    """
    Test that params_effective calculation rule is stable and locked.
    
    Rule: int(params_total * param_subsample_rate) (floor)
    """
    # Test cases: (params_total, subsample_rate, expected_effective)
    test_cases = [
        (1000, 0.0, 0),
        (1000, 0.1, 100),
        (1000, 0.15, 150),
        (1000, 0.5, 500),
        (1000, 0.99, 990),
        (1000, 1.0, 1000),
        (100, 0.1, 10),
        (100, 0.33, 33),  # Floor: 33.0 -> 33
        (100, 0.34, 34),  # Floor: 34.0 -> 34
        (100, 0.999, 99),  # Floor: 99.9 -> 99
    ]
    
    for params_total, subsample_rate, expected in test_cases:
        result = compute_params_effective(params_total, subsample_rate)
        assert result == expected, (
            f"Failed for params_total={params_total}, "
            f"subsample_rate={subsample_rate}: "
            f"expected={expected}, got={result}"
        )
    
    # Test edge case: invalid subsample_rate
    with pytest.raises(ValueError):
        compute_params_effective(1000, 1.1)  # > 1.0
    
    with pytest.raises(ValueError):
        compute_params_effective(1000, -0.1)  # < 0.0


def test_manifest_must_include_param_subsample_rate():
    """Test that manifest must include param_subsample_rate."""
    audit = AuditSchema(
        run_id=make_run_id(),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        git_sha="a1b2c3d4e5f6",
        dirty_repo=False,
        param_subsample_rate=0.25,
        config_hash="test_hash",
        season="2025Q4",
        dataset_id="test_dataset",
        bars=20000,
        params_total=1000,
        params_effective=250,
    )
    
    manifest_dict = audit.to_dict()
    
    # Verify param_subsample_rate exists and is correct type
    assert "param_subsample_rate" in manifest_dict
    assert isinstance(manifest_dict["param_subsample_rate"], float)
    assert manifest_dict["param_subsample_rate"] == 0.25
    
    # Verify all required fields exist
    required_fields = [
        "run_id",
        "created_at",
        "git_sha",
        "dirty_repo",
        "param_subsample_rate",
        "config_hash",
        "season",
        "dataset_id",
        "bars",
        "params_total",
        "params_effective",
        "artifact_version",
    ]
    
    for field in required_fields:
        assert field in manifest_dict, f"Missing required field: {field}"


def test_created_at_is_iso8601_utc():
    """Test that created_at uses ISO8601 UTC format with Z suffix."""
    audit = AuditSchema(
        run_id=make_run_id(),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        git_sha="a1b2c3d4e5f6",
        dirty_repo=False,
        param_subsample_rate=0.1,
        config_hash="test_hash",
        season="2025Q4",
        dataset_id="test_dataset",
        bars=20000,
        params_total=1000,
        params_effective=100,
    )
    
    created_at = audit.created_at
    
    # Verify Z suffix (UTC indicator)
    assert created_at.endswith("Z"), f"created_at should end with Z, got: {created_at}"
    
    # Verify ISO8601 format (can parse)
    try:
        # Remove Z and parse
        dt_str = created_at.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(dt_str)
        assert parsed.tzinfo is not None
    except ValueError as e:
        pytest.fail(f"created_at is not valid ISO8601: {created_at}, error: {e}")


def test_audit_schema_is_frozen():
    """Test that AuditSchema is frozen (immutable)."""
    audit = AuditSchema(
        run_id=make_run_id(),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        git_sha="a1b2c3d4e5f6",
        dirty_repo=False,
        param_subsample_rate=0.1,
        config_hash="test_hash",
        season="2025Q4",
        dataset_id="test_dataset",
        bars=20000,
        params_total=1000,
        params_effective=100,
    )
    
    # Verify frozen (cannot modify)
    with pytest.raises(Exception):  # dataclass.FrozenInstanceError
        audit.run_id = "new_id"
