"""
Test that season_index root directory is auto‑created when SeasonStore is initialized.

P1-3: season_index root 必須 auto-create（抗 clean）
"""

import shutil
from pathlib import Path

import pytest

from control.season_api import SeasonStore, get_season_index_root


def test_season_store_creates_root(tmp_path: Path) -> None:
    """SeasonStore.__init__ should create the root directory if it doesn't exist."""
    root = tmp_path / "season_index"
    
    # Ensure root does not exist
    if root.exists():
        shutil.rmtree(root)
    assert not root.exists()
    
    # Creating SeasonStore should create the directory
    store = SeasonStore(root)
    assert root.exists()
    assert root.is_dir()
    
    # The root should be empty (no season subdirectories yet)
    assert list(root.iterdir()) == []


def test_season_store_reuses_existing_root(tmp_path: Path) -> None:
    """SeasonStore should work with an already‑existing root directory."""
    root = tmp_path / "season_index"
    root.mkdir(parents=True)
    
    # Put a dummy file to verify it's not cleaned
    dummy = root / "dummy.txt"
    dummy.write_text("test")
    
    store = SeasonStore(root)
    assert root.exists()
    assert dummy.exists()  # still there
    assert dummy.read_text() == "test"


def test_season_dir_creation_on_write(tmp_path: Path) -> None:
    """Writing season index or metadata should create the season subdirectory."""
    root = tmp_path / "season_index"
    store = SeasonStore(root)
    
    season = "2026Q1"
    index_path = store.index_path(season)
    meta_path = store.metadata_path(season)
    
    # Neither the season directory nor the files exist yet
    assert not index_path.exists()
    assert not meta_path.exists()
    
    # Write index – should create season directory
    index_obj = {
        "season": season,
        "generated_at": "2025-01-01T00:00:00Z",
        "batches": [],
    }
    store.write_index(season, index_obj)
    
    assert index_path.exists()
    assert index_path.parent.exists()  # season directory
    assert index_path.parent.name == season
    
    # Write metadata – should reuse existing season directory
    from control.season_api import SeasonMetadata
    meta = SeasonMetadata(
        season=season,
        frozen=False,
        tags=[],
        note="test",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )
    store.set_metadata(season, meta)
    
    assert meta_path.exists()
    assert meta_path.parent.exists()


def test_read_index_does_not_create_directory(tmp_path: Path) -> None:
    """Reading a non‑existent index should raise FileNotFoundError, not create directories."""
    root = tmp_path / "season_index"
    store = SeasonStore(root)
    
    season = "2026Q1"
    season_dir = store.season_dir(season)
    
    # Season directory does not exist
    assert not season_dir.exists()
    
    # Attempt to read index – should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        store.read_index(season)
    
    # Directory should still not exist (no side‑effect)
    assert not season_dir.exists()


def test_get_metadata_returns_none_not_create(tmp_path: Path) -> None:
    """get_metadata should return None, not create directory, when metadata doesn't exist."""
    root = tmp_path / "season_index"
    store = SeasonStore(root)
    
    season = "2026Q1"
    season_dir = store.season_dir(season)
    
    assert not season_dir.exists()
    meta = store.get_metadata(season)
    assert meta is None
    assert not season_dir.exists()  # still not created


def test_rebuild_index_creates_artifacts_root_if_missing(tmp_path: Path) -> None:
    """rebuild_index should create artifacts_root if it doesn't exist."""
    root = tmp_path / "season_index"
    store = SeasonStore(root)
    
    artifacts_root = tmp_path / "artifacts"
    assert not artifacts_root.exists()
    
    # This should not raise, and should create an empty artifacts directory
    result = store.rebuild_index(artifacts_root, "2026Q1")
    
    assert artifacts_root.exists()
    assert artifacts_root.is_dir()
    assert result["season"] == "2026Q1"
    assert result["batches"] == []  # no batches because no metadata.json files


def test_environment_override() -> None:
    """get_season_index_root should respect FISHBRO_SEASON_INDEX_ROOT env var."""
    import os
    
    original = os.environ.get("FISHBRO_SEASON_INDEX_ROOT")
    
    try:
        os.environ["FISHBRO_SEASON_INDEX_ROOT"] = "/custom/path/season_index"
        root = get_season_index_root()
        assert str(root) == "/custom/path/season_index"
    finally:
        if original is not None:
            os.environ["FISHBRO_SEASON_INDEX_ROOT"] = original
        else:
            os.environ.pop("FISHBRO_SEASON_INDEX_ROOT", None)