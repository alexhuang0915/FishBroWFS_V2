"""
Phase 17‑C: Portfolio Plan API End‑to‑End Tests.

Contracts:
- Full flow: create plan via POST, list via GET, retrieve via GET.
- Deterministic plan ID across runs.
- Hash chain validation.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app


def _create_mock_export(tmp_path: Path, season: str, export_name: str) -> Path:
    """Create a minimal export with a few candidates."""
    export_dir = tmp_path / "seasons" / season / export_name
    export_dir.mkdir(parents=True)

    (export_dir / "manifest.json").write_text(json.dumps({}, separators=(",", ":")))
    candidates = [
        {
            "candidate_id": "cand1",
            "strategy_id": "stratA",
            "dataset_id": "ds1",
            "params": {"p": 1},
            "score": 0.9,
            "season": season,
            "source_batch": "batch1",
            "source_export": export_name,
        },
        {
            "candidate_id": "cand2",
            "strategy_id": "stratB",
            "dataset_id": "ds2",
            "params": {"p": 2},
            "score": 0.8,
            "season": season,
            "source_batch": "batch1",
            "source_export": export_name,
        },
    ]
    (export_dir / "candidates.json").write_text(json.dumps(candidates, separators=(",", ":")))
    return tmp_path


def test_full_plan_creation_and_retrieval():
    """POST → GET list → GET by ID."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = _create_mock_export(tmp_path, "season1", "export1")

        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            with patch("FishBroWFS_V2.control.api._get_outputs_root", return_value=tmp_path):
                client = TestClient(app)

                # 1. List plans (should be empty)
                resp_list = client.get("/portfolio/plans")
                assert resp_list.status_code == 200
                assert resp_list.json()["plans"] == []

                # 2. Create a plan
                payload = {
                    "season": "season1",
                    "export_name": "export1",
                    "top_n": 10,
                    "max_per_strategy": 5,
                    "max_per_dataset": 5,
                    "weighting": "bucket_equal",
                    "bucket_by": ["dataset_id"],
                    "max_weight": 0.2,
                    "min_weight": 0.0,
                }
                resp_create = client.post("/portfolio/plans", json=payload)
                assert resp_create.status_code == 200
                create_data = resp_create.json()
                assert "plan_id" in create_data
                assert "universe" in create_data
                assert "weights" in create_data
                assert "summaries" in create_data
                assert "constraints_report" in create_data

                plan_id = create_data["plan_id"]
                assert plan_id.startswith("plan_")

                # 3. List plans again (should contain the new plan)
                resp_list2 = client.get("/portfolio/plans")
                assert resp_list2.status_code == 200
                list_data = resp_list2.json()
                assert len(list_data["plans"]) == 1
                listed_plan = list_data["plans"][0]
                assert listed_plan["plan_id"] == plan_id
                assert "source" in listed_plan
                assert "config" in listed_plan

                # 4. Retrieve full plan by ID
                resp_get = client.get(f"/portfolio/plans/{plan_id}")
                assert resp_get.status_code == 200
                full_plan = resp_get.json()
                assert full_plan["plan_id"] == plan_id
                assert len(full_plan["universe"]) == 2
                assert len(full_plan["weights"]) == 2
                # Verify weight sum is 1.0
                total_weight = sum(w["weight"] for w in full_plan["weights"])
                assert abs(total_weight - 1.0) < 1e-9

                # 5. Verify plan directory exists with expected files
                plan_dir = tmp_path / "portfolio" / "plans" / plan_id
                assert plan_dir.exists()
                expected_files = {
                    "plan_metadata.json",
                    "portfolio_plan.json",
                    "plan_checksums.json",
                    "plan_manifest.json",
                }
                actual_files = {f.name for f in plan_dir.iterdir()}
                assert actual_files == expected_files

                # 6. Verify manifest self‑hash
                manifest_path = plan_dir / "plan_manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                assert "manifest_sha256" in manifest
                # (hash validation is covered in hash‑chain tests)


def test_plan_deterministic_across_api_calls():
    """Same export + same payload → same plan ID via API."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = _create_mock_export(tmp_path, "season1", "export1")

        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            with patch("FishBroWFS_V2.control.api._get_outputs_root", return_value=tmp_path):
                client = TestClient(app)

                payload = {
                    "season": "season1",
                    "export_name": "export1",
                    "top_n": 10,
                    "max_per_strategy": 5,
                    "max_per_dataset": 5,
                    "weighting": "bucket_equal",
                    "bucket_by": ["dataset_id"],
                    "max_weight": 0.2,
                    "min_weight": 0.0,
                }

                # First call
                resp1 = client.post("/portfolio/plans", json=payload)
                assert resp1.status_code == 200
                plan_id1 = resp1.json()["plan_id"]

                # Second call with identical payload (but plan already exists)
                # Should raise 409 conflict? Actually our endpoint returns 200 and same plan.
                # We'll just verify plan ID matches.
                resp2 = client.post("/portfolio/plans", json=payload)
                assert resp2.status_code == 200
                plan_id2 = resp2.json()["plan_id"]
                assert plan_id1 == plan_id2


def test_missing_export_returns_404():
    """POST with non‑existent export returns 404."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = tmp_path / "exports"
        exports_root.mkdir()

        with patch("FishBroWFS_V2.control.api.get_exports_root", return_value=exports_root):
            with patch("FishBroWFS_V2.control.api._get_outputs_root", return_value=tmp_path):
                client = TestClient(app)
                payload = {
                    "season": "season1",
                    "export_name": "nonexistent",
                    "top_n": 10,
                    "max_per_strategy": 5,
                    "max_per_dataset": 5,
                    "weighting": "bucket_equal",
                    "bucket_by": ["dataset_id"],
                    "max_weight": 0.2,
                    "min_weight": 0.0,
                }
                resp = client.post("/portfolio/plans", json=payload)
                assert resp.status_code == 404
                assert "not found" in resp.json()["detail"].lower()


def test_invalid_payload_returns_400():
    """POST with invalid payload returns 400."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with patch("FishBroWFS_V2.control.api._get_outputs_root", return_value=tmp_path):
            client = TestClient(app)
            # Missing required field 'season'
            payload = {
                "export_name": "export1",
                "top_n": 10,
            }
            resp = client.post("/portfolio/plans", json=payload)
            # FastAPI validation returns 422
            assert resp.status_code == 422


def test_list_plans_returns_correct_structure():
    """GET /portfolio/plans returns list of plan manifests."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Create a mock plan directory
        plan_dir = tmp_path / "portfolio" / "plans" / "plan_test123"
        plan_dir.mkdir(parents=True)
        manifest = {
            "plan_id": "plan_test123",
            "generated_at_utc": "2025-12-20T00:00:00Z",
            "source": {"season": "season1", "export_name": "export1"},
            "config": {"top_n": 10},
            "summaries": {"total_candidates": 5},
        }
        (plan_dir / "plan_manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))

        with patch("FishBroWFS_V2.control.api._get_outputs_root", return_value=tmp_path):
            client = TestClient(app)
            resp = client.get("/portfolio/plans")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["plans"]) == 1
            listed = data["plans"][0]
            assert listed["plan_id"] == "plan_test123"
            assert listed["generated_at_utc"] == "2025-12-20T00:00:00Z"
            assert listed["source"]["season"] == "season1"