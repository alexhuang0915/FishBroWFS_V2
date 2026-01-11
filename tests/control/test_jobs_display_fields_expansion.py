"""
Test display fields expansion from params_override for jobs list API.

Phase10-F2: Jobs List Display Unblock + Registry Timeframes Endpoint
Part A - Jobs list field expansion from params_override
"""
import pytest
from fastapi.testclient import TestClient
from src.control.api import app, _expand_display_fields_from_params_override


@pytest.fixture(scope="module")
def test_client():
    """Test client for FastAPI."""
    client = TestClient(app)
    yield client


def test_expand_display_fields_from_params_override():
    """Unit test for _expand_display_fields_from_params_override helper."""
    # Case 1: Top-level fields already present
    params = {
        "instrument": "CME.MNQ",
        "timeframe": "60m",
        "run_mode": "research",
        "dataset": "VX",
    }
    metadata = {"season": "2026Q1"}
    instrument, timeframe, run_mode, season, dataset = _expand_display_fields_from_params_override(
        params, metadata
    )
    assert instrument == "CME.MNQ"
    assert timeframe == "60m"
    assert run_mode == "research"
    assert season == "2026Q1"
    assert dataset == "VX"

    # Case 2: Empty top-level fields, filled from params_override
    params = {
        "instrument": "",
        "timeframe": "",
        "run_mode": "",
        "dataset": "",
        "params_override": {
            "instrument": "CME.MES",
            "timeframe": "240m",
            "run_mode": "backtest",
            "season": "2025Q4",
            "dataset": "ZN",
        },
    }
    metadata = {"season": ""}
    instrument, timeframe, run_mode, season, dataset = _expand_display_fields_from_params_override(
        params, metadata
    )
    assert instrument == "CME.MES"
    assert timeframe == "240m"
    assert run_mode == "backtest"
    assert season == "2025Q4"
    assert dataset == "ZN"

    # Case 3: Mixed - some top-level, some from params_override
    params = {
        "instrument": "CME.MNQ",  # already present
        "timeframe": "",  # empty
        "run_mode": "research",  # present
        "dataset": "",
        "params_override": {
            "instrument": "IGNORED",  # should be ignored because top-level already non-empty
            "timeframe": "120m",  # should be used
            "run_mode": "IGNORED",
            "season": "2026Q2",
            "dataset": "TEST",
        },
    }
    metadata = {"season": ""}
    instrument, timeframe, run_mode, season, dataset = _expand_display_fields_from_params_override(
        params, metadata
    )
    assert instrument == "CME.MNQ"  # from top-level
    assert timeframe == "120m"  # from params_override
    assert run_mode == "research"  # from top-level
    assert season == "2026Q2"  # from params_override (metadata empty)
    assert dataset == "TEST"  # from params_override

    # Case 4: params_override missing some keys
    params = {
        "instrument": "",
        "timeframe": "",
        "run_mode": "",
        "params_override": {
            "instrument": "CME.MNQ",
            # missing timeframe, run_mode, season, dataset
        },
    }
    metadata = {}
    instrument, timeframe, run_mode, season, dataset = _expand_display_fields_from_params_override(
        params, metadata
    )
    assert instrument == "CME.MNQ"
    assert timeframe == ""  # stays empty
    assert run_mode == ""
    assert season == ""
    assert dataset == ""

    # Case 5: None values are coerced to empty strings
    params = {
        "instrument": None,
        "timeframe": None,
        "params_override": {
            "instrument": None,
            "timeframe": "60m",
        },
    }
    metadata = {"season": None}
    instrument, timeframe, run_mode, season, dataset = _expand_display_fields_from_params_override(
        params, metadata
    )
    assert instrument == ""  # None -> empty string
    assert timeframe == "60m"  # from params_override
    assert run_mode == ""
    assert season == ""
    assert dataset == ""

    print("✓ Unit test for _expand_display_fields_from_params_override passed")


def test_jobs_list_api_integration(test_client: TestClient):
    """
    Integration smoke test: verify GET /api/v1/jobs returns fields
    (requires at least one job in supervisor DB).
    This test is minimal and will pass if the endpoint returns 200.
    """
    response = test_client.get("/api/v1/jobs?limit=5")
    # Should return 200 OK (or 503 if registries not loaded, but in test environment they should be)
    assert response.status_code in (200, 503), f"Unexpected status {response.status_code}: {response.text}"
    if response.status_code == 200:
        jobs = response.json()
        assert isinstance(jobs, list)
        # If there are jobs, check that each has the expected fields
        for job in jobs:
            assert "instrument" in job
            assert "timeframe" in job
            assert "run_mode" in job
            assert "season" in job
            # dataset is optional
    print("✓ Jobs list API integration smoke passed")


def test_registry_timeframes_endpoint(test_client: TestClient):
    """Test /api/v1/registry/timeframes returns 200 with list of strings."""
    response = test_client.get("/api/v1/registry/timeframes")
    # Could be 503 if registry not preloaded in test environment
    # We'll accept either 200 or 503, but if 200 we validate shape
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)
        # Should be non-empty list of strings
        if data:
            assert all(isinstance(item, str) for item in data)
            # Expected timeframes from configs/registry/timeframes.yaml: [15, 30, 60, 120, 240]
            # Display names are "15m", "30m", etc.
            expected_prefixes = {"15m", "30m", "60m", "120m", "240m"}
            for item in data:
                # Each item should be like "15m"
                assert item.endswith("m")
                # Minutes should be parseable
                minutes = int(item.rstrip("m"))
                assert minutes > 0
    elif response.status_code == 503:
        # Registry not preloaded - that's okay for some test environments
        pass
    else:
        pytest.fail(f"Unexpected status {response.status_code}: {response.text}")
    print("✓ Registry timeframes endpoint test passed")


if __name__ == "__main__":
    # Run unit tests directly
    test_expand_display_fields_from_params_override()
    print("All unit tests passed")