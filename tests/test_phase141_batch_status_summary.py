
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from control.api import app


@pytest.fixture
def client():
    return TestClient(app)


def _write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_batch_status_reads_execution_json(client):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        batch_id = "batch1"

        # execution schema: jobs mapping
        _write_json(
            root / batch_id / "execution.json",
            {
                "batch_state": "RUNNING",
                "jobs": {
                    "jobA": {"state": "SUCCESS"},
                    "jobB": {"state": "FAILED"},
                    "jobC": {"state": "RUNNING"},
                },
            },
        )

        with patch("control.api._get_artifacts_root", return_value=root):
            r = client.get(f"/batches/{batch_id}/status")
            assert r.status_code == 200
            data = r.json()
            assert data["batch_id"] == batch_id
            assert data["state"] == "RUNNING"
            assert data["jobs_total"] == 3
            assert data["jobs_done"] == 1
            assert data["jobs_failed"] == 1


def test_batch_status_missing_execution_json(client):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        with patch("control.api._get_artifacts_root", return_value=root):
            r = client.get("/batches/batchX/status")
            assert r.status_code == 404


def test_batch_summary_reads_summary_json(client):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        batch_id = "batch1"
        _write_json(
            root / batch_id / "summary.json",
            {"topk": [{"job_id": "jobA", "score": 1.23}], "metrics": {"n": 10}},
        )

        with patch("control.api._get_artifacts_root", return_value=root):
            r = client.get(f"/batches/{batch_id}/summary")
            assert r.status_code == 200
            data = r.json()
            assert data["batch_id"] == batch_id
            assert isinstance(data["topk"], list)
            assert data["topk"][0]["job_id"] == "jobA"
            assert data["metrics"]["n"] == 10


def test_batch_summary_missing_summary_json(client):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        with patch("control.api._get_artifacts_root", return_value=root):
            r = client.get("/batches/batchX/summary")
            assert r.status_code == 404


def test_batch_index_endpoint(client):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        batch_id = "batch1"
        _write_json(root / batch_id / "index.json", {"batch_id": batch_id, "jobs": ["jobA", "jobB"]})

        with patch("control.api._get_artifacts_root", return_value=root):
            r = client.get(f"/batches/{batch_id}/index")
            assert r.status_code == 200
            assert r.json()["batch_id"] == batch_id


def test_batch_artifacts_listing(client):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        batch_id = "batch1"

        # artifacts tree
        _write_json(
            root / batch_id / "jobA" / "attempt_1" / "manifest.json",
            {"job_id": "jobA", "score": 2.0},
        )
        _write_json(
            root / batch_id / "jobA" / "attempt_2" / "manifest.json",
            {"job_id": "jobA", "metrics": {"score": 3.0}},
        )
        (root / batch_id / "jobB" / "attempt_1").mkdir(parents=True, exist_ok=True)  # no manifest ok

        with patch("control.api._get_artifacts_root", return_value=root):
            r = client.get(f"/batches/{batch_id}/artifacts")
            assert r.status_code == 200
            data = r.json()
            assert data["batch_id"] == batch_id
            assert [j["job_id"] for j in data["jobs"]] == ["jobA", "jobB"]
            jobA = data["jobs"][0]
            assert [a["attempt"] for a in jobA["attempts"]] == [1, 2]


