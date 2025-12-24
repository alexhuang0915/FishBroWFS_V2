#!/usr/bin/env python3
"""Test API endpoints."""

import os
import sys
import pytest

# Module-level integration marker
pytestmark = pytest.mark.integration

# Add project root to path
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from FishBroWFS_V2.control.api import app

# Import from same directory
try:
    from ._integration_gate import require_control_api_health
except ImportError:
    # Fallback for direct execution
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from _integration_gate import require_control_api_health

client = TestClient(app)


def test_api_status_endpoint():
    """Test /batches/test/status endpoint."""
    require_control_api_health()
    # Note: TestClient uses internal app, not external dashboard
    # This test is actually testing the Control API, not dashboard
    response = client.get('/batches/test/status')
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_api_summary_endpoint():
    """Test /batches/test/summary endpoint."""
    require_control_api_health()
    
    response = client.get('/batches/test/summary')
    assert response.status_code == 200
    data = response.json()
    # Check response structure
    assert isinstance(data, dict)


def test_api_frozenbatch_retry():
    """Test /batches/frozenbatch/retry endpoint."""
    require_control_api_health()
    
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
