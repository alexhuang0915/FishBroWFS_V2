"""Phase 14: API batch endpoints tests."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_governance_store():
    """Mock governance store.

    NOTE:
    Governance store now uses artifacts root and stores metadata at:
      artifacts/{batch_id}/metadata.json
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_root = Path(tmpdir) / "artifacts"
        artifacts_root.mkdir(parents=True, exist_ok=True)

        with patch("FishBroWFS_V2.control.api._get_artifacts_root") as mock_root, \
             patch("FishBroWFS_V2.control.api._get_governance_store") as mock_store:
            from FishBroWFS_V2.control.governance import BatchGovernanceStore
            real_store = BatchGovernanceStore(artifacts_root)
            mock_root.return_value = artifacts_root
            mock_store.return_value = real_store
            yield real_store


def test_get_batch_metadata(client, mock_governance_store):
    """GET /batches/{batch_id}/metadata returns metadata."""
    # Create metadata
    from FishBroWFS_V2.control.governance import BatchMetadata
    meta = BatchMetadata(
        batch_id="batch1",
        season="2026Q1",
        tags=["test"],
        note="hello",
        frozen=False,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="system",
    )
    mock_governance_store.set_metadata("batch1", meta)

    response = client.get("/batches/batch1/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == "batch1"
    assert data["season"] == "2026Q1"
    assert data["tags"] == ["test"]
    assert data["note"] == "hello"
    assert data["frozen"] is False


def test_get_batch_metadata_not_found(client, mock_governance_store):
    """GET /batches/{batch_id}/metadata returns 404 if not found."""
    response = client.get("/batches/nonexistent/metadata")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_update_batch_metadata(client, mock_governance_store):
    """PATCH /batches/{batch_id}/metadata updates metadata."""
    # First create
    from FishBroWFS_V2.control.governance import BatchMetadata
    meta = BatchMetadata(
        batch_id="batch1",
        season="2026Q1",
        tags=[],
        note="",
        frozen=False,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="system",
    )
    mock_governance_store.set_metadata("batch1", meta)

    # Update
    update = {"season": "2026Q2", "tags": ["newtag"], "note": "updated"}
    response = client.patch("/batches/batch1/metadata", json=update)
    assert response.status_code == 200
    data = response.json()
    assert data["season"] == "2026Q2"
    assert data["tags"] == ["newtag"]
    assert data["note"] == "updated"
    assert data["frozen"] is False
    assert data["updated_at"] != "2025-01-01T00:00:00Z"  # timestamp updated


def test_update_batch_metadata_frozen_restrictions(client, mock_governance_store):
    """PATCH respects frozen rules."""
    # Create frozen batch
    from FishBroWFS_V2.control.governance import BatchMetadata
    meta = BatchMetadata(
        batch_id="frozenbatch",
        season="2026Q1",
        tags=[],
        note="",
        frozen=True,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="system",
    )
    mock_governance_store.set_metadata("frozenbatch", meta)

    # Attempt to change season -> 400
    response = client.patch("/batches/frozenbatch/metadata", json={"season": "2026Q2"})
    assert response.status_code == 400
    assert "Cannot change season" in response.json()["detail"]

    # Attempt to unfreeze -> 400
    response = client.patch("/batches/frozenbatch/metadata", json={"frozen": False})
    assert response.status_code == 400
    assert "Cannot unfreeze" in response.json()["detail"]

    # Append tags should work
    response = client.patch("/batches/frozenbatch/metadata", json={"tags": ["newtag"]})
    assert response.status_code == 200
    data = response.json()
    assert "newtag" in data["tags"]

    # Update note should work
    response = client.patch("/batches/frozenbatch/metadata", json={"note": "updated"})
    assert response.status_code == 200
    assert response.json()["note"] == "updated"


def test_freeze_batch(client, mock_governance_store):
    """POST /batches/{batch_id}/freeze freezes batch."""
    # Create unfrozen batch
    from FishBroWFS_V2.control.governance import BatchMetadata
    meta = BatchMetadata(
        batch_id="batch1",
        season="2026Q1",
        tags=[],
        note="",
        frozen=False,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="system",
    )
    mock_governance_store.set_metadata("batch1", meta)

    response = client.post("/batches/batch1/freeze")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "frozen"
    assert data["batch_id"] == "batch1"

    # Verify frozen
    assert mock_governance_store.is_frozen("batch1") is True


def test_freeze_batch_not_found(client, mock_governance_store):
    """POST /batches/{batch_id}/freeze returns 404 if batch not found."""
    response = client.post("/batches/nonexistent/freeze")
    assert response.status_code == 404


def test_retry_batch_frozen(client, mock_governance_store):
    """POST /batches/{batch_id}/retry rejects frozen batch."""
    # Create frozen batch
    from FishBroWFS_V2.control.governance import BatchMetadata
    meta = BatchMetadata(
        batch_id="frozenbatch",
        season="2026Q1",
        tags=[],
        note="",
        frozen=True,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="system",
    )
    mock_governance_store.set_metadata("frozenbatch", meta)

    response = client.post("/batches/frozenbatch/retry", json={"force": False})
    assert response.status_code == 403
    assert "frozen" in response.json()["detail"].lower()


def test_batch_status_not_implemented(client):
    """GET /batches/{batch_id}/status returns 404 when execution.json missing."""
    # Mock artifacts root to return a path that doesn't have execution.json
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        root.mkdir(parents=True, exist_ok=True)
        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=root):
            response = client.get("/batches/batch1/status")
            assert response.status_code == 404
            assert "execution.json not found" in response.json()["detail"]


def test_batch_summary_not_implemented(client):
    """GET /batches/{batch_id}/summary returns 404 when summary.json missing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        root.mkdir(parents=True, exist_ok=True)
        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=root):
            response = client.get("/batches/batch1/summary")
            assert response.status_code == 404
            assert "summary.json not found" in response.json()["detail"]
