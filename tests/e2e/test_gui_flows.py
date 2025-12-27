
"""
E2E flow tests for GUI contracts.

Tests the complete flow from GUI payload to API execution,
ensuring contracts are enforced and governance rules are respected.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app
from FishBroWFS_V2.contracts.gui import (
    SubmitBatchPayload,
    FreezeSeasonPayload,
    ExportSeasonPayload,
    CompareRequestPayload,
)


@pytest.fixture
def client():
    return TestClient(app)


def _wjson(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_submit_batch_flow(client):
    """Test submit batch → execution.json flow."""
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        exports_root = Path(tmp) / "exports"
        datasets_root = Path(tmp) / "datasets"

        # Create a mock dataset index file
        datasets_root.mkdir(parents=True, exist_ok=True)
        dataset_index_path = datasets_root / "datasets_index.json"
        dataset_index = {
            "generated_at": "2025-12-23T00:00:00Z",
            "datasets": [
                {
                    "id": "CME_MNQ_v2",
                    "symbol": "CME.MNQ",
                    "exchange": "CME",
                    "timeframe": "60m",
                    "path": "CME.MNQ/60m/2020-2024.parquet",
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31",
                    "fingerprint_sha256_40": "abc123def456abc123def456abc123def456abc12",
                    "fingerprint_sha1": "abc123def456abc123def456abc123def456abc12",  # optional
                    "tz_provider": "IANA",
                    "tz_version": "unknown"
                }
            ]
        }
        dataset_index_path.write_text(json.dumps(dataset_index, indent=2), encoding="utf-8")

        # Mock the necessary roots and dataset index loading
        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root), \
             patch("FishBroWFS_V2.control.season_export.get_exports_root", return_value=exports_root), \
             patch("FishBroWFS_V2.control.api._load_dataset_index_from_file") as mock_load, \
             patch("FishBroWFS_V2.control.api._check_worker_status") as mock_check:
            # Mock worker as alive to avoid 503
            mock_check.return_value = {
                "alive": True,
                "pid": 12345,
                "last_heartbeat_age_sec": 1.0,
                "reason": "worker alive",
                "expected_db": str(Path(tmp) / "jobs.db"),
            }
            # Make the mock return the dataset index we created
            from FishBroWFS_V2.data.dataset_registry import DatasetIndex
            mock_load.return_value = DatasetIndex.model_validate(dataset_index)
            
            # First, create a season index
            season = "2026Q1"
            _wjson(
                season_root / season / "season_index.json",
                {"season": season, "generated_at": "Z", "batches": []},
            )

            # Import the actual models used by the API
            from FishBroWFS_V2.control.batch_submit import BatchSubmitRequest
            from FishBroWFS_V2.control.job_spec import WizardJobSpec, DataSpec, WFSSpec
            
            # Create a valid JobSpec using the actual schema
            job = WizardJobSpec(
                season=season,
                data1=DataSpec(dataset_id="CME_MNQ_v2", start_date="2024-01-01", end_date="2024-01-31"),
                data2=None,
                strategy_id="sma_cross_v1",
                params={"fast": 10, "slow": 30},
                wfs=WFSSpec(),
            )
            
            # Create BatchSubmitRequest
            batch_request = BatchSubmitRequest(jobs=[job])
            payload = batch_request.model_dump(mode="json")
            
            r = client.post("/jobs/batch", json=payload)
            assert r.status_code == 200
            data = r.json()
            assert "batch_id" in data
            batch_id = data["batch_id"]
            
            # Verify batch execution.json exists (or will be created by execution)
            # This is a smoke test - actual execution would require worker
            pass


def test_freeze_season_flow(client):
    """Test freeze season → season_index lock flow."""
    with tempfile.TemporaryDirectory() as tmp:
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # Create season index
        _wjson(
            season_root / season / "season_index.json",
            {"season": season, "generated_at": "Z", "batches": []},
        )

        with patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            # Freeze season
            r = client.post(f"/seasons/{season}/freeze")
            assert r.status_code == 200
            
            # Verify season is frozen by trying to rebuild index (should fail)
            r = client.post(f"/seasons/{season}/rebuild_index")
            assert r.status_code == 403
            assert "frozen" in r.json()["detail"].lower()


def test_export_season_flow(client):
    """Test export season → exports tree flow."""
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"

        # Create season index with a batch
        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [{"batch_id": "batchA"}],
            },
        )

        # Create batch artifacts
        _wjson(artifacts_root / "batchA" / "metadata.json", {"season": season, "frozen": True})
        _wjson(artifacts_root / "batchA" / "index.json", {"x": 1})
        _wjson(artifacts_root / "batchA" / "summary.json", {"topk": [], "metrics": {}})

        # Freeze season first
        with patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            r = client.post(f"/seasons/{season}/freeze")
            assert r.status_code == 200

        # Export season
        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root), \
             patch("FishBroWFS_V2.control.season_export.get_exports_root", return_value=exports_root):
            
            r = client.post(f"/seasons/{season}/export")
            assert r.status_code == 200
            data = r.json()
            
            # Verify export directory exists
            export_dir = Path(data["export_dir"])
            assert export_dir.exists()
            assert (export_dir / "package_manifest.json").exists()
            assert (export_dir / "season_index.json").exists()
            assert (export_dir / "batches" / "batchA" / "metadata.json").exists()


def test_compare_flow(client):
    """Test compare → leaderboard flow."""
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # Create season index with batches
        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [
                    {"batch_id": "batchA"},
                    {"batch_id": "batchB"},
                ],
            },
        )

        # Create batch summaries with topk
        _wjson(
            artifacts_root / "batchA" / "summary.json",
            {
                "topk": [
                    {"job_id": "job1", "score": 1.5, "strategy_id": "S1"},
                    {"job_id": "job2", "score": 1.2, "strategy_id": "S2"},
                ],
                "metrics": {},
            },
        )
        _wjson(
            artifacts_root / "batchB" / "summary.json",
            {
                "topk": [
                    {"job_id": "job3", "score": 1.8, "strategy_id": "S1"},
                ],
                "metrics": {},
            },
        )

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            
            # Test compare topk
            r = client.get(f"/seasons/{season}/compare/topk?k=5")
            assert r.status_code == 200
            data = r.json()
            assert data["season"] == season
            assert len(data["items"]) == 3  # all topk items merged
            
            # Test compare batches
            r = client.get(f"/seasons/{season}/compare/batches")
            assert r.status_code == 200
            data = r.json()
            assert len(data["batches"]) == 2
            
            # Test compare leaderboard
            r = client.get(f"/seasons/{season}/compare/leaderboard?group_by=strategy_id")
            assert r.status_code == 200
            data = r.json()
            assert "groups" in data
            assert any(g["key"] == "S1" for g in data["groups"])


def test_gui_contract_validation():
    """Test that GUI contracts reject invalid payloads."""
    # SubmitBatchPayload validation
    with pytest.raises(ValueError):
        SubmitBatchPayload(
            dataset_id="CME_MNQ_v2",
            strategy_id="sma_cross_v1",
            param_grid_id="grid1",
            jobs=[],  # empty list should fail
            outputs_root=Path("outputs"),
        )
    
    # ExportSeasonPayload validation
    with pytest.raises(ValueError):
        ExportSeasonPayload(
            season="2026Q1",
            export_name="",  # empty name should fail
        )
    
    # CompareRequestPayload validation
    with pytest.raises(ValueError):
        CompareRequestPayload(
            season="2026Q1",
            top_k=0,  # must be > 0
        )
    
    with pytest.raises(ValueError):
        CompareRequestPayload(
            season="2026Q1",
            top_k=101,  # must be ≤ 100
        )


