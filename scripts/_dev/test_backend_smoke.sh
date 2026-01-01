#!/bin/bash
set -e

echo "=== Starting backend smoke test ==="
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000

# Start backend in background
echo "Starting backend on $BACKEND_HOST:$BACKEND_PORT..."
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m uvicorn control.api:app --host $BACKEND_HOST --port $BACKEND_PORT --reload &
BACKEND_PID=$!

# Give it time to start
echo "Waiting for backend to start..."
sleep 3

# Probe /health
echo "Probing /health endpoint..."
if curl -s http://$BACKEND_HOST:$BACKEND_PORT/health | grep -q '"status":"ok"'; then
    echo "✓ Backend /health endpoint responds correctly"
else
    echo "✗ Backend /health endpoint failed"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

# Probe /worker/status (should return worker not alive)
echo "Probing /worker/status endpoint..."
if curl -s http://$BACKEND_HOST:$BACKEND_PORT/worker/status | grep -q '"alive":false'; then
    echo "✓ Worker status correctly reports not alive (no worker running)"
else
    echo "✗ Worker status endpoint unexpected response"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

# Kill backend
echo "Stopping backend (PID: $BACKEND_PID)..."
kill $BACKEND_PID 2>/dev/null || true
wait $BACKEND_PID 2>/dev/null || true

echo "=== Backend smoke test PASSED ==="
