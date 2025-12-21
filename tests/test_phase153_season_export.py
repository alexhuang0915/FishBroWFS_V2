import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app
from FishBroWFS_V2.control.artifacts import compute_sha256


@pytest.fixture
def client():
    return TestClient(app)


def _wjson(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_export_requires_frozen_season(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"

        # season index exists
        _wjson(
            season_root / season / "season_index.json",
            {"season": season, "generated_at": "Z", "batches": []},
        )

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root), \
             patch("FishBroWFS_V2.control.season_export.get_exports_root", return_value=exports_root):
            r = client.post(f"/seasons/{season}/export")
            assert r.status_code == 403


def test_export_builds_package_and_manifest_sha_matches(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"

        # create season index with 2 batches
        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [{"batch_id": "batchB"}, {"batch_id": "batchA"}],
            },
        )

        # create season metadata and freeze it
        # (use API to freeze for realism)
        with patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.post(f"/seasons/{season}/freeze")
            assert r.status_code == 200

        # artifacts files
        _wjson(artifacts_root / "batchA" / "metadata.json", {"season": season, "frozen": True, "tags": ["a"], "note": ""})
        _wjson(artifacts_root / "batchA" / "index.json", {"x": 1})
        _wjson(artifacts_root / "batchA" / "summary.json", {"topk": [{"job_id": "j1", "score": 1.0}], "metrics": {}})

        _wjson(artifacts_root / "batchB" / "metadata.json", {"season": season, "frozen": False, "tags": ["b"], "note": "n"})
        _wjson(artifacts_root / "batchB" / "index.json", {"y": 2})
        # omit batchB summary.json to test missing files recorded

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root), \
             patch("FishBroWFS_V2.control.season_export.get_exports_root", return_value=exports_root):
            r = client.post(f"/seasons/{season}/export")
            assert r.status_code == 200
            out = r.json()

            export_dir = Path(out["export_dir"])
            manifest_path = Path(out["manifest_path"])
            assert export_dir.exists()
            assert manifest_path.exists()

            # verify manifest sha matches actual bytes
            actual_sha = compute_sha256(manifest_path.read_bytes())
            assert out["manifest_sha256"] == actual_sha

            # verify key files copied
            assert (export_dir / "season_index.json").exists()
            # metadata may exist (freeze created it)
            assert (export_dir / "season_metadata.json").exists()
            assert (export_dir / "batches" / "batchA" / "metadata.json").exists()
            assert (export_dir / "batches" / "batchA" / "index.json").exists()
            assert (export_dir / "batches" / "batchA" / "summary.json").exists()

            # batchB summary missing -> recorded
            assert "batches/batchB/summary.json" in out["missing_files"]

            # manifest contains file hashes
            man = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert man["season"] == season
            assert "files" in man and isinstance(man["files"], list)
            assert "manifest_sha256" in man