"""
Gate 16.5‑B: Dataset registry wiring – register snapshot as dataset.

Contract:
- register_snapshot_as_dataset is append‑only (no overwrites)
- Conflict detection: if snapshot already registered → ValueError with "already registered"
- Deterministic dataset_id: snapshot_{symbol}_{timeframe}_{normalized_sha256[:12]}
- Registry entry includes raw_sha256, normalized_sha256, manifest_sha256 chain
"""

import json
import tempfile
from pathlib import Path

import pytest

from control.data_snapshot import create_snapshot
from control.dataset_registry_mutation import (
    register_snapshot_as_dataset,
    _get_dataset_registry_root,
)
from data.dataset_registry import DatasetIndex, DatasetRecord


def test_register_snapshot_as_dataset():
    """Basic registration adds entry to registry."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshots_root = tmp_path / "snapshots"
        snapshots_root.mkdir()
        registry_root = tmp_path / "datasets"
        registry_root.mkdir()

        # Create a snapshot
        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")
        snapshot_dir = snapshots_root / meta.snapshot_id

        # Register
        entry = register_snapshot_as_dataset(snapshot_dir=snapshot_dir, registry_root=registry_root)

        # Verify entry fields (DatasetRecord)
        assert entry.id.startswith("snapshot_TEST_1h_")
        assert entry.symbol == "TEST"
        assert entry.timeframe == "1h"
        # fingerprint_sha1 is derived from normalized_sha256
        assert entry.fingerprint_sha1 == meta.normalized_sha256[:40]

        # Verify registry file exists and contains entry
        registry_file = registry_root / "datasets_index.json"
        assert registry_file.exists()
        registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
        assert "datasets" in registry_data
        datasets = registry_data["datasets"]
        assert any(d["id"] == entry.id for d in datasets)

        # Load via DatasetIndex to validate schema
        index = DatasetIndex.model_validate(registry_data)
        found = [d for d in index.datasets if d.id == entry.id]
        assert len(found) == 1
        assert found[0].symbol == "TEST"


def test_register_snapshot_conflict():
    """Second registration of same snapshot raises ValueError with 'already registered'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshots_root = tmp_path / "snapshots"
        snapshots_root.mkdir()
        registry_root = tmp_path / "datasets"
        registry_root.mkdir()

        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")
        snapshot_dir = snapshots_root / meta.snapshot_id

        # First registration succeeds
        entry1 = register_snapshot_as_dataset(snapshot_dir=snapshot_dir, registry_root=registry_root)

        # Second registration raises ValueError
        with pytest.raises(ValueError, match="already registered"):
            register_snapshot_as_dataset(snapshot_dir=snapshot_dir, registry_root=registry_root)

        # Registry still contains exactly one entry for this snapshot
        registry_file = registry_root / "datasets_index.json"
        registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
        datasets = registry_data["datasets"]
        snapshot_entries = [d for d in datasets if d["id"] == entry1.id]
        assert len(snapshot_entries) == 1


def test_register_snapshot_deterministic_dataset_id():
    """dataset_id is deterministic based on symbol, timeframe, normalized_sha256."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshots_root = tmp_path / "snapshots"
        snapshots_root.mkdir()
        registry_root = tmp_path / "datasets"
        registry_root.mkdir()

        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")
        snapshot_dir = snapshots_root / meta.snapshot_id

        entry = register_snapshot_as_dataset(snapshot_dir=snapshot_dir, registry_root=registry_root)

        # Expected pattern
        expected_prefix = f"snapshot_TEST_1h_{meta.normalized_sha256[:12]}"
        assert entry.id == expected_prefix

        # Same snapshot yields same dataset_id
        # (cannot register twice, but we can compute manually)
        from control.dataset_registry_mutation import _compute_dataset_id
        computed_id = _compute_dataset_id(meta.symbol, meta.timeframe, meta.normalized_sha256)
        assert computed_id == expected_prefix


def test_register_snapshot_appends_to_existing_registry():
    """Registry may already contain other datasets; new entry is appended."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        registry_root = tmp_path / "datasets"
        registry_root.mkdir()

        # Create an existing registry with one dataset
        existing_entry = DatasetRecord(
            id="existing_123",
            symbol="EXISTING",
            exchange="UNKNOWN",
            timeframe="1d",
            path="some/path",
            start_date="2025-01-01",
            end_date="2025-01-31",
            fingerprint_sha1="a" * 40,
            tz_provider="UTC",
            tz_version="unknown",
        )
        existing_index = DatasetIndex(
            generated_at="2025-01-01T00:00:00Z",
            datasets=[existing_entry],
        )
        registry_file = registry_root / "datasets_index.json"
        registry_file.write_text(existing_index.model_dump_json(indent=2), encoding="utf-8")

        # Create a snapshot
        snapshots_root = tmp_path / "snapshots"
        snapshots_root.mkdir()
        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")
        snapshot_dir = snapshots_root / meta.snapshot_id

        # Register snapshot
        entry = register_snapshot_as_dataset(snapshot_dir=snapshot_dir, registry_root=registry_root)

        # Verify registry now contains both entries
        registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
        datasets = registry_data["datasets"]
        assert len(datasets) == 2
        dataset_ids = [d["id"] for d in datasets]
        assert "existing_123" in dataset_ids
        assert entry.id in dataset_ids

        # Order should be preserved (existing first, new appended)
        assert datasets[0]["id"] == "existing_123"
        assert datasets[1]["id"] == entry.id


def test_register_snapshot_missing_manifest():
    """Snapshot directory missing manifest.json raises FileNotFoundError."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshots_root = tmp_path / "snapshots"
        snapshots_root.mkdir()
        registry_root = tmp_path / "datasets"
        registry_root.mkdir()

        # Create a directory that looks like a snapshot but has no manifest
        fake_snapshot_dir = snapshots_root / "fake_snapshot"
        fake_snapshot_dir.mkdir()
        (fake_snapshot_dir / "raw.json").write_text("[]", encoding="utf-8")

        with pytest.raises(FileNotFoundError):
            register_snapshot_as_dataset(snapshot_dir=fake_snapshot_dir, registry_root=registry_root)


def test_register_snapshot_corrupt_manifest():
    """Manifest with invalid JSON raises JSONDecodeError."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshots_root = tmp_path / "snapshots"
        snapshots_root.mkdir()
        registry_root = tmp_path / "datasets"
        registry_root.mkdir()

        fake_snapshot_dir = snapshots_root / "fake_snapshot"
        fake_snapshot_dir.mkdir()
        (fake_snapshot_dir / "manifest.json").write_text("{invalid json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            register_snapshot_as_dataset(snapshot_dir=fake_snapshot_dir, registry_root=registry_root)


def test_register_snapshot_env_override():
    """_get_dataset_registry_root respects environment variable."""
    import os
    with tempfile.TemporaryDirectory() as tmp:
        custom_root = Path(tmp) / "custom_registry"
        custom_root.mkdir()

        # Set environment variable
        os.environ["FISHBRO_DATASET_REGISTRY_ROOT"] = str(custom_root)

        try:
            root = _get_dataset_registry_root()
            assert root == custom_root
        finally:
            del os.environ["FISHBRO_DATASET_REGISTRY_ROOT"]