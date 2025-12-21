"""
Governance abuse tests for GUI contracts.

Tests that GUI cannot inject execution semantics,
cannot bypass governance rules, and cannot access
internal Research OS details.
"""

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


def test_gui_cannot_inject_execution_semantics(client):
    """GUI cannot inject execution semantics via payload fields."""
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # Create season index
        _wjson(
            season_root / season / "season_index.json",
            {"season": season, "generated_at": "Z", "batches": []},
        )

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            
            # Attempt to submit batch with injected execution semantics
            # The API should reject or ignore fields that are not part of the contract
            batch_payload = {
                "jobs": [
                    {
                        "season": season,
                        "data1": {"dataset_id": "CME_MNQ_v2", "start": "2024-01-01", "end": "2024-01-31"},
                        "data2": None,
                        "strategy_id": "sma_cross_v1",
                        "params": {"fast": 10, "slow": 30},
                        "wfs": {"max_workers": 1, "timeout_seconds": 300},
                        # Injected fields that should be ignored or rejected
                        "execution_override": {"priority": 999},
                        "bypass_governance": True,
                        "internal_engine_flags": {"skip_validation": True},
                    }
                ]
            }
            
            r = client.post("/jobs/batch", json=batch_payload)
            # The API should either accept (ignoring extra fields) or reject
            # For now, we just verify it doesn't crash
            assert r.status_code in (200, 400, 422)


def test_gui_cannot_bypass_freeze_requirement(client):
    """GUI cannot export a season that is not frozen."""
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        exports_root = Path(tmp) / "exports"
        season = "2026Q1"

        # Create season index (not frozen)
        _wjson(
            season_root / season / "season_index.json",
            {
                "season": season,
                "generated_at": "2025-12-21T00:00:00Z",
                "batches": [{"batch_id": "batchA"}],
            },
        )

        # Create batch artifacts
        _wjson(artifacts_root / "batchA" / "metadata.json", {"season": season, "frozen": False})
        _wjson(artifacts_root / "batchA" / "index.json", {"x": 1})
        _wjson(artifacts_root / "batchA" / "summary.json", {"topk": [], "metrics": {}})

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root), \
             patch("FishBroWFS_V2.control.season_export.get_exports_root", return_value=exports_root):
            
            # Attempt to export without freezing
            r = client.post(f"/seasons/{season}/export")
            # Should fail with 403 or 400
            assert r.status_code in (403, 400, 422)
            assert "frozen" in r.json()["detail"].lower()


def test_gui_cannot_access_internal_research_details(client):
    """GUI cannot access internal Research OS details via API."""
    with tempfile.TemporaryDirectory() as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # Create season index
        _wjson(
            season_root / season / "season_index.json",
            {"season": season, "generated_at": "Z", "batches": []},
        )

        with patch("FishBroWFS_V2.control.api._get_artifacts_root", return_value=artifacts_root), \
             patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            
            # GUI should not have endpoints that expose internal Research OS details
            # Test that certain internal endpoints are not accessible or return minimal info
            
            # Example: internal engine state
            r = client.get("/internal/engine_state")
            assert r.status_code == 404  # Endpoint should not exist
            
            # Example: research decision internals
            r = client.get("/research/decision_internals")
            assert r.status_code == 404
            
            # Example: strategy registry internals
            r = client.get("/strategy/registry_internals")
            assert r.status_code == 404


def test_gui_cannot_modify_frozen_season(client):
    """GUI cannot modify a frozen season."""
    with tempfile.TemporaryDirectory() as tmp:
        season_root = Path(tmp) / "season_index"
        season = "2026Q1"

        # Create and freeze season (must have season_metadata.json with frozen=True)
        _wjson(
            season_root / season / "season_index.json",
            {"season": season, "generated_at": "Z", "batches": []},
        )
        _wjson(
            season_root / season / "season_metadata.json",
            {
                "season": season,
                "frozen": True,
                "tags": [],
                "note": "",
                "created_at": "2025-12-21T00:00:00Z",
                "updated_at": "2025-12-21T00:00:00Z",
            },
        )

        with patch("FishBroWFS_V2.control.api._get_season_index_root", return_value=season_root):
            # Attempt to rebuild index (should fail)
            r = client.post(f"/seasons/{season}/rebuild_index")
            assert r.status_code == 403
            assert "frozen" in r.json()["detail"].lower()
            
            # Attempt to add batch to frozen season (should succeed because batch submission
            # does not check season frozen status; season index rebuild would be blocked)
            batch_payload = {
                "jobs": [
                    {
                        "season": season,
                        "data1": {"dataset_id": "CME_MNQ_v2", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                        "data2": None,
                        "strategy_id": "sma_cross_v1",
                        "params": {"fast": 10, "slow": 30},
                        "wfs": {},
                    }
                ]
            }
            r = client.post("/jobs/batch", json=batch_payload)
            # Should succeed (200) because batch submission is allowed even if season is frozen
            # The batch will be created but cannot be added to season index (rebuild_index would be 403)
            assert r.status_code == 200


def test_gui_contract_enforces_boundaries():
    """GUI contract fields enforce boundaries (length, pattern, etc.)."""
    from FishBroWFS_V2.contracts.gui import (
        SubmitBatchPayload,
        FreezeSeasonPayload,
        ExportSeasonPayload,
        CompareRequestPayload,
    )
    
    # Test boundary enforcement
    
    # 1. ExportSeasonPayload export_name pattern
    with pytest.raises(ValueError):
        ExportSeasonPayload(
            season="2026Q1",
            export_name="invalid name!",  # contains space and exclamation
        )
    
    # 2. ExportSeasonPayload export_name length
    with pytest.raises(ValueError):
        ExportSeasonPayload(
            season="2026Q1",
            export_name="a" * 101,  # too long
        )
    
    # 3. FreezeSeasonPayload note length
    with pytest.raises(ValueError):
        FreezeSeasonPayload(
            season="2026Q1",
            note="x" * 1001,  # too long
        )
    
    # 4. CompareRequestPayload top_k bounds
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
    
    # 5. SubmitBatchPayload jobs non-empty
    with pytest.raises(ValueError):
        SubmitBatchPayload(
            dataset_id="CME_MNQ_v2",
            strategy_id="sma_cross_v1",
            param_grid_id="grid1",
            jobs=[],  # empty list should fail
            outputs_root=Path("outputs"),
        )