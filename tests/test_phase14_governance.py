"""Phase 14: Governance tests."""

import tempfile
from pathlib import Path

from FishBroWFS_V2.control.governance import (
    BatchGovernanceStore,
    BatchMetadata,
)


def test_batch_metadata_creation():
    """BatchMetadata can be created with defaults."""
    meta = BatchMetadata(batch_id="batch1", season="2026Q1", tags=["test"], note="hello")
    assert meta.batch_id == "batch1"
    assert meta.season == "2026Q1"
    assert meta.tags == ["test"]
    assert meta.note == "hello"
    assert meta.frozen is False
    assert meta.created_at == ""
    assert meta.updated_at == ""


def test_batch_governance_store_init():
    """Store creates directory if not exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir) / "artifacts"
        store = BatchGovernanceStore(store_root)
        assert store.artifacts_root.exists()
        assert store.artifacts_root.is_dir()


def test_batch_governance_store_set_get():
    """Store can set and retrieve metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir) / "artifacts"
        store = BatchGovernanceStore(store_root)

        meta = BatchMetadata(
            batch_id="batch1",
            season="2026Q1",
            tags=["tag1", "tag2"],
            note="test note",
            frozen=False,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            created_by="user",
        )

        store.set_metadata("batch1", meta)

        retrieved = store.get_metadata("batch1")
        assert retrieved is not None
        assert retrieved.batch_id == meta.batch_id
        assert retrieved.season == meta.season
        assert retrieved.tags == meta.tags
        assert retrieved.note == meta.note
        assert retrieved.frozen == meta.frozen
        assert retrieved.created_at == meta.created_at
        assert retrieved.updated_at == meta.updated_at
        assert retrieved.created_by == meta.created_by


def test_batch_governance_store_update_metadata_new():
    """Update metadata creates new metadata if not exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir) / "artifacts"
        store = BatchGovernanceStore(store_root)

        meta = store.update_metadata(
            "newbatch",
            season="2026Q2",
            tags=["new"],
            note="created",
        )

        assert meta.batch_id == "newbatch"
        assert meta.season == "2026Q2"
        assert meta.tags == ["new"]
        assert meta.note == "created"
        assert meta.frozen is False
        assert meta.created_at != ""
        assert meta.updated_at != ""


def test_batch_governance_store_update_metadata_frozen_rules():
    """Frozen batch restricts updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir) / "artifacts"
        store = BatchGovernanceStore(store_root)

        # Create a frozen batch
        meta = store.update_metadata("frozenbatch", season="2026Q1", frozen=True)
        assert meta.frozen is True

        import pytest
        # Attempt to change season -> should raise
        with pytest.raises(ValueError, match="Cannot change season of frozen batch"):
            store.update_metadata("frozenbatch", season="2026Q2")

        # Attempt to unfreeze -> should raise
        with pytest.raises(ValueError, match="Cannot unfreeze a frozen batch"):
            store.update_metadata("frozenbatch", frozen=False)

        # Append tags should work
        meta2 = store.update_metadata("frozenbatch", tags=["newtag"])
        assert "newtag" in meta2.tags
        assert meta2.season == "2026Q1"  # unchanged

        # Update note should work
        meta3 = store.update_metadata("frozenbatch", note="updated note")
        assert meta3.note == "updated note"

        # Setting frozen=True again is no-op
        meta4 = store.update_metadata("frozenbatch", frozen=True)
        assert meta4.frozen is True


def test_batch_governance_store_freeze():
    """Freeze method sets frozen flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir) / "artifacts"
        store = BatchGovernanceStore(store_root)

        store.update_metadata("batch1", season="2026Q1")
        assert store.is_frozen("batch1") is False

        store.freeze("batch1")
        assert store.is_frozen("batch1") is True

        # Freeze again is idempotent
        store.freeze("batch1")
        assert store.is_frozen("batch1") is True


def test_batch_governance_store_list_batches():
    """List batches with filters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir) / "artifacts"
        store = BatchGovernanceStore(store_root)

        store.update_metadata("batch1", season="2026Q1", tags=["a", "b"])
        store.update_metadata("batch2", season="2026Q1", tags=["b", "c"], frozen=True)
        store.update_metadata("batch3", season="2026Q2", tags=["a"])

        # All batches
        all_batches = store.list_batches()
        assert len(all_batches) == 3
        ids = [m.batch_id for m in all_batches]
        assert sorted(ids) == ["batch1", "batch2", "batch3"]

        # Filter by season
        season_batches = store.list_batches(season="2026Q1")
        assert len(season_batches) == 2
        assert {m.batch_id for m in season_batches} == {"batch1", "batch2"}

        # Filter by tag
        tag_batches = store.list_batches(tag="a")
        assert {m.batch_id for m in tag_batches} == {"batch1", "batch3"}

        # Filter by frozen
        frozen_batches = store.list_batches(frozen=True)
        assert {m.batch_id for m in frozen_batches} == {"batch2"}
