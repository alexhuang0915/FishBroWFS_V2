from pathlib import Path

from fastapi.testclient import TestClient

from control.api import app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_wfs_policy_registry_endpoint_returns_policies():
    client = TestClient(app)
    response = client.get("/api/v1/wfs/policies")
    assert response.status_code == 200
    data = response.json()
    entries = data.get("entries", [])
    selectors = [entry.get("selector") for entry in entries]
    assert "default" in selectors
    assert "red_team" in selectors
    assert all(entry.get("hash", "").startswith("sha256:") for entry in entries)


def test_wfs_policy_registry_entries_contain_expected_fields():
    client = TestClient(app)
    response = client.get("/api/v1/wfs/policies")
    entries = response.json().get("entries", [])
    wfs_dir = (_repo_root() / "configs" / "strategies" / "wfs").resolve()
    for entry in entries:
        assert "modes" in entry and "gates" in entry
        resolved = Path(entry.get("resolved_source", "")).resolve()
        assert resolved.is_relative_to(wfs_dir)
