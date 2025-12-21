"""
Phase 16: Export Pack Replay Mode regression tests.

Tests that exported season packages can be replayed without artifacts.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app
from FishBroWFS_V2.control.season_export_replay import (
    load_replay_index,
    replay_season_topk,
    replay_season_batch_cards,
    replay_season_leaderboard,
)


@pytest.fixture
def client():
    return TestClient(app)


def _wjson(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_load_replay_index():
    """Test loading replay_index.json."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [{"job_id": "job1", "score": 1.5, "strategy_id": "S1"}],
                        "metrics": {"n": 10},
                    },
                    "index": {"jobs": ["job1"]},
                }
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        loaded = load_replay_index(exports_root, season)
        assert loaded["season"] == season
        assert len(loaded["batches"]) == 1
        assert loaded["batches"][0]["batch_id"] == "batchA"


def test_load_replay_index_missing():
    """Test FileNotFoundError when replay_index.json missing."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        with pytest.raises(FileNotFoundError):
            load_replay_index(exports_root, season)


def test_replay_season_topk():
    """Test replay season topk."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [
                            {"job_id": "job1", "score": 1.5, "strategy_id": "S1"},
                            {"job_id": "job2", "score": 1.2, "strategy_id": "S2"},
                        ],
                        "metrics": {},
                    },
                },
                {
                    "batch_id": "batchB",
                    "summary": {
                        "topk": [
                            {"job_id": "job3", "score": 1.8, "strategy_id": "S1"},
                        ],
                        "metrics": {},
                    },
                },
                {
                    "batch_id": "batchC",
                    "summary": None,  # missing summary
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        res = replay_season_topk(exports_root, season, k=5)
        assert res.season == season
        assert res.k == 5
        assert len(res.items) == 3  # all topk items merged
        assert res.skipped_batches == ["batchC"]
        
        # Verify ordering by score descending
        scores = [item["score"] for item in res.items]
        assert scores == [1.8, 1.5, 1.2]
        
        # Verify batch_id added
        assert all("_batch_id" in item for item in res.items)


def test_replay_season_batch_cards():
    """Test replay season batch cards."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [{"job_id": "job1", "score": 1.5}],
                        "metrics": {"n": 10},
                    },
                    "index": {"jobs": ["job1"]},
                },
                {
                    "batch_id": "batchB",
                    "summary": None,  # missing summary
                    "index": {"jobs": ["job2"]},
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        res = replay_season_batch_cards(exports_root, season)
        assert res.season == season
        assert len(res.batches) == 1
        assert res.batches[0]["batch_id"] == "batchA"
        assert res.skipped_summaries == ["batchB"]


def test_replay_season_leaderboard():
    """Test replay season leaderboard."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [
                            {"job_id": "job1", "score": 1.5, "strategy_id": "S1", "dataset_id": "D1"},
                            {"job_id": "job2", "score": 1.2, "strategy_id": "S2", "dataset_id": "D1"},
                        ],
                        "metrics": {},
                    },
                },
                {
                    "batch_id": "batchB",
                    "summary": {
                        "topk": [
                            {"job_id": "job3", "score": 1.8, "strategy_id": "S1", "dataset_id": "D2"},
                            {"job_id": "job4", "score": 0.9, "strategy_id": "S2", "dataset_id": "D2"},
                        ],
                        "metrics": {},
                    },
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        # Test group_by strategy_id
        res = replay_season_leaderboard(exports_root, season, group_by="strategy_id", per_group=2)
        assert res.season == season
        assert res.group_by == "strategy_id"
        assert res.per_group == 2
        assert len(res.groups) == 2  # S1 and S2
        
        # Find S1 group
        s1_group = next(g for g in res.groups if g["key"] == "S1")
        assert s1_group["total"] == 2
        assert len(s1_group["items"]) == 2
        assert s1_group["items"][0]["score"] == 1.8  # top score first
        
        # Test group_by dataset_id
        res2 = replay_season_leaderboard(exports_root, season, group_by="dataset_id", per_group=1)
        assert len(res2.groups) == 2  # D1 and D2
        d1_group = next(g for g in res2.groups if g["key"] == "D1")
        assert len(d1_group["items"]) == 1  # per_group=1


def test_export_season_compare_topk_endpoint(client):
    """Test /exports/seasons/{season}/compare/topk endpoint."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [{"job_id": "job1", "score": 1.5}],
                        "metrics": {},
                    },
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            r = client.get(f"/exports/seasons/{season}/compare/topk?k=5")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season
            assert data["k"] == 5
            assert len(data["items"]) == 1
            assert data["items"][0]["job_id"] == "job1"


def test_export_season_compare_batches_endpoint(client):
    """Test /exports/seasons/{season}/compare/batches endpoint."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [{"job_id": "job1", "score": 1.5}],
                        "metrics": {"n": 10},
                    },
                    "index": {"jobs": ["job1"]},
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            r = client.get(f"/exports/seasons/{season}/compare/batches")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season
            assert len(data["batches"]) == 1
            assert data["batches"][0]["batch_id"] == "batchA"


def test_export_season_compare_leaderboard_endpoint(client):
    """Test /exports/seasons/{season}/compare/leaderboard endpoint."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [
                            {"job_id": "job1", "score": 1.5, "strategy_id": "S1"},
                        ],
                        "metrics": {},
                    },
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            r = client.get(f"/exports/seasons/{season}/compare/leaderboard?group_by=strategy_id")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season
            assert data["group_by"] == "strategy_id"
            assert len(data["groups"]) == 1
            assert data["groups"][0]["key"] == "S1"


def test_export_endpoints_missing_replay_index(client):
    """Test 404 when replay_index.json missing."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            r = client.get(f"/exports/seasons/{season}/compare/topk")
            assert r.status_code == 404
            assert "replay_index.json" in r.json()["detail"]


def test_deterministic_ordering():
    """Test deterministic ordering in replay functions."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        # Create replay index with batches in non-alphabetical order
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchZ",
                    "summary": {
                        "topk": [{"job_id": "jobZ", "score": 1.0}],
                        "metrics": {},
                    },
                },
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [{"job_id": "jobA", "score": 2.0}],
                        "metrics": {},
                    },
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        # Test that batches are processed in sorted order (batchA before batchZ)
        res = replay_season_topk(exports_root, season, k=10)
        # The items should be sorted by score, not batch order
        scores = [item["score"] for item in res.items]
        assert scores == [2.0, 1.0]  # score ordering, not batch ordering
        
        # Test batch cards ordering
        res2 = replay_season_batch_cards(exports_root, season)
        batch_ids = [b["batch_id"] for b in res2.batches]
        assert batch_ids == ["batchA", "batchZ"]  # sorted by batch_id


def test_replay_with_empty_topk():
    """Test replay with empty topk lists."""
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [],
                        "metrics": {},
                    },
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        res = replay_season_topk(exports_root, season, k=5)
        assert res.season == season
        assert len(res.items) == 0
        assert res.skipped_batches == []  # not skipped because summary exists


def test_replay_endpoint_zero_write_guarantee(client):
    """Ensure replay endpoints do NOT write to exports tree."""
    import os
    import time
    
    with tempfile.TemporaryDirectory() as tmp:
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"
        
        replay_index = {
            "season": season,
            "generated_at": "2025-12-21T00:00:00Z",
            "batches": [
                {
                    "batch_id": "batchA",
                    "summary": {
                        "topk": [{"job_id": "job1", "score": 1.5}],
                        "metrics": {},
                    },
                    "index": {"jobs": ["job1"]},
                },
            ],
        }
        
        _wjson(exports_root / "seasons" / season / "replay_index.json", replay_index)
        
        # Record initial state
        def get_file_state():
            files = []
            for root, dirs, filenames in os.walk(exports_root):
                for f in filenames:
                    path = Path(root) / f
                    files.append((str(path.relative_to(exports_root)), path.stat().st_mtime))
            return sorted(files)
        
        initial_state = get_file_state()
        
        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            # Call each replay endpoint
            r1 = client.get(f"/exports/seasons/{season}/compare/topk?k=5")
            assert r1.status_code == 200
            r2 = client.get(f"/exports/seasons/{season}/compare/batches")
            assert r2.status_code == 200
            r3 = client.get(f"/exports/seasons/{season}/compare/leaderboard?group_by=strategy_id")
            assert r3.status_code == 200
        
        # Wait a tiny bit to ensure mtime could change if write occurred
        time.sleep(0.01)
        
        final_state = get_file_state()
        
        # No new files should appear, no mtime changes
        assert initial_state == final_state, "Replay endpoints must not write to exports tree"