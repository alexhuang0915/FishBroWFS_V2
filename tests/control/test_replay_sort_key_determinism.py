"""
Test that replay sorting uses deterministic key (-score, batch_id, job_id).

P1-2: Replay/Compare 排序規則固定（determinism）
"""

from control.season_export_replay import (
    replay_season_topk,
    replay_season_leaderboard,
)


def test_replay_topk_sort_key_determinism() -> None:
    """Verify that replay_season_topk sorts by (-score, batch_id, job_id)."""
    # Mock replay index with items having same score but different batch/job IDs
    mock_index = {
        "season": "test_season",
        "generated_at": "2025-01-01T00:00:00Z",
        "batches": [
            {
                "batch_id": "batch2",
                "summary": {
                    "topk": [
                        {"job_id": "job3", "score": 0.9, "strategy_id": "s1"},
                        {"job_id": "job1", "score": 0.9, "strategy_id": "s1"},  # same score as job3
                    ],
                },
            },
            {
                "batch_id": "batch1",
                "summary": {
                    "topk": [
                        {"job_id": "job2", "score": 0.9, "strategy_id": "s1"},  # same score
                        {"job_id": "job4", "score": 0.8, "strategy_id": "s2"},  # lower score
                    ],
                },
            },
        ],
    }
    
    # We'll test by mocking load_replay_index
    import control.season_export_replay as replay_module
    
    original_load = replay_module.load_replay_index
    replay_module.load_replay_index = lambda exports_root, season: mock_index
    
    try:
        exports_root = None  # not used due to mock
        result = replay_season_topk(exports_root=exports_root, season="test_season", k=10)
        
        # Expected order:
        # 1. All items with score 0.9, sorted by batch_id then job_id
        #   batch1 comes before batch2 (lexicographically)
        #   Within batch1: job2
        #   Within batch2: job1, job3 (job1 < job3)
        # 2. Then item with score 0.8: job4
        
        items = result.items
        assert len(items) == 4
        
        # Check ordering
        # First: batch1, job2 (score 0.9)
        assert items[0]["_batch_id"] == "batch1"
        assert items[0]["job_id"] == "job2"
        assert items[0]["score"] == 0.9
        
        # Second: batch2, job1 (score 0.9)
        assert items[1]["_batch_id"] == "batch2"
        assert items[1]["job_id"] == "job1"
        assert items[1]["score"] == 0.9
        
        # Third: batch2, job3 (score 0.9)
        assert items[2]["_batch_id"] == "batch2"
        assert items[2]["job_id"] == "job3"
        assert items[2]["score"] == 0.9
        
        # Fourth: batch1, job4 (score 0.8)
        assert items[3]["_batch_id"] == "batch1"
        assert items[3]["job_id"] == "job4"
        assert items[3]["score"] == 0.8
        
    finally:
        replay_module.load_replay_index = original_load


def test_replay_leaderboard_sort_key_determinism() -> None:
    """Verify that replay_season_leaderboard sorts within groups by (-score, batch_id, job_id)."""
    mock_index = {
        "season": "test_season",
        "generated_at": "2025-01-01T00:00:00Z",
        "batches": [
            {
                "batch_id": "batch1",
                "summary": {
                    "topk": [
                        {"job_id": "job1", "score": 0.9, "strategy_id": "s1", "dataset_id": "d1"},
                        {"job_id": "job2", "score": 0.85, "strategy_id": "s1", "dataset_id": "d1"},
                    ],
                },
            },
            {
                "batch_id": "batch2",
                "summary": {
                    "topk": [
                        {"job_id": "job3", "score": 0.9, "strategy_id": "s1", "dataset_id": "d1"},  # same score as job1
                        {"job_id": "job4", "score": 0.8, "strategy_id": "s2", "dataset_id": "d2"},
                    ],
                },
            },
        ],
    }
    
    import control.season_export_replay as replay_module
    
    original_load = replay_module.load_replay_index
    replay_module.load_replay_index = lambda exports_root, season: mock_index
    
    try:
        exports_root = None
        result = replay_season_leaderboard(
            exports_root=exports_root,
            season="test_season",
            group_by="strategy_id",
            per_group=10,
        )
        
        # Find group for strategy s1
        s1_group = None
        for g in result.groups:
            if g["key"] == "s1":
                s1_group = g
                break
        
        assert s1_group is not None
        items = s1_group["items"]
        
        # Within s1 group, we have three items: job1 (score 0.9, batch1), job3 (score 0.9, batch2), job2 (score 0.85, batch1)
        # Sorting by (-score, batch_id, job_id):
        # 1. job1 (score 0.9, batch1, job1)
        # 2. job3 (score 0.9, batch2, job3)  # batch2 > batch1 lexicographically, so comes after
        # 3. job2 (score 0.85)
        
        assert len(items) == 3
        assert items[0]["job_id"] == "job1"
        assert items[0]["score"] == 0.9
        assert items[0].get("_batch_id") == "batch1" or items[0].get("batch_id") == "batch1"
        
        assert items[1]["job_id"] == "job3"
        assert items[1]["score"] == 0.9
        assert items[1].get("_batch_id") == "batch2" or items[1].get("batch_id") == "batch2"
        
        assert items[2]["job_id"] == "job2"
        assert items[2]["score"] == 0.85
        
    finally:
        replay_module.load_replay_index = original_load


def test_sort_key_with_missing_fields() -> None:
    """Test that sorting handles missing score, batch_id, or job_id gracefully."""
    mock_index = {
        "season": "test_season",
        "generated_at": "2025-01-01T00:00:00Z",
        "batches": [
            {
                "batch_id": "batch1",
                "summary": {
                    "topk": [
                        {"job_id": "job1", "score": 0.9},  # complete
                        {"job_id": "job2"},  # missing score
                        {"score": 0.8},  # missing job_id
                        {},  # missing both
                    ],
                },
            },
        ],
    }
    
    import control.season_export_replay as replay_module
    
    original_load = replay_module.load_replay_index
    replay_module.load_replay_index = lambda exports_root, season: mock_index
    
    try:
        exports_root = None
        result = replay_season_topk(exports_root=exports_root, season="test_season", k=10)
        
        # Should not crash; items with missing scores go last
        items = result.items
        assert len(items) == 4
        
        # First item should be the one with score 0.9
        assert items[0].get("score") == 0.9
        assert items[0].get("job_id") == "job1"
        
        # Remaining items order is deterministic based on default values
        # (missing score -> float('inf'), missing batch_id/job_id -> empty string)
        
    finally:
        replay_module.load_replay_index = original_load