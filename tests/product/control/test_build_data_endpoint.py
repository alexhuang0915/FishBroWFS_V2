"""
Test that BUILD_DATA payload from BarPrepare is correctly handled by the API endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from control.api import app


def test_build_data_payload_accepts_explicit_job_type():
    """
    Ensure that a payload with explicit job_type=BUILD_DATA is recognized and
    does not fall back to RUN_RESEARCH_V2 validation.
    """
    with patch('control.api.supervisor_submit') as mock_submit:
        mock_submit.return_value = {'job_id': 'test_job_123'}
        
        client = TestClient(app)
        
        payload = {
            "job_type": "BUILD_DATA",
            "dataset_id": "MNQ",
            "timeframe_min": 60,
            "mode": "FULL",
            "force_rebuild": False
        }
        
        response = client.post("/api/v1/jobs", json=payload)
        
        # Should succeed (200 or 201)
        assert response.status_code in (200, 201), f"Unexpected status {response.status_code}: {response.text}"
        
        # Verify supervisor_submit was called with correct job_type
        mock_submit.assert_called_once()
        call_args = mock_submit.call_args[0]  # positional args
        assert len(call_args) >= 2
        job_type = call_args[0]
        params = call_args[1]
        metadata = call_args[2] if len(call_args) > 2 else {}
        
        assert job_type == "BUILD_DATA"
        assert params["dataset_id"] == "MNQ"
        assert params["timeframe_min"] == 60
        assert params["mode"] == "FULL"
        assert params["force_rebuild"] is False
        assert metadata.get("source") == "api_v1"
        assert metadata.get("submitted_via") == "gui"


def test_build_data_payload_missing_dataset_id_returns_422():
    """
    BUILD_DATA validation should catch missing dataset_id and return 422.
    """
    with patch('control.api.supervisor_submit') as mock_submit:
        client = TestClient(app)
        
        payload = {
            "job_type": "BUILD_DATA",
            "timeframe_min": 60,
            "mode": "FULL",
            "force_rebuild": False
            # missing dataset_id
        }
        
        response = client.post("/api/v1/jobs", json=payload)
        
        # Should be 422 validation error
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        assert "Missing required field for BUILD_DATA" in response.json()["detail"]
        
        # supervisor_submit should not be called
        mock_submit.assert_not_called()


def test_build_data_payload_with_extra_fields_ignored():
    """
    Extra fields (like instrument, timeframe) should be ignored for BUILD_DATA.
    """
    with patch('control.api.supervisor_submit') as mock_submit:
        mock_submit.return_value = {'job_id': 'test_job_456'}
        
        client = TestClient(app)
        
        payload = {
            "job_type": "BUILD_DATA",
            "dataset_id": "ES",
            "timeframe_min": 120,
            "mode": "FULL",
            "force_rebuild": True,
            "instrument": "ES",          # extra
            "timeframe": "120m",         # extra
            "season": "2025Q1",          # extra
            "run_mode": "research"       # extra
        }
        
        response = client.post("/api/v1/jobs", json=payload)
        
        assert response.status_code in (200, 201)
        
        mock_submit.assert_called_once()
        job_type = mock_submit.call_args[0][0]
        params = mock_submit.call_args[0][1]
        
        assert job_type == "BUILD_DATA"
        # extra fields should not appear in params (they may appear in metadata?)
        assert "instrument" not in params
        assert "timeframe" not in params
        assert "season" not in params
        assert "run_mode" not in params


def test_build_data_normalization_handles_case_insensitive():
    """
    normalize_job_type should handle case-insensitive job_type strings.
    """
    with patch('control.api.supervisor_submit') as mock_submit:
        mock_submit.return_value = {'job_id': 'test_job_789'}
        
        client = TestClient(app)
        
        # lowercase should still be normalized to BUILD_DATA
        payload = {
            "job_type": "build_data",   # lowercase
            "dataset_id": "NQ",
            "timeframe_min": 30,
            "mode": "FULL",
            "force_rebuild": False
        }
        
        response = client.post("/api/v1/jobs", json=payload)
        
        assert response.status_code in (200, 201)
        
        mock_submit.assert_called_once()
        job_type = mock_submit.call_args[0][0]
        assert job_type == "BUILD_DATA"  # normalized to uppercase


def test_build_data_without_explicit_job_type_falls_back_to_run_mode():
    """
    If job_type is not provided, fallback to run_mode mapping (should default to RUN_RESEARCH_V2).
    This test ensures the fallback logic still works.
    """
    with patch('control.api.supervisor_submit') as mock_submit:
        mock_submit.return_value = {'job_id': 'test_job_999'}
        
        client = TestClient(app)
        
        # payload without job_type, with run_mode research
        payload = {
            "strategy_id": "s1_v1",
            "instrument": "MNQ",
            "timeframe": "60m",
            "run_mode": "research",
            "season": "2025Q1",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31"
        }
        
        response = client.post("/api/v1/jobs", json=payload)
        
        # Should succeed (research job)
        assert response.status_code in (200, 201)
        
        mock_submit.assert_called_once()
        job_type = mock_submit.call_args[0][0]
        assert job_type == "RUN_RESEARCH_V2"



def test_build_data_payload_from_bar_prepare_with_extra_fields():
    """
    Ensure that the exact payload sent by BarPrepare (including instrument, timeframe, season)
    is correctly recognized as BUILD_DATA and not misclassified as RUN_RESEARCH_V2.
    """
    with patch('control.api.supervisor_submit') as mock_submit:
        mock_submit.return_value = {'job_id': 'test_job_bar_prepare'}

        client = TestClient(app)

        payload = {
            "job_type": "BUILD_DATA",
            "dataset_id": "MNQ",
            "timeframe_min": 60,
            "mode": "FULL",
            "force_rebuild": False,
            "instrument": "MNQ",   # extra fields that may cause confusion
            "timeframe": "60m",
            "season": "2025Q1",
        }

        response = client.post("/api/v1/jobs", json=payload)

        # Should succeed
        assert response.status_code in (200, 201), f"Unexpected status {response.status_code}: {response.text}"

        mock_submit.assert_called_once()
        job_type = mock_submit.call_args[0][0]
        params = mock_submit.call_args[0][1]
        metadata = mock_submit.call_args[0][2] if len(mock_submit.call_args[0]) > 2 else {}

        assert job_type == "BUILD_DATA"
        assert params["dataset_id"] == "MNQ"
        assert params["timeframe_min"] == 60
        assert params["mode"] == "FULL"
        assert params["force_rebuild"] is False
        # extra fields should not appear in params
        assert "instrument" not in params
        assert "timeframe" not in params
        assert "season" not in params


def test_normalize_job_type_accepts_build_data():
    """
    Ensure normalize_job_type correctly maps "BUILD_DATA" (and case variations)
    to the JobType.BUILD_DATA enum.
    """
    from control.supervisor.models import normalize_job_type, JobType

    # Canonical uppercase
    result = normalize_job_type("BUILD_DATA")
    assert result == JobType.BUILD_DATA
    assert result.value == "BUILD_DATA"

    # Lowercase
    result = normalize_job_type("build_data")
    assert result == JobType.BUILD_DATA

    # Mixed case
    result = normalize_job_type("Build_Data")
    assert result == JobType.BUILD_DATA

    # Ensure no ValueError is raised


def test_invalid_explicit_job_type_returns_422_no_fallback():
    """
    Ensure that an invalid explicit job_type returns 422 validation error
    and does NOT silently fall back to run_mode mapping.
    """
    with patch('control.api.supervisor_submit') as mock_submit:
        client = TestClient(app)

        payload = {
            "job_type": "NOT_A_REAL_TYPE",
            "instrument": "MNQ",
            "timeframe": "60m",
            "run_mode": "research",
            "season": "2025Q1",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31"
        }

        response = client.post("/api/v1/jobs", json=payload)

        # Should be 422 validation error
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        detail = response.json()["detail"]
        assert "Invalid job_type" in detail or "Invalid job_type" in detail

        # supervisor_submit should not be called
        mock_submit.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])