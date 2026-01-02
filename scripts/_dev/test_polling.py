#!/usr/bin/env python3
import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

base_url = "http://localhost:8080"
url = f"{base_url}/_nicegui_ws/socket.io/?EIO=4&transport=polling"

max_retries = 3
retry_delay = 1.0

resp = None
for attempt in range(max_retries):
    resp = requests.get(url, timeout=10)
    logger.info("Socket.IO polling response (attempt %d/%d): status=%d",
               attempt + 1, max_retries, resp.status_code)
    
    # If not 404, break out of retry loop
    if resp.status_code != 404:
        break
        
    # If 404 and not last attempt, wait and retry
    if attempt < max_retries - 1:
        logger.info("Socket.IO route returned 404, retrying after %.1f seconds...", retry_delay)
        time.sleep(retry_delay)

# The route must NOT be 404
assert resp.status_code != 404, f"Socket.IO polling route returned 404 after {max_retries} attempts (regression!)"

# Acceptable status codes: 200 (OK) or 400 (bad request) are both fine
# because the polling endpoint may reject missing session IDs, but must not 404.
assert resp.status_code in (200, 400), f"Unexpected status {resp.status_code}"

# If status is 200, the body should contain engine.io format (starts with digits)
if resp.status_code == 200:
    body = resp.text
    assert body, "Empty response body"
    # Engine.IO handshake response starts with digits (e.g., "0{"sid":"...","upgrades":[...]}")
    # We'll just ensure it's not an HTML error page
    assert not body.strip().startswith("<!DOCTYPE"), f"Response looks like HTML error page: {body[:100]}"

print("SUCCESS: Socket.IO polling route exists and returns acceptable status.")