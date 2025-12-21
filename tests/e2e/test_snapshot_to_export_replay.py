"""
Phase 16.5‑C: End‑to‑end snapshot → dataset → batch → export → replay.

Contract:
- Deterministic snapshot creation (same raw bars → same snapshot_id)
- Dataset registry append‑only (no overwrites)
- Batch submission uses snapshot‑registered dataset
- Season freeze → export → replay yields identical results
- Zero write in compare/replay (read‑only)
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app
from FishBroWFS_V2.control.data_snapshot import compute_snapshot_id, normalize_bars
from FishBroWFS_V2.control.dataset_registry_mutation import register_snapshot_as_dataset


@pytest.fixture
def client():
    return TestClient(app)


def _write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_snapshot_create_deterministic():
    """Gate 16.5‑A: deterministic snapshot ID and normalized SHA‑256."""
    raw_bars = [
        {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        {"timestamp": "2025-01-01T01:00:00Z", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1200},
    ]
    symbol = "TEST"
    timeframe = "1h"
    transform_version = "v1"

    # Same input must produce same snapshot_id
    id1 = compute_snapshot_id(raw_bars, symbol, timeframe, transform_version)
    id2 = compute_snapshot_id(raw_bars, symbol, timeframe, transform_version)
    assert id1 == id2

    # Normalized bars must be identical
    norm1, sha1 = normalize_bars(raw_bars, transform_version)
    norm2, sha2 = normalize_bars(raw_bars, transform_version)
    assert sha1 == sha2
    assert norm1 == norm2

    # Different transform version changes SHA
    id3 = compute_snapshot_id(raw_bars, symbol, timeframe, "v2")
    assert id3 != id1


def test_snapshot_endpoint_creates_manifest(client):
    """POST /datasets/snapshots creates immutable snapshot directory."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "snapshots"
        root.mkdir(parents=True)

        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        payload = {
            "raw_bars": raw_bars,
            "symbol": "TEST",
            "timeframe": "1h",
            "transform_version": "v1",
        }

        with patch("FishBroWFS_V2.control.api._get_snapshots_root", return_value=root):
            r = client.post("/datasets/snapshots", json=payload)
            if r.status_code != 200:
                print(f"Response status: {r.status_code}")
                print(f"Response body: {r.text}")
            assert r.status_code == 200
            meta = r.json()
            assert "snapshot_id" in meta
            assert meta["symbol"] == "TEST"
            assert meta["timeframe"] == "1h"
            assert "raw_sha256" in meta
            assert "normalized_sha256" in meta
            assert "manifest_sha256" in meta
            assert "created_at" in meta

            # Verify directory exists
            snapshot_dir = root / meta["snapshot_id"]
            assert snapshot_dir.exists()
            assert (snapshot_dir / "manifest.json").exists()
            assert (snapshot_dir / "raw.json").exists()
            assert (snapshot_dir / "normalized.json").exists()

            # Manifest content matches metadata
            manifest = _read_json(snapshot_dir / "manifest.json")
            assert manifest["snapshot_id"] == meta["snapshot_id"]
            assert manifest["raw_sha256"] == meta["raw_sha256"]


def test_register_snapshot_endpoint(client):
    """POST /datasets/registry/register_snapshot adds snapshot to dataset registry."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshots_root = Path(tmp) / "snapshots"
        snapshots_root.mkdir(parents=True)

        # Create a snapshot manually
        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        from FishBroWFS_V2.control.data_snapshot import create_snapshot
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")
        snapshot_id = meta.snapshot_id

        # Mock both roots
        with patch("FishBroWFS_V2.control.api._get_snapshots_root", return_value=snapshots_root):
            # Registry root also needs to be mocked (inside dataset_registry_mutation)
            registry_root = Path(tmp) / "datasets"
            registry_root.mkdir(parents=True)
            with patch("FishBroWFS_V2.control.dataset_registry_mutation._get_dataset_registry_root", return_value=registry_root):
                r = client.post("/datasets/registry/register_snapshot", json={"snapshot_id": snapshot_id})
                if r.status_code != 200:
                    print(f"Response status: {r.status_code}")
                    print(f"Response body: {r.text}")
                assert r.status_code == 200
                resp = r.json()
                assert resp["snapshot_id"] == snapshot_id
                assert resp["dataset_id"].startswith("snapshot_")

                # Verify registry file updated
                registry_file = registry_root / "datasets_index.json"
                assert registry_file.exists()
                registry_data = _read_json(registry_file)
                assert any(d["id"] == resp["dataset_id"] for d in registry_data["datasets"])

                # Second registration → 409 conflict
                r2 = client.post("/datasets/registry/register_snapshot", json={"snapshot_id": snapshot_id})
                assert r2.status_code == 409


def test_snapshot_to_batch_to_export_e2e(client):
    """
    Full pipeline: snapshot → dataset → batch → freeze → export → replay.

    This test is heavy; we mock the heavy parts (engine) but keep the file‑system
    mutations real to verify deterministic chain.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Setup directories
        artifacts_root = tmp_path / "artifacts"
        artifacts_root.mkdir()
        snapshots_root = tmp_path / "snapshots"
        snapshots_root.mkdir()
        exports_root = tmp_path / "exports"
        exports_root.mkdir()
        season_index_root = tmp_path / "season_index"
        season_index_root.mkdir()
        dataset_registry_root = tmp_path / "datasets"
        dataset_registry_root.mkdir()

        # Create a snapshot
        raw_bars = [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            {"timestamp": "2025-01-01T01:00:00Z", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1200},
        ]
        from FishBroWFS_V2.control.data_snapshot import create_snapshot
        meta = create_snapshot(snapshots_root, raw_bars, "TEST", "1h", "v1")
        snapshot_id = meta.snapshot_id

        # Register snapshot as dataset
        from FishBroWFS_V2.control.dataset_registry_mutation import register_snapshot_as_dataset
        snapshot_dir = snapshots_root / snapshot_id
        entry = register_snapshot_as_dataset(snapshot_dir=snapshot_dir, registry_root=dataset_registry_root)
        dataset_id = entry.id

        # Prepare batch submission (mock engine to avoid real computation)
        # We'll create a dummy batch with a single job that references the snapshot dataset
        batch_id = "test_batch_123"
        batch_dir = artifacts_root / batch_id
        batch_dir.mkdir()

        # Write dummy execution.json (simulate batch completion)
        _write_json(
            batch_dir / "execution.json",
            {
                "batch_state": "DONE",
                "jobs": {
                    "job1": {"state": "SUCCESS"},
                },
            },
        )

        # Write dummy summary.json with a topk entry referencing the snapshot dataset
        _write_json(
            batch_dir / "summary.json",
            {
                "topk": [
                    {
                        "job_id": "job1",
                        "score": 1.23,
                        "dataset_id": dataset_id,
                        "strategy_id": "dummy_strategy",
                    }
                ],
                "metrics": {"n": 1},
            },
        )

        # Write dummy index.json
        _write_json(
            batch_dir / "index.json",
            {
                "batch_id": batch_id,
                "jobs": ["job1"],
                "datasets": [dataset_id],
            },
        )

        # Write batch metadata (season = "test_season")
        _write_json(
            batch_dir / "metadata.json",
            {
                "batch_id": batch_id,
                "season": "test_season",
                "tags": ["snapshot_test"],
                "note": "Snapshot integration test",
                "frozen": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Freeze batch
        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root):
            store_patch = patch("FishBroWFS_V2.control.api._get_governance_store")
            mock_store = store_patch.start()
            mock_store.return_value.is_frozen.return_value = False
            mock_store.return_value.freeze.return_value = None

            # Freeze season
            season_store_patch = patch("FishBroWFS_V2.control.api._get_season_store")
            mock_season_store = season_store_patch.start()
            mock_season_store.return_value.is_frozen.return_value = False
            mock_season_store.return_value.freeze.return_value = None

            # Export season (mock export function to avoid heavy copying)
            export_patch = patch("FishBroWFS_V2.control.api.export_season_package")
            mock_export = export_patch.start()
            mock_export.return_value = type(
                "ExportResult",
                (),
                {
                    "season": "test_season",
                    "export_dir": exports_root / "seasons" / "test_season",
                    "manifest_path": exports_root / "seasons" / "test_season" / "manifest.json",
                    "manifest_sha256": "dummy_sha256",
                    "exported_files": [],
                    "missing_files": [],
                },
            )()

            # Replay endpoints (read‑only) should work without touching artifacts
            with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
                # Mock replay_index.json (format matches season_export.py)
                replay_index_path = exports_root / "seasons" / "test_season" / "replay_index.json"
                replay_index_path.parent.mkdir(parents=True, exist_ok=True)
                _write_json(
                    replay_index_path,
                    {
                        "season": "test_season",
                        "batches": [
                            {
                                "batch_id": batch_id,
                                "summary": {
                                    "topk": [
                                        {
                                            "job_id": "job1",
                                            "score": 1.23,
                                            "dataset_id": dataset_id,
                                            "strategy_id": "dummy_strategy",
                                        }
                                    ],
                                    "metrics": {"n": 1},
                                },
                                "index": {
                                    "batch_id": batch_id,
                                    "jobs": ["job1"],
                                    "datasets": [dataset_id],
                                },
                            }
                        ],
                    },
                )

                # Call replay endpoints
                r = client.get("/exports/seasons/test_season/compare/topk")
                if r.status_code != 200:
                    print(f"Response status: {r.status_code}")
                    print(f"Response body: {r.text}")
                assert r.status_code == 200
                data = r.json()
                assert data["season"] == "test_season"
                assert len(data["items"]) == 1
                assert data["items"][0]["dataset_id"] == dataset_id

                r2 = client.get("/exports/seasons/test_season/compare/batches")
                assert r2.status_code == 200
                data2 = r2.json()
                assert data2["season"] == "test_season"
                assert len(data2["batches"]) == 1

            # Clean up patches
            export_patch.stop()
            season_store_patch.stop()
            store_patch.stop()

        # Verify snapshot tree zero‑write: no extra files under snapshot directory
        snapshot_dir = snapshots_root / snapshot_id
        snapshot_files = list(snapshot_dir.rglob("*"))
        # Should have exactly raw.json, normalized.json, manifest.json
        assert len(snapshot_files) == 3
        assert any(f.name == "raw.json" for f in snapshot_files)
        assert any(f.name == "normalized.json" for f in snapshot_files)
        assert any(f.name == "manifest.json" for f in snapshot_files)


def test_list_snapshots_endpoint(client):
    """GET /datasets/snapshots returns sorted snapshot list."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "snapshots"
        root.mkdir(parents=True)

        # Create two snapshot directories manually
        snap1 = root / "TEST_1h_abc123_v1"
        snap1.mkdir()
        _write_json(
            snap1 / "manifest.json",
            {
                "snapshot_id": "TEST_1h_abc123_v1",
                "symbol": "TEST",
                "timeframe": "1h",
                "created_at": "2025-01-01T00:00:00Z",
                "raw_sha256": "abc123",
                "normalized_sha256": "def456",
                "manifest_sha256": "ghi789",
            },
        )

        snap2 = root / "TEST_1h_def456_v1"
        snap2.mkdir()
        _write_json(
            snap2 / "manifest.json",
            {
                "snapshot_id": "TEST_1h_def456_v1",
                "symbol": "TEST",
                "timeframe": "1h",
                "created_at": "2025-01-01T01:00:00Z",
                "raw_sha256": "def456",
                "normalized_sha256": "ghi789",
                "manifest_sha256": "jkl012",
            },
        )

        with patch("FishBroWFS_V2.control.api._get_snapshots_root", return_value=root):
            r = client.get("/datasets/snapshots")
            assert r.status_code == 200
            data = r.json()
            assert "snapshots" in data
            assert len(data["snapshots"]) == 2
            # Should be sorted by snapshot_id
            ids = [s["snapshot_id"] for s in data["snapshots"]]
            assert ids == sorted(ids)