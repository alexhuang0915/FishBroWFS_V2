#!/usr/bin/env python3
"""Test API endpoints."""

import os
import sys
import pytest

# Module-level integration marker
pytestmark = pytest.mark.integration

# Skip entire module if integration flag not set
if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":
    pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1", allow_module_level=True)

# Add project root to path
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from FishBroWFS_V2.control.api import app

client = TestClient(app)


def test_api_status_endpoint():
    """Test /batches/test/status endpoint."""
    response = client.get('/batches/test/status')
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_api_summary_endpoint():
    """Test /batches/test/summary endpoint."""
    response = client.get('/batches/test/summary')
    assert response.status_code == 200
    data = response.json()
    # Check response structure
    assert isinstance(data, dict)


def test_api_frozenbatch_retry():
    """Test /batches/frozenbatch/retry endpoint."""
    response = client.post('/batches/frozenbatch/retry', json={"force": False})
    # This endpoint might return various status codes depending on state
    # We just check that it returns something
    assert response.status_code in [200, 400, 404]
    data = response.json()
    assert isinstance(data, dict)


if __name__ == "__main__":
    # Allow running as script for debugging
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
