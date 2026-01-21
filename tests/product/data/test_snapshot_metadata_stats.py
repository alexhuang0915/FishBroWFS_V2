"""
Gate 16.5‑A: Snapshot metadata and statistics.

Contract:
- SnapshotMetadata includes raw_sha256, normalized_sha256, manifest_sha256 chain
- Statistics (count, min/max timestamp, price ranges) are computed correctly
- Timezone‑aware UTC timestamps (datetime.now(timezone.utc))
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control.data_snapshot import create_snapshot, SnapshotMetadata
from contracts.data.snapshot_models import SnapshotStats


def test_snapshot_metadata_fields():
    """SnapshotMetadata includes all required fields."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshots_root = Path(tmp) / "snapshots"
        snapshots_root.mkdir()

        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            {"timestamp": "2025-01-01T01:00:00Z", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1200},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")

        assert isinstance(meta, SnapshotMetadata)
        assert meta.snapshot_id.startswith("TEST_1h_")
        assert meta.symbol == "TEST"
        assert meta.timeframe == "1h"
        assert meta.transform_version == "v1"
        assert len(meta.raw_sha256) == 64  # SHA‑256 hex length
        assert len(meta.normalized_sha256) == 64
        assert len(meta.manifest_sha256) == 64
        assert meta.created_at is not None
        # created_at should be UTC ISO 8601 with Z suffix
        assert meta.created_at.endswith("Z")
        dt = datetime.fromisoformat(meta.created_at.replace("Z", "+00:00"))
        assert dt.tzinfo == timezone.utc

        # stats should be present
        assert meta.stats is not None
        assert isinstance(meta.stats, SnapshotStats)
        assert meta.stats.count == 2
        assert meta.stats.min_timestamp == "2025-01-01T00:00:00Z"
        assert meta.stats.max_timestamp == "2025-01-01T01:00:00Z"
        assert meta.stats.min_price == 99.0
        assert meta.stats.max_price == 102.0
        assert meta.stats.total_volume == 2200.0


def test_snapshot_stats_computation():
    """SnapshotStats computed correctly from normalized bars."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshots_root = Path(tmp) / "snapshots"
        snapshots_root.mkdir()

        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 50.0, "high": 55.0, "low": 48.0, "close": 52.0, "volume": 500},
            {"timestamp": "2025-01-01T01:00:00Z", "open": 52.0, "high": 60.0, "low": 51.0, "close": 58.0, "volume": 700},
            {"timestamp": "2025-01-01T02:00:00Z", "open": 58.0, "high": 58.5, "low": 57.0, "close": 57.5, "volume": 300},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")

        stats = meta.stats
        assert stats.count == 3
        assert stats.min_timestamp == "2025-01-01T00:00:00Z"
        assert stats.max_timestamp == "2025-01-01T02:00:00Z"
        # min price across low
        assert stats.min_price == 48.0
        # max price across high
        assert stats.max_price == 60.0
        assert stats.total_volume == 1500.0


def test_snapshot_manifest_hash_chain():
    """manifest_sha256 is SHA‑256 of canonical JSON of manifest (excluding manifest_sha256)."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshots_root = Path(tmp) / "snapshots"
        snapshots_root.mkdir()

        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")

        # Read manifest
        manifest_path = snapshots_root / meta.snapshot_id / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # manifest_sha256 should be excluded from the hash computation
        # The create_snapshot function already ensures this; we can verify
        # that the manifest_sha256 field matches the computed hash of the rest.
        from control.artifacts import compute_sha256, canonical_json_bytes

        # Create a copy without manifest_sha256
        manifest_without_hash = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        canonical = canonical_json_bytes(manifest_without_hash)
        computed_hash = compute_sha256(canonical)
        assert manifest["manifest_sha256"] == computed_hash
        assert meta.manifest_sha256 == computed_hash


def test_snapshot_metadata_persistence():
    """Snapshot metadata survives round‑trip (write → read)."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshots_root = Path(tmp) / "snapshots"
        snapshots_root.mkdir()

        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")

        # Read manifest and validate it matches SnapshotMetadata
        manifest_path = snapshots_root / meta.snapshot_id / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # Convert manifest to SnapshotMetadata (should succeed)
        meta2 = SnapshotMetadata.model_validate(manifest)
        assert meta2.snapshot_id == meta.snapshot_id
        assert meta2.raw_sha256 == meta.raw_sha256
        assert meta2.normalized_sha256 == meta.normalized_sha256
        assert meta2.manifest_sha256 == meta.manifest_sha256
        # created_at may differ by microseconds due to two separate datetime.now() calls
        # Compare up to second precision
        from datetime import datetime
        dt1 = datetime.fromisoformat(meta.created_at.replace("Z", "+00:00"))
        dt2 = datetime.fromisoformat(meta2.created_at.replace("Z", "+00:00"))
        assert abs((dt1 - dt2).total_seconds()) < 1.0
        assert meta2.stats.count == meta.stats.count


def test_snapshot_empty_bars():
    """Edge case: empty raw_bars should raise ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshots_root = Path(tmp) / "snapshots"
        snapshots_root.mkdir()

        raw_bars = []
        with pytest.raises(ValueError, match="raw_bars cannot be empty"):
            create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")


def test_snapshot_malformed_timestamp():
    """Non‑ISO timestamp is accepted as a string (no validation)."""
    from control.data_snapshot import normalize_bars

    raw_bars = [
        {"timestamp": "not-a-timestamp", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
    ]
    # normalize_bars does not validate timestamp format; it just passes through.
    normalized, sha = normalize_bars(raw_bars, "v1")
    assert len(normalized) == 1
    assert normalized[0]["timestamp"] == "not-a-timestamp"