"""
Test that replay/compare handlers are strictly read‑only (no writes).

P2: Read‑only enforcement policy (保證 compare/replay 0 write)
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from control.season_export_replay import (
    replay_season_topk,
    replay_season_batch_cards,
    replay_season_leaderboard,
)


def test_replay_compare_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Verify that replay/compare functions never call any write operations.

    Monkey‑patches Path.write_text, Path.mkdir, shutil.copyfile etc.
    If any of these are called during replay, the test fails immediately.
    """
    # Mock functions that would indicate a write
    write_calls = []

    def boom_write_text(*args: Any, **kwargs: Any) -> None:
        write_calls.append(("Path.write_text", args, kwargs))
        pytest.fail("Replay/Compare must be read‑only (Path.write_text called)")

    def boom_mkdir(*args: Any, **kwargs: Any) -> None:
        write_calls.append(("Path.mkdir", args, kwargs))
        pytest.fail("Replay/Compare must be read‑only (Path.mkdir called)")

    def boom_copyfile(*args: Any, **kwargs: Any) -> None:
        write_calls.append(("shutil.copyfile", args, kwargs))
        pytest.fail("Replay/Compare must be read‑only (shutil.copyfile called)")

    # Create a minimal replay_index.json that satisfies the functions' expectations
    exports_root = tmp_path / "exports"
    season_dir = exports_root / "seasons" / "test_season"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Apply monkey patches AFTER creating directories
    monkeypatch.setattr(Path, "write_text", boom_write_text, raising=True)
    monkeypatch.setattr(Path, "mkdir", boom_mkdir, raising=True)
    monkeypatch.setattr(shutil, "copyfile", boom_copyfile, raising=True)

    replay_index = {
        "season": "test_season",
        "generated_at": "2025-01-01T00:00:00Z",
        "batches": [
            {
                "batch_id": "batch1",
                "summary": {
                    "topk": [
                        {
                            "job_id": "job1",
                            "score": 0.95,
                            "strategy_id": "s1",
                            "dataset_id": "d1",
                            "params": {"window": 20},
                        },
                        {
                            "job_id": "job2",
                            "score": 0.90,
                            "strategy_id": "s2",
                            "dataset_id": "d2",
                            "params": {"window": 30},
                        },
                    ],
                    "metrics": {"count": 2, "avg_score": 0.925},
                },
                "index": {
                    "jobs": [
                        {"job_id": "job1", "status": "completed"},
                        {"job_id": "job2", "status": "completed"},
                    ]
                },
            }
        ],
        "deterministic_order": {
            "batches": "batch_id asc",
            "files": "path asc",
        },
    }

    # Write the replay index (this write is allowed because it's test setup,
    # not part of the replay functions themselves).
    # Temporarily restore the original methods for setup.
    monkeypatch.undo()
    replay_index_path = season_dir / "replay_index.json"
    replay_index_path.write_text('{"dummy": "data"}')  # Write something
    # Now re‑apply the patches for the actual test
    monkeypatch.setattr(Path, "write_text", boom_write_text, raising=True)
    monkeypatch.setattr(Path, "mkdir", boom_mkdir, raising=True)
    monkeypatch.setattr(shutil, "copyfile", boom_copyfile, raising=True)

    # Actually write the proper replay index (still test setup)
    # We need to temporarily allow writes for setup, so we use a context manager
    # or just write directly without monkeypatch.
    # Let's do it by temporarily removing the monkeypatch.
    original_write_text = Path.write_text
    original_mkdir = Path.mkdir
    monkeypatch.undo()
    replay_index_path.write_text('{"dummy": "data"}')
    # Re‑apply patches
    monkeypatch.setattr(Path, "write_text", boom_write_text, raising=True)
    monkeypatch.setattr(Path, "mkdir", boom_mkdir, raising=True)
    monkeypatch.setattr(shutil, "copyfile", boom_copyfile, raising=True)

    # Actually, let's create a simpler approach: write the file before patching
    # We'll create the file without monkeypatch interference.
    # Reset and write properly.
    monkeypatch.undo()
    replay_index_path.write_text('{"dummy": "data"}')
    # Now patch for the actual test calls
    monkeypatch.setattr(Path, "write_text", boom_write_text, raising=True)
    monkeypatch.setattr(Path, "mkdir", boom_mkdir, raising=True)
    monkeypatch.setattr(shutil, "copyfile", boom_copyfile, raising=True)

    # The replay functions will try to read the file, but our dummy content
    # will cause JSON decode errors. Instead, we should mock the load_replay_index
    # function to return our prepared index.
    from control import season_export_replay

    def mock_load_replay_index(exports_root: Path, season: str) -> dict[str, Any]:
        if season == "test_season" and exports_root == exports_root:
            return replay_index
        raise FileNotFoundError

    monkeypatch.setattr(
        season_export_replay,
        "load_replay_index",
        mock_load_replay_index,
    )

    # Now call the replay functions – they should only read, never write.
    # If any write operation is triggered, the boom_* functions will raise pytest.fail.
    try:
        # 1) replay_season_topk
        result_topk = replay_season_topk(exports_root=exports_root, season="test_season", k=5)
        assert result_topk.season == "test_season"
        assert len(result_topk.items) == 2

        # 2) replay_season_batch_cards
        result_cards = replay_season_batch_cards(exports_root=exports_root, season="test_season")
        assert result_cards.season == "test_season"
        assert len(result_cards.batches) == 1

        # 3) replay_season_leaderboard
        result_leader = replay_season_leaderboard(
            exports_root=exports_root,
            season="test_season",
            group_by="strategy_id",
            per_group=3,
        )
        assert result_leader.season == "test_season"
        assert len(result_leader.groups) == 2  # s1 and s2

    except Exception as e:
        # If an exception occurs that is not a write violation, we should still fail
        # unless it's expected (e.g., FileNotFoundError due to missing files).
        # In this mocked scenario, no exception should happen.
        pytest.fail(f"Unexpected exception during replay: {e}")

    # If we reach here, no write was attempted – test passes.
    assert len(write_calls) == 0, f"Unexpected write calls: {write_calls}"