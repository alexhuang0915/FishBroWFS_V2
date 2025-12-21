import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app


@pytest.fixture
def client():
    return TestClient(app)


def _wjson(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_season_compare_topk_merge_and_tiebreak(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # season index lists two batches
        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [{"batch_id": "batchA"}, {"batch_id": "batchB"}],
            },
        )

        # batchA summary
        _wjson(
            artifacts_root / "batchA" / "summary.json",
            {
                "topk": [
                    {"job_id": "j2", "score": 2.0},
                    {"job_id": "j1", "score": 2.0},  # tie on score, job_id decides inside same batch later
                    {"job_id": "j0", "score": 1.0},
                ],
                "metrics": {"n": 3},
            },
        )

        # batchB summary (tie score with batchA to test tie-break by batch_id then job_id)
        _wjson(
            artifacts_root / "batchB" / "summary.json",
            {
                "topk": [
                    {"job_id": "j9", "score": 2.0},
                    {"job_id": "j8", "score": None},  # None goes last
                ],
                "metrics": {},
            },
        )

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.get(f"/seasons/{season}/compare/topk?k=10")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season
            items = data["items"]

            # score desc, tie-break batch_id asc, tie-break job_id asc
            # score=2.0 items are: batchA j1/j2, batchB j9
            # batchA < batchB => all batchA first; within batchA j1 < j2
            assert [(x["batch_id"], x["job_id"], x["score"]) for x in items[:3]] == [
                ("batchA", "j1", 2.0),
                ("batchA", "j2", 2.0),
                ("batchB", "j9", 2.0),
            ]

            # None score should be at the end
            assert items[-1]["score"] is None


def test_season_compare_skips_missing_or_corrupt_summaries(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [{"batch_id": "batchOK"}, {"batch_id": "batchMissing"}, {"batch_id": "batchBad"}],
            },
        )

        _wjson(
            artifacts_root / "batchOK" / "summary.json",
            {"topk": [{"job_id": "j1", "score": 1.0}], "metrics": {}},
        )

        # batchMissing -> no summary.json

        # batchBad -> corrupt json
        bad_path = artifacts_root / "batchBad" / "summary.json"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_text("{not-json", encoding="utf-8")

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.get(f"/seasons/{season}/compare/topk?k=20")
            assert r.status_code == 200
            data = r.json()
            assert [(x["batch_id"], x["job_id"]) for x in data["items"]] == [("batchOK", "j1")]

            skipped = set(data["skipped_batches"])
            assert "batchMissing" in skipped
            assert "batchBad" in skipped


def test_season_compare_404_when_season_index_missing(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.get("/seasons/NOPE/compare/topk?k=20")
            assert r.status_code == 404