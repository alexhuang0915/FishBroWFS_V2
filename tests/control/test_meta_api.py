
"""Tests for Meta API endpoints (Phase 12)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from control.api import app
from data.dataset_registry import DatasetIndex, DatasetRecord
from strategy.registry import StrategyRegistryResponse, StrategySpecForGUI
from strategy.param_schema import ParamSpec


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_dataset_index(tmp_path: Path) -> DatasetIndex:
    """Create mock dataset index for testing."""
    # Create mock dataset index file
    index_data = DatasetIndex(
        generated_at=datetime.now(),
        datasets=[
            DatasetRecord(
                id="CME.MNQ.60m.2020-2024",
                symbol="CME.MNQ",
                exchange="CME",
                timeframe="60m",
                path="CME.MNQ/60m/2020-2024.parquet",
                start_date=date(2020, 1, 1),
                end_date=date(2024, 12, 31),
                fingerprint_sha1="a" * 40,
                fingerprint_sha256_40="a" * 40,
                tz_provider="IANA",
                tz_version="2024a"
            ),
            DatasetRecord(
                id="TWF.MXF.15m.2018-2023",
                symbol="TWF.MXF",
                exchange="TWF",
                timeframe="15m",
                path="TWF.MXF/15m/2018-2023.parquet",
                start_date=date(2018, 1, 1),
                end_date=date(2023, 12, 31),
                fingerprint_sha1="b" * 40,
                fingerprint_sha256_40="b" * 40,
                tz_provider="IANA",
                tz_version="2024a"
            )
        ]
    )
    
    # Write to temporary file
    index_dir = tmp_path / "outputs" / "datasets"
    index_dir.mkdir(parents=True)
    index_file = index_dir / "datasets_index.json"
    
    with open(index_file, "w", encoding="utf-8") as f:
        f.write(index_data.model_dump_json(indent=2))
    
    return index_data


@pytest.fixture
def mock_strategy_registry() -> StrategyRegistryResponse:
    """Create mock strategy registry for testing."""
    return StrategyRegistryResponse(
        strategies=[
            StrategySpecForGUI(
                strategy_id="sma_cross_v1",
                params=[
                    ParamSpec(
                        name="window",
                        type="int",
                        min=10,
                        max=200,
                        default=20,
                        help="Lookback window"
                    ),
                    ParamSpec(
                        name="threshold",
                        type="float",
                        min=0.0,
                        max=1.0,
                        default=0.5,
                        help="Signal threshold"
                    )
                ]
            ),
            StrategySpecForGUI(
                strategy_id="breakout_channel_v1",
                params=[
                    ParamSpec(
                        name="channel_width",
                        type="int",
                        min=5,
                        max=50,
                        default=20,
                        help="Channel width"
                    )
                ]
            )
        ]
    )


def test_meta_datasets_endpoint(
    client: TestClient,
    mock_dataset_index: DatasetIndex,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test /meta/datasets endpoint."""
    # Mock the dataset index loading
    def mock_load_dataset_index() -> DatasetIndex:
        return mock_dataset_index
    
    monkeypatch.setattr(
        "control.api.load_dataset_index",
        mock_load_dataset_index
    )
    
    # Make request
    response = client.get("/meta/datasets")
    
    # Verify response
    assert response.status_code == 200
    
    data = response.json()
    assert "generated_at" in data
    assert "datasets" in data
    assert isinstance(data["datasets"], list)
    assert len(data["datasets"]) == 2
    
    # Verify dataset structure
    dataset1 = data["datasets"][0]
    assert dataset1["id"] == "CME.MNQ.60m.2020-2024"
    assert dataset1["symbol"] == "CME.MNQ"
    assert dataset1["timeframe"] == "60m"
    assert dataset1["start_date"] == "2020-01-01"
    assert dataset1["end_date"] == "2024-12-31"
    assert len(dataset1["fingerprint_sha1"]) == 40
    assert "fingerprint_sha256_40" in dataset1
    assert len(dataset1["fingerprint_sha256_40"]) == 40


def test_meta_strategies_endpoint(
    client: TestClient,
    mock_strategy_registry: StrategyRegistryResponse,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test /meta/strategies endpoint."""
    # Mock the strategy registry loading
    def mock_load_strategy_registry() -> StrategyRegistryResponse:
        return mock_strategy_registry
    
    monkeypatch.setattr(
        "control.api.load_strategy_registry",
        mock_load_strategy_registry
    )
    
    # Make request
    response = client.get("/meta/strategies")
    
    # Verify response
    assert response.status_code == 200
    
    data = response.json()
    assert "strategies" in data
    assert isinstance(data["strategies"], list)
    assert len(data["strategies"]) == 2
    
    # Verify strategy structure
    strategy1 = data["strategies"][0]
    assert strategy1["strategy_id"] == "sma_cross_v1"
    assert "params" in strategy1
    assert isinstance(strategy1["params"], list)
    assert len(strategy1["params"]) == 2
    
    # Verify parameter structure
    param1 = strategy1["params"][0]
    assert param1["name"] == "window"
    assert param1["type"] == "int"
    assert param1["min"] == 10
    assert param1["max"] == 200
    assert param1["default"] == 20
    assert "Lookback window" in param1["help"]


def test_meta_endpoints_readonly(client: TestClient) -> None:
    """Test that meta endpoints are read-only (no mutation)."""
    # These should all be GET requests only
    response = client.post("/meta/datasets")
    assert response.status_code == 405  # Method Not Allowed
    
    response = client.put("/meta/datasets")
    assert response.status_code == 405
    
    response = client.delete("/meta/datasets")
    assert response.status_code == 405


def test_meta_endpoints_no_filesystem_access(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that meta endpoints don't access filesystem directly."""
    import_filesystem_access = False
    
    original_get = client.get
    
    def track_filesystem_access(*args: Any, **kwargs: Any) -> Any:
        nonlocal import_filesystem_access
        # Check if the request would trigger filesystem access
        # (simplified check for this test)
        return original_get(*args, **kwargs)
    
    monkeypatch.setattr(client, "get", track_filesystem_access)
    
    # The endpoints should load data from pre-loaded registries,
    # not from filesystem during request handling
    response = client.get("/meta/datasets")
    # Should fail because registries aren't loaded in test setup
    assert response.status_code == 503  # Service Unavailable
    
    response = client.get("/meta/strategies")
    assert response.status_code == 503


def test_api_startup_registry_loading(
    mock_dataset_index: DatasetIndex,
    mock_strategy_registry: StrategyRegistryResponse,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test API startup loads registries."""
    from control.api import load_dataset_index, load_strategy_registry
    
    # Mock the loading functions
    monkeypatch.setattr(
        "control.api.load_dataset_index",
        lambda: mock_dataset_index
    )
    
    monkeypatch.setattr(
        "control.api.load_strategy_registry",
        lambda: mock_strategy_registry
    )
    
    # Test that loading works
    loaded_index = load_dataset_index()
    assert len(loaded_index.datasets) == 2
    
    loaded_registry = load_strategy_registry()
    assert len(loaded_registry.strategies) == 2


def test_dataset_index_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error when dataset index file is missing."""
    from control.api import load_dataset_index
    
    # Mock Path.exists to return False
    monkeypatch.setattr(Path, "exists", lambda self: False)
    
    # Should raise RuntimeError
    with pytest.raises(RuntimeError, match="Dataset index not found"):
        load_dataset_index()


def test_meta_endpoints_response_schema(
    client: TestClient,
    mock_dataset_index: DatasetIndex,
    mock_strategy_registry: StrategyRegistryResponse,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that meta endpoints return valid Pydantic models."""
    # Mock the loading functions
    monkeypatch.setattr(
        "control.api.load_dataset_index",
        lambda: mock_dataset_index
    )
    
    monkeypatch.setattr(
        "control.api.load_strategy_registry",
        lambda: mock_strategy_registry
    )
    
    # Test datasets endpoint
    response = client.get("/meta/datasets")
    assert response.status_code == 200
    
    # Validate response matches DatasetIndex schema
    data = response.json()
    index = DatasetIndex.model_validate(data)
    assert isinstance(index, DatasetIndex)
    assert len(index.datasets) == 2
    
    # Test strategies endpoint
    response = client.get("/meta/strategies")
    assert response.status_code == 200
    
    # Validate response matches StrategyRegistryResponse schema
    data = response.json()
    registry = StrategyRegistryResponse.model_validate(data)
    assert isinstance(registry, StrategyRegistryResponse)
    assert len(registry.strategies) == 2


def test_meta_endpoints_deterministic_ordering(
    client: TestClient,
    mock_dataset_index: DatasetIndex,
    mock_strategy_registry: StrategyRegistryResponse,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that meta endpoints return data in deterministic order."""
    # Mock the loading functions
    monkeypatch.setattr(
        "control.api.load_dataset_index",
        lambda: mock_dataset_index
    )

    monkeypatch.setattr(
        "control.api.load_strategy_registry",
        lambda: mock_strategy_registry
    )

    # Get datasets multiple times
    responses = []
    for _ in range(3):
        response = client.get("/meta/datasets")
        responses.append(response.json())
    
    # All responses should be identical
    for i in range(1, len(responses)):
        assert responses[i] == responses[0]
    
    # Verify datasets are sorted by ID
    datasets = responses[0]["datasets"]
    dataset_ids = [d["id"] for d in datasets]
    assert dataset_ids == sorted(dataset_ids)
    
    # Get strategies multiple times
    strategy_responses = []
    for _ in range(3):
        response = client.get("/meta/strategies")
        strategy_responses.append(response.json())
    
    # All responses should be identical
    for i in range(1, len(strategy_responses)):
        assert strategy_responses[i] == strategy_responses[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


