
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


def test_compare_batches_cards_and_robust_summary(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # season index includes 3 batches; ensure order is batchA, batchB, batchC
        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [
                    {"batch_id": "batchB", "frozen": False, "tags": ["b"], "note": "nB", "index_hash": "iB", "summary_hash": "sB"},
                    {"batch_id": "batchA", "frozen": True, "tags": ["a"], "note": "nA", "index_hash": "iA", "summary_hash": "sA"},
                    {"batch_id": "batchC", "frozen": False, "tags": [], "note": "", "index_hash": None, "summary_hash": None},
                ],
            },
        )

        # batchA: ok summary
        _wjson(
            artifacts_root / "batchA" / "summary.json",
            {"topk": [{"job_id": "j1", "score": 1.23}], "metrics": {"n": 1}},
        )

        # batchB: corrupt summary
        p_bad = artifacts_root / "batchB" / "summary.json"
        p_bad.parent.mkdir(parents=True, exist_ok=True)
        p_bad.write_text("{not-json", encoding="utf-8")

        # batchC: missing summary

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.get(f"/seasons/{season}/compare/batches")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season

            batches = data["batches"]
            assert [b["batch_id"] for b in batches] == ["batchA", "batchB", "batchC"]

            bA = batches[0]
            assert bA["summary_ok"] is True
            assert bA["top_job_id"] == "j1"
            assert bA["top_score"] == 1.23
            assert bA["topk_size"] == 1

            bB = batches[1]
            assert bB["summary_ok"] is False

            bC = batches[2]
            assert bC["summary_ok"] is False
            assert bC["topk_size"] == 0

            skipped = set(data["skipped_summaries"])
            assert "batchB" in skipped
            assert "batchC" in skipped


def test_compare_leaderboard_grouping_and_determinism(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [{"batch_id": "batchA"}, {"batch_id": "batchB"}],
            },
        )

        # Include strategy_id and dataset_id in rows for grouping
        _wjson(
            artifacts_root / "batchA" / "summary.json",
            {
                "topk": [
                    {"job_id": "a2", "score": 2.0, "strategy_id": "S1"},
                    {"job_id": "a1", "score": 2.0, "strategy_id": "S1"},  # tie within same group
                    {"job_id": "a0", "score": 1.0, "strategy_id": "S2"},
                ]
            },
        )
        _wjson(
            artifacts_root / "batchB" / "summary.json",
            {
                "topk": [
                    {"job_id": "b9", "score": 2.0, "strategy_id": "S1"},
                    {"job_id": "b8", "score": None, "strategy_id": "S1"},
                ]
            },
        )

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.get(f"/seasons/{season}/compare/leaderboard?group_by=strategy_id&per_group=3")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season
            assert data["group_by"] == "strategy_id"
            assert data["per_group"] == 3

            groups = {g["key"]: g["items"] for g in data["groups"]}
            assert "S1" in groups
            # Deterministic ordering inside group S1 by score desc, tie-break batch_id asc, job_id asc
            # score=2.0: batchA a1/a2, batchB b9 => batchA first; within batchA a1 < a2
            assert [(x["batch_id"], x["job_id"], x["score"]) for x in groups["S1"][:3]] == [
                ("batchA", "a1", 2.0),
                ("batchA", "a2", 2.0),
                ("batchB", "b9", 2.0),
            ]


def test_compare_endpoints_404_when_season_index_missing(client):
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.get("/seasons/NOPE/compare/batches")
            assert r.status_code == 404
            r = client.get("/seasons/NOPE/compare/leaderboard")
            assert r.status_code == 404


