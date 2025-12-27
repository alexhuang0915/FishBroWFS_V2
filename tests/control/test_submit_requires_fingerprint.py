"""
Test that batch submit requires a data fingerprint (no DIRTY jobs).

P0-2: fingerprint 必填（禁止 DIRTY job 進治理鏈）
"""

import pytest
from unittest.mock import Mock, patch

from FishBroWFS_V2.control.batch_submit import (
    wizard_to_db_jobspec,
    submit_batch,
)
from FishBroWFS_V2.control.job_spec import WizardJobSpec, DataSpec, WFSSpec
from FishBroWFS_V2.control.types import DBJobSpec


def test_wizard_to_db_jobspec_requires_fingerprint() -> None:
    """wizard_to_db_jobspec must raise ValueError if fingerprint is missing."""
    from datetime import date
    wizard = WizardJobSpec(
        season="2026Q1",
        data1=DataSpec(
            dataset_id="test_dataset",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
        ),
        data2=None,
        strategy_id="test_strategy",
        params={"window": 20},
        wfs=WFSSpec(),
    )
    
    # Dataset record with fingerprint -> should succeed
    dataset_record = {
        "fingerprint_sha256_40": "a" * 40,
        "normalized_sha256_40": "b" * 40,  # alternative field
    }
    
    db_spec = wizard_to_db_jobspec(wizard, dataset_record)
    assert isinstance(db_spec, DBJobSpec)
    assert db_spec.data_fingerprint_sha256_40 == "a" * 40
    
    # Dataset record with normalized_sha256_40 but no fingerprint_sha256_40
    dataset_record2 = {
        "normalized_sha256_40": "c" * 40,
    }
    db_spec2 = wizard_to_db_jobspec(wizard, dataset_record2)
    assert db_spec2.data_fingerprint_sha256_40 == "c" * 40
    
    # Dataset record with no fingerprint -> must raise
    dataset_record3 = {}
    with pytest.raises(ValueError, match="data_fingerprint_sha256_40 is required"):
        wizard_to_db_jobspec(wizard, dataset_record3)
    
    # Dataset record with empty string fingerprint -> must raise
    dataset_record4 = {"fingerprint_sha256_40": ""}
    with pytest.raises(ValueError, match="data_fingerprint_sha256_40 is required"):
        wizard_to_db_jobspec(wizard, dataset_record4)


def test_submit_batch_requires_fingerprint() -> None:
    """submit_batch must fail when dataset index lacks fingerprint."""
    from FishBroWFS_V2.control.batch_submit import submit_batch, BatchSubmitRequest
    from datetime import date
    
    wizard = WizardJobSpec(
        season="2026Q1",
        data1=DataSpec(
            dataset_id="test_dataset",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
        ),
        data2=None,
        strategy_id="test_strategy",
        params={"window": 20},
        wfs=WFSSpec(),
    )
    
    # Dataset index with fingerprint -> should succeed (mocked)
    dataset_index = {
        "test_dataset": {
            "fingerprint_sha256_40": "fingerprint1234567890123456789012345678901234567890",
        }
    }
    
    with patch("FishBroWFS_V2.control.batch_submit.create_job", return_value="job123"):
        # This should not raise
        result = submit_batch(
            db_path=":memory:",
            req=BatchSubmitRequest(jobs=[wizard]),
            dataset_index=dataset_index,
        )
        assert hasattr(result, "batch_id")
        assert result.batch_id.startswith("batch-")
    
    # Dataset index without fingerprint -> must raise
    dataset_index_bad = {
        "test_dataset": {
            # missing fingerprint
        }
    }
    
    with patch("FishBroWFS_V2.control.batch_submit.create_job", return_value="job123"):
        with pytest.raises(ValueError, match="fingerprint required"):
            submit_batch(
                db_path=":memory:",
                req=BatchSubmitRequest(jobs=[wizard]),
                dataset_index=dataset_index_bad,
            )
    
    # Dataset index with empty fingerprint -> must raise
    dataset_index_empty = {
        "test_dataset": {
            "fingerprint_sha256_40": "",
        }
    }
    
    with patch("FishBroWFS_V2.control.batch_submit.create_job", return_value="job123"):
        with pytest.raises(ValueError, match="data_fingerprint_sha256_40 is required"):
            submit_batch(
                db_path=":memory:",
                req=BatchSubmitRequest(jobs=[wizard]),
                dataset_index=dataset_index_empty,
            )


def test_api_endpoint_enforces_fingerprint() -> None:
    """The batch submit API endpoint should return 400 when fingerprint missing."""
    from fastapi.testclient import TestClient
    from FishBroWFS_V2.control.api import app
    from FishBroWFS_V2.data.dataset_registry import DatasetIndex, DatasetRecord
    from datetime import date
    
    client = TestClient(app)
    
    # Create a dataset record with empty fingerprint (should trigger error)
    dataset_record = DatasetRecord(
        id="test_dataset",
        symbol="TEST",
        exchange="TEST",
        timeframe="60m",
        path="test/path.parquet",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31),
        fingerprint_sha256_40="",  # empty fingerprint
        fingerprint_sha1="",
        tz_provider="IANA",
        tz_version="unknown"
    )
    mock_index = DatasetIndex(generated_at="2025-12-23T00:00:00Z", datasets=[dataset_record])
    
    # Mock the dataset index loading
    import FishBroWFS_V2.control.api as api_module
    
    with patch.object(api_module, "load_dataset_index", return_value=mock_index), \
         patch.object(api_module, "_check_worker_status") as mock_check:
        # Mock worker as alive to avoid 503
        mock_check.return_value = {
            "alive": True,
            "pid": 12345,
            "last_heartbeat_age_sec": 1.0,
            "reason": "worker alive",
            "expected_db": "some/path.db",
        }
        # Prime registries first (required by API)
        client.post("/meta/prime")
        
        # Submit batch request to correct endpoint
        payload = {
            "jobs": [
                {
                    "season": "2026Q1",
                    "data1": {
                        "dataset_id": "test_dataset",
                        "start_date": "2020-01-01",
                        "end_date": "2024-12-31",
                    },
                    "data2": None,
                    "strategy_id": "test_strategy",
                    "params": {"window": 20},
                    "wfs": {
                        "stage0_subsample": 1.0,
                        "top_k": 100,
                        "mem_limit_mb": 4096,
                        "allow_auto_downsample": True,
                    },
                }
            ]
        }
        
        response = client.post("/jobs/batch", json=payload)
        # Should be 400 Bad Request because fingerprint missing
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        # Check that error mentions fingerprint
        assert "fingerprint" in response.text.lower() or "required" in response.text.lower()