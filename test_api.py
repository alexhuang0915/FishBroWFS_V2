#!/usr/bin/env python3
"""Test API endpoints."""

import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from FishBroWFS_V2.control.api import app

client = TestClient(app)

# Test status endpoint
print("Testing /batches/test/status...")
response = client.get('/batches/test/status')
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

print("\nTesting /batches/test/summary...")
response = client.get('/batches/test/summary')
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

print("\nTesting /batches/frozenbatch/retry (frozen check)...")
response = client.post('/batches/frozenbatch/retry', json={"force": False})
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")