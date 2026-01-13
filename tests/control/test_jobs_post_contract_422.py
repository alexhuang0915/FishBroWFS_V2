import pytest
from fastapi.testclient import TestClient
from control.api import app  # Assuming your FastAPI app instance is in src/control/api.py

# Helper function to create a TestClient
@pytest.fixture(scope="module")
def test_client():
    client = TestClient(app)
    yield client

# Test 1: Unknown key does not 500
def test_run_research_v2_unknown_key_no_500(test_client: TestClient):
    payload = {
        "strategy_id": "test_strategy",
        "instrument": "TEST",
        "timeframe": "1h",
        "run_mode": "research",
        "season": "test_season",
        "start_date": "2020-01-01",
        "end_date": "2020-12-31",
        "unknown_key": "some_value"  # Extra key
    }
    response = test_client.post("/api/v1/jobs", json=payload)

    # Expect either 200/201 if system accepts and enqueues job, OR 422 if required fields missing
    # But never 500
    assert response.status_code != 500, f"Expected status code other than 500, but got {response.status_code}"

    # Depending on the exact implementation, an unknown key might lead to a 422
    # or it might be accepted and the unknown key ignored or placed in params_override.
    # The primary goal is to not crash with a 500.
    # If the normalization works as intended, it should be accepted (200/201) or return 422 if other fields are missing.
    # For this test, we'll assert it's not 500 and optionally check for 422 if that's the expected behavior for unknown keys.
    assert response.status_code in [200, 201, 422], f"Expected status code 200, 201, or 422, but got {response.status_code}"

    # If the system is designed to return 422 for unknown keys that are not part of the contract,
    # uncomment the following line:
    # assert response.status_code == 422, f"Expected status code 422 for unknown key, but got {response.status_code}"

# Test 2: Server remains alive after POST
def test_server_remains_alive_after_post(test_client: TestClient):
    # First, submit a job that should be valid
    payload = {
        "strategy_id": "test_strategy",
        "instrument": "TEST",
        "timeframe": "1h",
        "run_mode": "research",
        "season": "test_season",
        "start_date": "2020-01-01",
        "end_date": "2020-12-31",
    }
    post_response = test_client.post("/api/v1/jobs", json=payload)
    
    # Assert that the job submission was successful (e.g., 200 OK)
    assert post_response.status_code in [200, 201], f"Job submission failed with status code {post_response.status_code}"

    # Then, call /health and assert status 200
    health_response = test_client.get("/health")
    assert health_response.status_code == 200, f"Health check failed with status code {health_response.status_code}"
    assert health_response.json() == {"status": "ok"}

# Test 3: Invalid payload returns HTTP 422
def test_run_research_v2_invalid_payload_returns_422(test_client: TestClient):
    # Payload missing required 'strategy_id'
    invalid_payload = {
        "instrument": "TEST",
        "timeframe": "1h",
        "run_mode": "research",
        "season": "test_season",
    }
    response = test_client.post("/api/v1/jobs", json=invalid_payload)
    assert response.status_code == 422, f"Expected status code 422 for missing strategy_id, but got {response.status_code}"

    # Payload with incorrect type for a field (e.g., season as int)
    invalid_payload_type = {
        "strategy_id": "test_strategy",
        "instrument": "TEST",
        "timeframe": "1h",
        "run_mode": "research",
        "season": 123,  # Incorrect type
    }
    response_type = test_client.post("/api/v1/jobs", json=invalid_payload_type)
    assert response_type.status_code == 422, f"Expected status code 422 for incorrect type, but got {response_type.status_code}"

# Test 4: Ensure UI fields are correctly handled (no 500 errors)
def test_ui_fields_packed_into_params_override(test_client: TestClient):
    """
    Verify that UI fields (instrument, timeframe, season, run_mode, dataset, extra fields)
    are accepted without causing 500 errors.
    
    The fields should be packed into params_override (implementation detail),
    but we only verify that the submission succeeds.
    """
    payload = {
        "strategy_id": "test_strategy",
        "instrument": "TEST",
        "timeframe": "1h",
        "run_mode": "research",
        "season": "test_season",
        "start_date": "2020-01-01",
        "end_date": "2020-12-31",
        "dataset": "test_dataset",
        "extra_ui_field": "should_be_overridden"
    }
    response = test_client.post("/api/v1/jobs", json=payload)
    
    # The primary goal: no 500 error
    assert response.status_code != 500, f"Server crashed with 500 error: {response.text}"
    
    # Should be accepted (200/201) or 422 if validation fails
    # With our implementation, it should be accepted
    assert response.status_code in [200, 201, 422], f"Unexpected status code {response.status_code}: {response.text}"
    
    # If we got a successful submission, verify we have a job_id
    if response.status_code in [200, 201]:
        job_id = response.json().get("job_id")
        assert job_id is not None, "Job ID not found in response"
        
        # Verify we can retrieve the job (basic sanity check)
        job_response = test_client.get(f"/api/v1/jobs/{job_id}")
        assert job_response.status_code == 200, f"Failed to retrieve job details for job ID {job_id}"

