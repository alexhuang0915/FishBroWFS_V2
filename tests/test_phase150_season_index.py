
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from control.api import app


@pytest.fixture
def client():
    return TestClient(app)


def _wjson(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rebuild_season_index_collects_batches_and_is_deterministic(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # batch2 (lexicographically after batch1) — write first to verify sorting
        _wjson(
            artifacts_root / "batch2" / "metadata.json",
            {"batch_id": "batch2", "season": season, "tags": ["b", "a"], "note": "n2", "frozen": False},
        )
        _wjson(artifacts_root / "batch2" / "index.json", {"x": 1})
        _wjson(artifacts_root / "batch2" / "summary.json", {"topk": [], "metrics": {}})

        # batch1
        _wjson(
            artifacts_root / "batch1" / "metadata.json",
            {"batch_id": "batch1", "season": season, "tags": ["z"], "note": "n1", "frozen": True},
        )
        _wjson(artifacts_root / "batch1" / "index.json", {"y": 2})
        _wjson(artifacts_root / "batch1" / "summary.json", {"topk": [{"job_id": "j", "score": 1.0}], "metrics": {"n": 1}})

        # different season should be ignored
        _wjson(
            artifacts_root / "batchX" / "metadata.json",
            {"batch_id": "batchX", "season": "2026Q2", "tags": ["ignore"], "note": "", "frozen": False},
        )

        with patch("control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("control.api._get_season_index_root", return_value=season_root):
            r = client.post(f"/seasons/{season}/rebuild_index")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season
            assert len(data["batches"]) == 2

            # deterministic order by batch_id
            assert [b["batch_id"] for b in data["batches"]] == ["batch1", "batch2"]

            # tags dedupe+sort in index entries
            b2 = data["batches"][1]
            assert b2["tags"] == ["a", "b"]

            # index file exists
            idx_path = season_root / season / "season_index.json"
            assert idx_path.exists()


def test_season_metadata_lifecycle_and_freeze_rules(client):
    with tempfile.TemporaryDirectory() as tmp:
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        with patch("control.api._get_season_index_root", return_value=season_root):
            # metadata not exist -> 404
            r = client.get(f"/seasons/{season}/metadata")
            assert r.status_code == 404

            # create/update metadata
            r = client.patch(f"/seasons/{season}/metadata", json={"tags": ["core", "core"], "note": "hello"})
            assert r.status_code == 200
            meta = r.json()
            assert meta["season"] == season
            assert meta["tags"] == ["core"]
            assert meta["note"] == "hello"
            assert meta["frozen"] is False

            # freeze
            r = client.post(f"/seasons/{season}/freeze")
            assert r.status_code == 200
            assert r.json()["status"] == "frozen"

            # cannot unfreeze
            r = client.patch(f"/seasons/{season}/metadata", json={"frozen": False})
            assert r.status_code == 400

            # tags/note still allowed
            r = client.patch(f"/seasons/{season}/metadata", json={"tags": ["z"], "note": "n2"})
            assert r.status_code == 200
            meta2 = r.json()
            assert meta2["tags"] == ["core", "z"]
            assert meta2["note"] == "n2"
            assert meta2["frozen"] is True


def test_rebuild_index_forbidden_when_season_frozen(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # prepare one batch
        _wjson(
            artifacts_root / "batch1" / "metadata.json",
            {"batch_id": "batch1", "season": season, "tags": [], "note": "", "frozen": False},
        )

        with patch("control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("control.api._get_season_index_root", return_value=season_root):

            # freeze season first
            r = client.post(f"/seasons/{season}/freeze")
            assert r.status_code == 200

            # rebuild should be forbidden
            r = client.post(f"/seasons/{season}/rebuild_index")
            assert r.status_code == 403


